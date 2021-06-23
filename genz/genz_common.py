# Copyright  ©  2020-2021 IntelliProp Inc.
# Copyright (c) 2020 Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from ctypes import *
import uuid
from enum import IntEnum

c_u8  = c_ubyte
c_u16 = c_ushort
c_u32 = c_uint
c_u64 = c_ulonglong

genzUUID = uuid.UUID('4813ea5f-074e-4be2-a355-a354145c9927')

class CState(IntEnum):
    CDown = 0
    CCFG = 1
    CUp = 2
    CLP = 3
    CDLP = 4

    def __str__(self):
        _c_state = ['C-Down', 'C-CFG', 'C-Up', 'C-LP', 'C-DLP']
        return _c_state[self.value]

class IState(IntEnum):
    IDown = 0
    ICFG = 1
    IUp = 2
    ILP = 3

    def __str__(self):
        _i_state = ['I-Down', 'I-CFG', 'I-Up', 'I-LP']
        return _i_state[self.value]

class GCID():
    def __init__(self, val=None, sid=0, cid=None, str=None):
        if val is not None:
            self.val = val
        elif cid is not None:
            if cid < 0 or cid >= 1<<12:
                raise(ValueError)
            if sid < 0 or sid >= 1<<16:
                raise(ValueError)
            self.val = (sid << 12) | cid
        elif str is not None:
            sid_str, cid_str = str.split(':')
            sid = int(sid_str, 16)
            cid = int(cid_str, 16)
            self.val = (sid << 12) | cid
        else:
            raise(TypeError)
        # Revisit: this doesn't allow INVALID_GCID
        #if self.val < 0 or self.val >= 1<<28:
        #    raise(ValueError)

    @property
    def sid(self):
        return self.val >> 12

    @property
    def cid(self):
        return self.val & 0xfff

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.val == other.val

    def __hash__(self):
        return hash(self.val)

    def __repr__(self):
        return '{:04x}:{:03x}'.format(self.sid, self.cid)

class SpecialField():
    def __init__(self, value, parent, verbosity=0):
        self.value = value
        self.parent = parent
        self.verbosity = verbosity
        super().__init__()

    def __repr__(self):
        return '{}({:#x})'.format(type(self).__name__, self.value)

    def nameToId(self, name):
        return self._map[name]

    def idToName(self, id):
        return self._inverted_map[id]

    def bitField(self, width, bitOffset):
        lowBit = bitOffset % 64
        highBit = lowBit + width - 1
        return (highBit, lowBit)

    def __str__(self):
        r = ''
        bitOffset = 0
        for field in self.field._fields_:
            name = field[0]
            width = field[2]
            highBit, lowBit = self.bitField(width, bitOffset)
            val = getattr(self.field, name)
            if hasattr(self, '_special') and name in self._special:
                try:
                    state = self._special[name][val]
                except IndexError:
                    state = 'Rv'
                if width == 1:
                    r += '{0}{{{2}}}={1} '.format(name, state, lowBit)
                else:
                    r += '{0}{{{2}:{3}}}={1} '.format(name, state, highBit, lowBit)
            else:
                if (self.verbosity < 4 and
                    (name == 'Rv' or width == 1) and val == 0):
                    bitOffset += width
                    continue
                if width == 1:
                    r += '{0}{{{2}}}={1} '.format(name, val, lowBit)
                else:
                    r += '{0}{{{2}:{3}}}={1} '.format(name, val, highBit, lowBit)
            bitOffset += width
        # end for field
        return r

class Opcodes(SpecialField):
    _subfield_name = ['', 'Req', 'Rsp', 'ReqRsp']

    def opCode(self, name):
        return self._map[name]

    def name(self, opc):
        return self._inverted_map[opc]

    def __str__(self):
        r = ''
        if self.value == 0 or not hasattr(self, '_map'):
            return r
        for name, opcode in self._list:
            lowBit = 2 * opcode
            highBit = lowBit + 1
            subField = (self.value >> (2 * opcode)) & 0x3
            if subField != 0:
                r += '{0}{{{2}:{3}}}={1} '.format(
                    name, self._subfield_name[subField],
                    highBit, lowBit)
        return r
