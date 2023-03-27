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
import atomics
import uuid
from enum import Enum, IntEnum, auto

c_u8  = c_ubyte
c_u16 = c_ushort
c_u32 = c_uint
c_u64 = c_ulonglong

genzUUID = uuid.UUID('4813ea5f-074e-4be2-a355-a354145c9927')

DR_IFACE_NONE = 0xffff
MAX_HC = 63

class CState(IntEnum):
    CDown = 0
    CCFG = 1
    CUp = 2
    CLP = 3
    CDLP = 4
    CRv5 = 5
    CRv6 = 6
    CRv7 = 7

    def __str__(self):
        _c_state = ['C-Down', 'C-CFG', 'C-Up', 'C-LP', 'C-DLP']
        return 'Unknown' if self.reserved() else _c_state[self.value]

    def reserved(self):
        return self.value > CState.CDLP

    def to_json(self):
        return str(self)

class IState(IntEnum):
    IDown = 0
    ICFG = 1
    IUp = 2
    ILP = 3

    def __str__(self):
        _i_state = ['I-Down', 'I-CFG', 'I-Up', 'I-LP']
        return _i_state[self.value]

class ProvisionedIStats(IntEnum):
    Common = 0
    CommonReqRsp = 1
    CommonPktRelay = 2
    CommonReqRspPktRelay = 3

class PHYOpStatus(IntEnum):
    PHYDown = 0
    PHYUp = 1
    PHYDownRetrain = 2
    PHYUpLP1 = 3
    PHYUpLP2 = 4
    PHYUpLP3 = 5
    PHYUpLP4 = 6
    PHYLP1 = 7
    PHYLP2 = 8
    PHYLP3 = 9
    PHYLP4 = 10
    PHYRvB = 11
    PHYRvC = 12
    PHYRvD = 13
    PHYRvE = 14
    PHYRvF = 15

    def __str__(self):
        _phy_status = ['Down', 'Up', 'Down-Retrain',
                       'Up-LP1', 'Up-LP2', 'Up-LP3', 'Up-LP4',
                       'LP1', 'LP2', 'LP3', 'LP4',
                       'RvB', 'RvC', 'RvD', 'RvE', 'RvF']
        return 'PHY-' + _phy_status[self.value]

    def up_or_uplp(self):
        return (self.value == PHYOpStatus.PHYUp or
                (self.value >= PHYOpStatus.PHYUpLP1 and
                 self.value <= PHYOpStatus.PHYUpLP4))

class SigTgt(IntEnum):
    TgtNone      = 0
    TgtIntr0     = 0x1
    TgtIntr1     = 0x2
    TgtIntr01    = 0x3
    TgtUEP       = 0x4
    TgtIntr0UEP  = 0x5
    TgtIntr1UEP  = 0x6
    TgtIntr01UEP = 0x7

class UEPTgt(IntEnum):
    TgtPM      = 0
    TgtPFMSFM  = 1
    TgtMgrCID  = 2
    TgtMgrGCID = 3

class ZMMUType(IntEnum):
    ReqZMMU = 0
    RspZMMU = 1

class ErrSeverity(Enum):
    NonCritical = auto(),
    Caution = auto(),
    Critical = auto()

class ReasonClass(Enum):
    NE = auto(),
    TE = auto(),
    NTE = auto(),
    TC = auto(),
    NTC = auto()

class CReset(Enum):
    NoReset = 0
    FullReset = 1
    WarmReset = 2
    WarmNonSwitchReset = 3
    ContentReset = 4

class HostMgrUUID(IntEnum):
    Zero = 0
    Core = 1
    Vdef = 2
    Rv   = 3

class AllOnesData(ValueError):
    '''Custom ValueError for HW returning all-ones data
    '''
    pass

