from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools import ttLib
from fontTools.misc import sstruct
from fontTools.misc.fixedTools import fixedToFloat, floatToFixed
from fontTools.misc.textTools import safeEval
from fontTools.ttLib import TTLibError
from . import DefaultTable
import array
import struct
import warnings


# Apple's documentation of 'avar':
# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6avar.html

AVAR_HEADER_FORMAT = """
    > # big endian
    version:    L
    axisCount:  L
"""


class table__a_v_a_r(DefaultTable.DefaultTable):
    dependencies = ["fvar"]

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.segments = {}

    def compile(self, ttFont):
        fvarAxes = ttFont["fvar"].table.VariationAxis
        axisTags = [axis.AxisTag for axis in fvarAxes]
        header = {"version": 0x00010000, "axisCount": len(axisTags)}
        result = [sstruct.pack(AVAR_HEADER_FORMAT, header)]
        for axis in axisTags:
            mappings = sorted(self.segments[axis].items())
            result.append(struct.pack(">H", len(mappings)))
            for key, value in mappings:
                fixedKey = floatToFixed(key, 14)
                fixedValue = floatToFixed(value, 14)
                result.append(struct.pack(">hh", fixedKey, fixedValue))
        return bytesjoin(result)

    def decompile(self, data, ttFont):
        fvarAxes = ttFont["fvar"].table.VariationAxis
        axisTags = [axis.AxisTag for axis in fvarAxes]
        header = {}
        headerSize = sstruct.calcsize(AVAR_HEADER_FORMAT)
        header = sstruct.unpack(AVAR_HEADER_FORMAT, data[0:headerSize])
        if header["version"] != 0x00010000:
            raise TTLibError("unsupported 'avar' version %04x" % header["version"])
        pos = headerSize
        for axis in axisTags:
            segments = self.segments[axis] = {}
            numPairs = struct.unpack(">H", data[pos:pos+2])[0]
            pos = pos + 2
            for _ in range(numPairs):
                fromValue, toValue = struct.unpack(">hh", data[pos:pos+4])
                segments[fixedToFloat(fromValue, 14)] = fixedToFloat(toValue, 14)
                pos = pos + 4
        self.fixupSegments_(warn=warnings.warn)

    def toXML(self, writer, ttFont, progress=None):
        axisTags = [axis.AxisTag for axis in ttFont["fvar"].table.VariationAxis]
        for axis in axisTags:
            writer.begintag("segment", axis=axis)
            writer.newline()
            for key, value in sorted(self.segments[axis].items()):
                writer.simpletag("mapping", **{"from": key, "to": value})
                writer.newline()
            writer.endtag("segment")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "segment":
            axis = attrs["axis"]
            segment = self.segments[axis] = {}
            for element in content:
                if isinstance(element, tuple):
                    elementName, elementAttrs, _ = element
                    if elementName == "mapping":
                        fromValue = safeEval(elementAttrs["from"])
                        toValue = safeEval(elementAttrs["to"])
                        if fromValue in segment:
                            warnings.warn("duplicate entry for %s in axis '%s'" %
                                          (fromValue, axis))
                        segment[fromValue] = toValue
            self.fixupSegments_(warn=warnings.warn)

    def fixupSegments_(self, warn):
        for axis, mappings in self.segments.items():
            for k in [-1.0, 0.0, 1.0]:
                if mappings.get(k) != k:
                    warn("avar axis '%s' should map %s to %s" % (axis, k, k))
                    mappings[k] = k