class GCID(int):
    def __new__(cls, val=None, sid=0, cid=None, str=None):
        if val is not None:
            pass
        elif cid is not None:
            if cid < 0 or cid >= 1<<12:
                raise ValueError(f'cid {cid} is out of range')
            if sid < 0 or sid >= 1<<16:
                raise ValueError(f'sid {sid} is out of range')
            val = (sid << 12) | cid
        elif str is not None:
            gcid_str = str.split(':')
            if len(gcid_str) == 1:
                cid = int(gcid_str[0], 16)
            elif len(gcid_str) == 2:
                sid = int(gcid_str[0], 16)
                cid = int(gcid_str[1], 16)
            else:
                raise TypeError(f'invalid GCID str {str}')
            val = (sid << 12) | cid
        else:
            raise(TypeError)
        if not (val == 0xffffffff or (val >= 0 and val < 1<<28)):
            raise ValueError(f'value {val} is out of range')
        return int.__new__(cls, val)

    @property
    def sid(self):
        return self >> 12

    @property
    def cid(self):
        return self & 0xfff

    @property
    def val(self):
        return int(self)

    def __repr__(self):
        return '{:04x}:{:03x}'.format(self.sid, self.cid)

    def to_json(self):
        return str(self)

INVALID_GCID = GCID(val=0xffffffff) # valid GCIDs are only 28 bits

class RKey():
    # Revisit: add a random generator (per rkd), perhaps based on
    # the solutions by orange or aak318, here:
    # https://stackoverflow.com/questions/9755538/how-do-i-create-a-list-of-random-numbers-without-duplicates
    def __init__(self, val=None, rkd=None, os=None, str=None):
        if val is not None:
            self.val = val
        elif rkd is not None and os is not None:
            if os < 0 or os >= 1<<20:
                raise(ValueError)
            if rkd < 0 or rkd >= 1<<12:
                raise(ValueError)
            self.val = (rkd << 20) | os
        elif str is not None:
            rkd_str, os_str = str.split(':')
            rkd = int(rkd_str, 16)
            os = int(os_str, 16)
            self.val = (rkd << 20) | os
        else:
            raise(TypeError)
        if self.val < 0 or self.val >= 1<<32:
            raise(ValueError)

    @property
    def rkd(self):
        return self.val >> 20

    @rkd.setter
    def rkd(self, val):
        if val < 0 or val > 1<<12:
            raise(ValueError)
        self.val = (val << 12) | self.os

    @property
    def os(self):
        return self.val & 0xfffff

    @os.setter
    def os(self, val):
        if val < 0 or val > 1<<20:
            raise(ValueError)
        self.val = (self.rkd << 20) | (val & 0xfffff)

    def __eq__(self, other):
        if type(self) != type(other):
            return NotImplemented
        return self.val == other.val

    def __repr__(self):
        return '{:03x}:{:05x}'.format(self.rkd, self.os)

class SpecialField():
    def __init__(self, value, parent=None, verbosity=0, check=False):
        self.value = value
        self.parent = parent
        self.verbosity = verbosity
        super().__init__(val=value)
        if check:
            sz = sizeof(self)
            if sz <= 8: # Revisit: sz > 8, like CErrorSigTgt
                ones = (1 << (sz * 8)) - 1
                if value == ones:
                    raise AllOnesData(f'{repr(self)}: all-ones data')

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
                    r += '{0}{{{2}}}={1}({3}) '.format(name, state, lowBit, val)
                else:
                    r += '{0}{{{2}:{3}}}={1}({4}) '.format(name, state, highBit, lowBit, val)
            else:
                if (self.verbosity < 4 and
                    (name[:2] == 'Rv' or width == 1) and val == 0):
                    bitOffset += width
                    continue
                if width == 1:
                    r += '{0}{{{2}}}={1} '.format(name, val, lowBit)
                else:
                    r += '{0}{{{2}:{3}}}={1} '.format(name, val, highBit, lowBit)
            bitOffset += width
        # end for field
        return r

class Opcodes(SpecialField, Union):
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


class RefCount():
    def __init__(self, sz: tuple = (1, 1)):
        self._array = [[atomics.atomic(width=4, atype=atomics.UINT)
                        for col in range(sz[1])] for row in range(sz[0])]

    def inc(self, row=0, col=0) -> bool:
        '''
        Increment the refcount. Returns True if the refcount was 0 (now 1).
        '''
        return (self._array[row][col].fetch_inc() == 0)

    def dec(self, row=0, col=0):
        '''
        Decrement the refcount. Returns True if the refcount was 1 (now 0).
        '''
        return (self._array[row][col].fetch_dec() == 1)

    def value(self, row=0, col=0):
        '''
        Return the refcount.
        '''
        return self._array[row][col].load()

    def __getitem__(self, row):
        return self._array[row]
