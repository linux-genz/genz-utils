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

import textwrap
import re
import shutil
import crcmod
from pdb import set_trace
from uuid import UUID
from .genz_common import *

cols, lines = shutil.get_terminal_size()

# match Reserved field names
rv_re = re.compile('^R\d+$')

# Based on Gen-Z revision 1.1 final

reqPgPteUUID = UUID(hex='d2b57c49a98c42e68118f75aadbeb69c')
rspPgPteUUID = UUID(hex='acb0e6c1053d4afcb29de003bc234e13')

MaxPktPayload = 256
MaxMsgSize = (1 << 11) * MaxPktPayload  # 512KiB

# Revisit: this should be auto-generated from the v1.1.xml file

cclass_name = [ 'reserved',    'memory_p2p64', 'memory',      'int_switch',
                'exp_switch',  'fab_switch',   'processor',   'processor',
                'accelerator', 'accelerator',  'accelerator', 'accelerator',
                'io',          'io',           'io',          'io',
                'block',       'block',        'tr',          'multiclass',
                'bridge',      'bridge',       'compliance',  'lph' ]

cclass_name_to_classes = {
    'memory': (0x1, 0x2),
    'mem':    (0x1, 0x2),
    'switch': (0x3, 0x4, 0x5),
    'sw':     (0x3, 0x4, 0x5),
    'int_switch': (0x3,),
    'exp_switch': (0x4,),
    'fab_switch': (0x5,),
    'processor': (0x6, 0x7),
    'proc':      (0x6, 0x7),
    'accelerator': (0x8, 0x9, 0xA, 0xB),
    'acc':         (0x8, 0x9, 0xA, 0xB),
    'io': (0xC, 0xD, 0xE, 0xF),
    'block': (0x10, 0x11),
    'tr': (0x12,),
    'multiclass': (0x13,),
    'multi':      (0x13,),
    'bridge': (0x14, 0x15),
    'br':     (0x14, 0x15),
    'compliance': (0x16,),
    'lph': (0x17,),
}

def reason(esVal: int) -> int:
    es = ProtocolErrorES(esVal)
    rsn = es.ReasonCode
    # Revisit: multicast needs to use a different mapping
    bit = reasonData[rsn][2]
    return bit

def mechFW(esVal:int) -> int:
    es = MechFWErrorES(esVal)
    return es.BitK

def mediaMaint(esVal:int) -> int:
    es = MediaMaintEventES(esVal)
    return 18 if es.Secondary else 16

def mediaOvr(esVal:int) -> int:
    es = MediaOverrideEventES(esVal)
    return 19 if es.Secondary else 17

def dlpLpEntry(esVal:int) -> int:
    es = DlpLpEventES(esVal)
    return 23 if es.LP else 11

def dlpLpExit(esVal:int) -> int:
    es = DlpLpEventES(esVal)
    return 24 if es.LP else 3

def auxPwr(esVal:int) -> int:
    es = AuxPwrEventES(esVal)
    return 12 if es.Off else 11

def lowPwr(esVal:int) -> int:
    es = LowPwrEventES(esVal)
    return 7 + es.BitK

#                     Name                         bit (num, None, or func)
eventData = { 0x00: ('RecovProtocolErr',           reason),
              0x01: ('UnrecovProtocolErr',         reason),
              0x02: ('PossibleMaliciousPkt',       5),
              0x03: ('IfaceErr',                   None),
              0x04: ('CompContainment',            0),
              0x07: ('FullIfaceReset',             0),
              0x08: ('WarmIfaceReset',             1),
              0x09: ('NewPeerComp',                2),
              0x0a: ('UnableToCommunicate',        1),
              0x0b: ('ExcessiveRNRNAK',            2),
              0x0d: ('FatalMediaContainment',      12),
              0x0e: ('PrimaryMediaLog',            None),
              0x0f: ('SecondaryMediaLog',          None),
              0x10: ('InvalidCompImage',           6),
              0x11: ('CompThermShutdown',          4),
              0x12: ('PeerCompC-DLP/C-LPExit',     dlpLpExit),
              0x13: ('PowerFault',                 10),
              0x14: ('AuxPower',                   auxPwr),
              0x15: ('CompFWErr',                  mechFW),
              0x16: ('CompLowPower',               lowPwr),
              0x17: ('PeerCompC-DLP/C-LPEntry',    dlpLpEntry),
              0x18: ('EmergencyPowerReduction',    12),
              0x19: ('CompPowerOffTransition',     14),
              0x1a: ('CompPowerRestoration',       15),
              0x1b: ('IfacePerfDegradation',       5),
              0x1d: ('MediaMaintRequired',         mediaMaint),
              0x1e: ('MediaMaintOverride',         mediaOvr),
              0x1f: ('ExceededTransientErrThresh', 3),
              0x20: ('VdefC-Event',                None), # Revisit
              0x21: ('VdefI-Event',                None), # Revisit
              0x22: ('NonFatalInternalCompErr',    1),
              0x23: ('FatalInternalCompErr',       2),
              0x24: ('CompThermPerfThrottle',      20),
              0x25: ('CompThermThrottleRestore',   21),
              0x28: ('Mechanical',                 mechFW),
              0x29: ('ExcessiveE2ERetry',          None), # Revisit
              0x2a: ('BISTFailure',                0),
              0x2b: ('P2PNonTransient',            22),
              0xf0: ('VdefC-Error0',               None), # Revisit
              0xf1: ('VdefC-Error1',               None), # Revisit
              0xf2: ('VdefC-Error2',               None), # Revisit
              0xf3: ('VdefC-Error3',               None), # Revisit
              0xf4: ('Vdef0',                      None), # Revisit
              0xf5: ('Vdef1',                      None), # Revisit
              0xf6: ('Vdef2',                      None), # Revisit
              0xf7: ('Vdef3',                      None), # Revisit
              0xf8: ('Vdef4',                      None), # Revisit
              0xf9: ('Vdef5',                      None), # Revisit
              0xfa: ('Vdef6',                      None), # Revisit
              0xfb: ('Vdef7',                      None), # Revisit
              0xfc: ('Vdef8',                      None), # Revisit
              0xfd: ('Vdef9',                      None), # Revisit
              0xfe: ('VdefA',                      None), # Revisit
              0xff: ('VdefB',                      None), # Revisit
}

eventName = { key: val[0] for key, val in eventData.items() }
eventType = { val[0]: key for key, val in eventData.items() }

def ceil_div(num: int, denom: int) -> int:
    return -(-num // denom)

class ACREQRSP(IntEnum):
    NoAccess             = 0x0
    RKeyRequired         = 0x1
    Rv                   = 0x2
    FullAccess           = 0x3

class PTGranUnit(IntEnum):
    GranUnitNS           = 0
    GranUnitPS           = 1

class Reason(IntEnum):
    NoError              = 0x00
    NE                   = 0x00
    UnexpectedPkt        = 0x01
    UE                   = 0x01
    UnsupportedReq       = 0x02
    UR                   = 0x02
    MalformedPkt         = 0x03
    MP                   = 0x03
    PktExeNonFatal       = 0x04
    EXEnf                = 0x04
    PktExeFatal          = 0x05
    EXEfatal             = 0x05
    InvAccKey            = 0x06
    AEakey               = 0x06
    InvAccPerm           = 0x07
    AEperm               = 0x07
    CompContain          = 0x08
    PktExeAbort          = 0x09
    EXEabort             = 0x09
    RespNotReady0        = 0x0a
    RNR0                 = 0x0a
    RespNotReady1        = 0x0b
    RNR1                 = 0x0b
    DataCorrWarn         = 0x0c
    DCE                  = 0x0c
    DataUncorrErr        = 0x0d
    DUC                  = 0x0d
    PoisonDataDet        = 0x0e
    PDdet                = 0x0e
    PoisonDataFail       = 0x0f
    PDfail               = 0x0f
    InProgressSE         = 0x10
    SE                   = 0x10
    FatalMediaContain    = 0x11
    EmergPwrReduct       = 0x12
    InsufficientSpace    = 0x13
    AbortTransition      = 0x14
    UnsupServAddrRes     = 0x15
    USAR                 = 0x15
    InsufficientRespRes  = 0x16
    IRR                  = 0x16
    ExclusiveGranted     = 0x17
    UnableGrantExclShare = 0x18
    WakeFailure          = 0x19
    SODTransErr          = 0x1a
    InvalidCapabilities  = 0x1b
    AEcap                = 0x1b
    PrimBackupOp         = 0x1c
    CompPwrOffTrans      = 0x1d
    NoErrorWriteMSG      = 0x1e
    NEwritemsg           = 0x1e
    MediaEndurance       = 0x1f
    NoErrorHomeAgent     = 0x20
    NEha                 = 0x20
    PersFlushUpdateFail  = 0x21
    MaxReqPktRetrans     = 0x22
    T10DIPI              = 0x23
    BufferAEADFail       = 0x24
    SecSessionFail       = 0x25
    SecurityErr          = 0x26
    SECE                 = 0x26
    NoErrorEnqueue       = 0x27
    NEenq                = 0x27
    SecEncryptKeyFail    = 0x28
    NoErrorWriteMSGCompl = 0x29
    NEwritemsgcompl      = 0x29
    RespAccReq           = 0x2a
    RAR                  = 0x2a

    def __repr__(self):
        return '<{}.{}: {:#x}>'.format(
            self.__class__.__name__, self._name_, self._value_)

#              Reason  Name                   Class            Bit
reasonData = { 0x00: ('NoError',              ReasonClass.NE,  None),
               0x01: ('UnexpPkt',             ReasonClass.NTE, 7),
               0x02: ('UnsupReq',             ReasonClass.NTE, 3),
               0x03: ('MalformedPkt',         ReasonClass.NTE, 4),
               0x04: ('PktExeNonFatal',       ReasonClass.TE,  5),
               0x05: ('PktExeFatal',          ReasonClass.NTE, 6),
               0x06: ('InvAKey',              ReasonClass.NTE, 8),
               0x07: ('InvAccPerm',           ReasonClass.NTE, 9),
               0x08: ('CompContain',          ReasonClass.NTC, 0),
               0x09: ('PktExeAbort',          ReasonClass.NTE, 10),
               0x0a: ('RNR0',                 ReasonClass.NE,  None),
               0x0b: ('RNR1',                 ReasonClass.NE,  None),
               0x0c: ('DataCorr',             ReasonClass.TC,  5),
               0x0d: ('DataUncorr',           ReasonClass.NTC, 5),
               0x0e: ('PoisonDet',            ReasonClass.NTC, 5),
               0x0f: ('PoisonFail',           ReasonClass.NTE, 5),
               0x10: ('InProgressSE',         ReasonClass.TC,  5),
               0x11: ('FatalMediaContain',    ReasonClass.NTE, 6),
               0x12: ('EmergPwrReduct',       ReasonClass.TC,  6),
               0x13: ('InsufSpace',           ReasonClass.NTC, 21),
               0x14: ('AbortTransition',      ReasonClass.NTC, None),
               0x15: ('UnsupServAddrRes',     ReasonClass.NTE, 22),
               0x16: ('InsufRespRes',         ReasonClass.TC,  23),
               0x17: ('ExclusiveGranted',     ReasonClass.NE,  None),
               0x18: ('UnableGrantExclShare', ReasonClass.NE,  None),
               0x19: ('WakeFailure',          ReasonClass.NE,  None),
               0x1a: ('SODTransErr',          ReasonClass.NE,  None),
               0x1b: ('InvalidCapabilities',  ReasonClass.NTE, 5),
               0x1c: ('PrimBackupOp',         ReasonClass.TC,  5),
               0x1d: ('CompPwrOffTrans',      ReasonClass.NTC, 6),
               0x1e: ('NoErrorWriteMSG',      ReasonClass.NE,  None),
               0x1f: ('MediaEndurance',       ReasonClass.NTC, 6),
               0x20: ('NoErrorHomeAgent',     ReasonClass.NE,  None),
               0x21: ('PersFlushUpdateFail',  ReasonClass.NTC, 25),
               0x22: ('MaxReqPktRetrans',     ReasonClass.NTE, 11),
               0x23: ('T10DIPI',              ReasonClass.NTE, 6),
               0x24: ('BufferAEADFail',       ReasonClass.NTE, 27),
               0x25: ('SecSessionFail',       ReasonClass.NTE, 28),
               0x26: ('SecurityErr',          ReasonClass.NTE, 13),
               0x27: ('NoErrorEnqueue',       ReasonClass.NE,  None),
               0x28: ('SecEncryptKeyFail',    ReasonClass.NTE, 29),
               0x29: ('NoErrorWriteMSGCompl', ReasonClass.NE,  None),
               0x2a: ('RAR',                  ReasonClass.NE,  None),
}

class QD():
    # Revisit: _map[7] should be "> 87.5%"
    _map = [ 0.0, 12.5, 25.0, 50.0, 62.5, 75.0, 87.5, 100.0 ]

    def __init__(self, percent=None, val=0):
        self.update(percent, val)

    def decode(self, val=None) -> float:
        if val is None:
            val = self.val
        return self._map[val]

    def encode(self, percent=None) -> int:
        if percent is None:
            percent = self.percent
        for i, num in enumerate(self._map):
            if percent <= num:
                return i
        raise ValueError('percent must be 0.0 - 100.0')

    def update(self, percent=None, val=0):
        if percent is not None:
            self.percent = percent
            self.val = self.encode(percent)
        else: # use val
            self.val = val
            self.percent = self.decode(val)

    def __repr__(self):
        return f'QD({self.percent}%)'

class CStatus(SpecialField, Union):
    class CStatusFields(Structure):
        _fields_ = [('CState',              c_u64,  3),
                    ('UEStatus',            c_u64,  1),
                    ('NonFatalError',       c_u64,  1),
                    ('FatalError',          c_u64,  1),
                    ('NTError',             c_u64,  1),
                    ('BISTFailure',         c_u64,  1),
                    ('ThermStatus',         c_u64,  2),
                    ('Containment',         c_u64,  1),
                    ('EmergPwr',            c_u64,  1),
                    ('PwrOffTransCmpl',     c_u64,  1),
                    ('ThermThrottled',      c_u64,  1),
                    ('ThermThrotRestor',    c_u64,  1),
                    ('CannotExePersFlush',  c_u64,  1),
                    ('HwInitValid',         c_u64,  1),
                    ('RefreshCompCmpl',     c_u64,  1),
                    ('OpError',             c_u64,  1),
                    ('MaxCtrlNop',          c_u64,  1),
                    ('Rv',                  c_u64, 44),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', CStatusFields), ('val', c_u64)]
    _c_state = ['C-Down', 'C-CFG', 'C-Up', 'C-LP', 'C-DLP',
                'C-Rv5', 'C-Rv6', 'C-Rv7']
    _therm   = ['Nominal', 'Caution', 'Exceeded', 'Shutdown']
    _special = {'CState': _c_state, 'ThermStatus': _therm}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class CControl(SpecialField, Union):
    class CControlFields(Structure):
        _fields_ = [('ComponentEnb',                c_u64,  1),
                    ('ComponentReset',              c_u64,  3),
                    ('HaltUERT',                    c_u64,  1),
                    ('TransitionCUp',               c_u64,  1),
                    ('TransitionCLP',               c_u64,  1),
                    ('TransitionCDLP',              c_u64,  1),
                    ('TriggerEmergPwrRed',          c_u64,  1),
                    ('ExitEmergPwrRed',             c_u64,  1),
                    ('TransitionCompPwrOff',        c_u64,  1),
                    ('UpperThermLimPerfThrotEnb',   c_u64,  1),
                    ('CautionThermLimPerfThrotEnb', c_u64,  1),
                    ('LPDRspZMMUBypass',            c_u64,  1),
                    ('RefreshCompConfig',           c_u64,  1),
                    ('TransmitLocalCtlNoOp',        c_u64,  1),
                    ('TransmitGlobalCtlNoOp',       c_u64,  1),
                    ('TransmitLocalCtlAEAD',        c_u64,  1),
                    ('TransmitGlobalCtlAEAD',       c_u64,  1),
                    ('Rv',                          c_u64, 45),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', CControlFields), ('val', c_u64)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class CAP1(SpecialField, Union):
    class CAP1Fields(Structure):
        _fields_ = [('MaxPkt',              c_u64,  3),
                    ('NoSnoopSup',          c_u64,  1),
                    ('ContentResetSup',     c_u64,  1),
                    ('BISTSup',             c_u64,  1),
                    ('ContainmentSup',      c_u64,  1),
                    ('AddrInterp',          c_u64,  1),
                    ('NextHdrSup',          c_u64,  1),
                    ('RvZ',                 c_u64,  1),
                    ('PrecisionTimeSup',    c_u64,  1),
                    ('DataSpace',           c_u64,  3),
                    ('CachedCtlSpace',      c_u64,  1),
                    ('InbandMgmtSup',       c_u64,  1),
                    ('OOBMgmtSup',          c_u64,  1),
                    ('PrimMgrSup',          c_u64,  1),
                    ('FabricMgrSup',        c_u64,  1),
                    ('PwrMgrSup',           c_u64,  1),
                    ('AutoCStateSup',       c_u64,  1),
                    ('VdefPwrMgmtSup',      c_u64,  1),
                    ('EmergPwrReductSup',   c_u64,  1),
                    ('ConfigPostEmergPwr',  c_u64,  1),
                    ('EmergPwrRelaySup',    c_u64,  1),
                    ('CStatePwrCtlSup',     c_u64,  1),
                    ('PwrDisableSup',       c_u64,  1),
                    ('PwrScale',            c_u64,  3),
                    ('AuxPwrScale',         c_u64,  3),
                    ('MCTPSup',             c_u64,  1),
                    ('CoreLatScale',        c_u64,  2),
                    ('SubnetSup',           c_u64,  1),
                    ('Rv37',                c_u64,  2),
                    ('NIRTSup',             c_u64,  1),
                    ('Rv40',                c_u64,  1),
                    ('EmergPwrSigSup',      c_u64,  1),
                    ('CtlTimerUnit',        c_u64,  2),
                    ('TimerUnit',           c_u64,  4),
                    ('PwrDisSigSup',        c_u64,  1),
                    ('RspZMMUIntrTransSup', c_u64,  1),
                    ('SharedEmergSigSup',   c_u64,  1),
                    ('MgmtCLPSup',          c_u64,  1),
                    ('MgmtCDLPSup',         c_u64,  1),
                    ('FPSSup',              c_u64,  1),
                    ('PCOFPSSup',           c_u64,  1),
                    ('CompAuthSup',         c_u64,  1),
                    ('MgmtServSup',         c_u64,  1),
                    ('MaxCID',              c_u64,  3),
                    ('P2PNxtHdrSup',        c_u64,  1),
                    ('P2PAEADSup',          c_u64,  1),
                    ('ExplicitAEADSup',     c_u64,  1),
                    ('LoopbackSup',         c_u64,  1),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', CAP1Fields), ('val', c_u64)]
    _max_pkt    = ['256B']
    _addr       = ['ZeroBased', 'NonZeroBased']
    _data       = ['None', 'ByteAddr', 'BlockAddr', 'CompMedia', 'NonMedia']
    _pwr_scale  = ['1.0', '0.1', '0.01', '0.001',
                   '0.0001', '0.00001', '0.000001', '0.0000001']
    _lat_scale  = ['us', 'ns', 'ps']
    _ctl_tu     = ['1us', '10us', '100us', '1ms']
    _tu         = ['1ns', '10ns', '100ns', '1us', '10us', '100us', '1ms',
                   '10ms', '100ms', '1s']
    _max_cid    = ['CID0', 'CID0-1', 'CID0-2', 'CID0-3']
    _special = {'MaxPkt': _max_pkt, 'AddrInterp': _addr, 'DataSpace': _data,
                'PwrScale': _pwr_scale, 'AuxPwrScale': _pwr_scale,
                'CoreLatScale': _lat_scale, 'CtlTimerUnit': _ctl_tu,
                'TimerUnit': _tu, 'MaxCID': _max_cid
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class CAP1Control(SpecialField, Union):
    class CAP1ControlFields(Structure):
        _fields_ = [('MaxPkt',                     c_u64,  3),
                    ('NoSnoopCtl',                 c_u64,  1),
                    ('BISTCtl',                    c_u64,  1),
                    ('ManagerType',                c_u64,  1),
                    ('PrimaryMgrRole',             c_u64,  1),
                    ('PrimaryFabMgrRole',          c_u64,  1),
                    ('SecondaryFabMgrRole',        c_u64,  1),
                    ('PwrMgrEnb',                  c_u64,  2),
                    ('PrimaryMgrTransition',       c_u64,  1),
                    ('FabricMgrTransition',        c_u64,  1),
                    ('NextHdrEnb',                 c_u64,  1),
                    ('Rv14',                       c_u64,  1),
                    ('NextHdrPrecTimeEnb',         c_u64,  1),
                    ('InbandMgmtDisable',          c_u64,  1),
                    ('OOBMgmtDisable',             c_u64,  1),
                    ('AutoCStateEnb',              c_u64,  1),
                    ('VdefPwrMgmtEnb',             c_u64,  1),
                    ('MaxPwrCtl',                  c_u64,  3),
                    ('EmergPwrReductEnb',          c_u64,  1),
                    ('NotifyPeerCStateEnb',        c_u64,  1),
                    ('Rv25',                       c_u64,  1),
                    ('CStatePwrCtlEnb',            c_u64,  1),
                    ('LowestAutoCState',           c_u64,  3),
                    ('InitiateAllStatsSnap',       c_u64,  1),
                    ('InitiateAllIfaceStatsSnap',  c_u64,  1),
                    ('Rv32',                       c_u64,  2),
                    ('MCTPEnb',                    c_u64,  1),
                    ('MetaRWHdrEnb',               c_u64,  1),
                    ('HostMgrMGRUUIDEnb',          c_u64,  2),
                    ('MGRUUIDEnb',                 c_u64,  1),
                    ('LoopbackEnb',                c_u64,  1),
                    ('Rv40',                       c_u64, 16),
                    ('SWMgmt0',                    c_u64,  1),
                    ('SWMgmt1',                    c_u64,  1),
                    ('SWMgmt2',                    c_u64,  1),
                    ('SWMgmt3',                    c_u64,  1),
                    ('SWMgmt4',                    c_u64,  1),
                    ('SWMgmt5',                    c_u64,  1),
                    ('SWMgmt6',                    c_u64,  1),
                    ('SWMgmt7',                    c_u64,  1),
        ]

    _anonymous_ = ('field',)
    _fields_     = [('field', CAP1ControlFields), ('val', c_u64)]
    _max_pkt     = ['256B']
    _mgr_type    = ['Primary', 'Fabric']
    _pwr_mgr     = ['Disabled', 'EnabledCID', 'EnabledCIDSID']
    _pwr_ctl     = ['LPWR', 'NPWR', 'HPWR', 'MaxMech']
    _auto_cstate = ['C-Up', 'C-LP', 'C-DLP']
    _mgr_uuid    = ['Zero', 'Core', 'Vdef']
    _special = {'MaxPkt': _max_pkt, 'ManagerType': _mgr_type,
                'MaxPwrCtl': _pwr_ctl, 'LowestAutoCState': _auto_cstate,
                'HostMgrMGRUUIDEnb': _mgr_uuid
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class CAP2(SpecialField, Union):
    class CAP2Fields(Structure):
        _fields_ = [('RKeySup',                    c_u64,  2),
                    ('RspMemInterleaveSup',        c_u64,  1),
                    ('ReqMemInterleaveSup',        c_u64,  1),
                    ('Rv4',                        c_u64,  1),
                    ('WrMSGEmbeddedRdSup',         c_u64,  1),
                    ('PoisonGranSup',              c_u64,  4),
                    ('HostLPDType1Type2Sup',       c_u64,  1),
                    ('HostLPDType0Sup',            c_u64,  1),
                    ('PerfMarkerSup',              c_u64,  3),
                    ('MaxPerfRecords',             c_u64,  5),
                    ('MetaRdWrSup',                c_u64,  3),
                    ('HostLPDType3Sup',            c_u64,  1),
                    ('HostLPDType4Sup',            c_u64,  1),
                    ('BufReqT10DIFSup',            c_u64,  1),
                    ('BufReqT10PISup',             c_u64,  1),
                    ('DIPIBlockSzSup',             c_u64,  8),
                    ('Rv35',                       c_u64,  1),
                    ('WrMSGRecvTagFilterSup',      c_u64,  1),
                    ('WrMSGRecvTagPostingSup',     c_u64,  1),
                    ('WrMSGEnqDeqSharedQSup',      c_u64,  1),
                    ('Rv39',                       c_u64,  2),
                    ('PersFlushPageSup',           c_u64,  1),
                    ('RspLPDType5Sup',             c_u64,  1),
                    ('ReqLPDType5Sup',             c_u64,  1),
                    ('EnqueueEmbeddedRdSup',       c_u64,  1),
                    ('NoOpCoreInitiationSup',      c_u64,  1),
                    ('Rv',                         c_u64, 18),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', CAP2Fields), ('val', c_u64)]
    _rkey       = ['Unsup', 'Req', 'Rsp', 'ReqRsp']
    _poison     = ['Unsup', '16B', '32B', '64B', '128B', '256B', '512B',
                   '1KiB', '2KiB', '4KiB']
    _marker     = ['Unsup', 'Type0', 'Type1']
    _meta       = ['Unsup', 'CUUID', 'Vdef', 'ServiceUUID']
    _di_pi_sz   = ['Unsup', '512B', '4KiB', '512B|4KiB']
    _special = {'RKeySup': _rkey, 'PoisonGranSup': _poison,
                'PerfMarkerSup': _marker,
                'MetaRdWrSup': _meta, 'DIPIBlockSzSup': _di_pi_sz
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class CAP2Control(SpecialField, Union):
    class CAP2ControlFields(Structure):
        _fields_ = [('Rv0',                        c_u64,  1),
                    ('PMCIDValid',                 c_u64,  1),
                    ('PFMCIDValid',                c_u64,  1),
                    ('SFMCIDValid',                c_u64,  1),
                    ('PFMSIDValid',                c_u64,  1),
                    ('SFMSIDValid',                c_u64,  1),
                    ('RspMemInterleaveEnb',        c_u64,  1),
                    ('PerfLogRecordEnb',           c_u64,  1),
                    ('ClearPerfMarkerLog',         c_u64,  1),
                    ('HostLPDType1_2Enb',          c_u64,  1),
                    ('HostLPDType3Enb',            c_u64,  1),
                    ('HostLPDType0Enb',            c_u64,  1),
                    ('HostLPDType4Enb',            c_u64,  1),
                    ('Rv13',                       c_u64,  2),
                    ('DIPIBlockSize',              c_u64,  3),
                    ('BufReqT10DIFPIEnb',          c_u64,  1),
                    ('Rv19',                       c_u64,  3),
                    ('RSPLPDType5Enb',             c_u64,  1),
                    ('REQLPDType5Enb',             c_u64,  1),
                    ('EnqueueEmbeddedRdEnb',       c_u64,  1),
                    ('Rv',                         c_u64, 39),
        ]

    _anonymous_ = ('field',)
    _fields_     = [('field', CAP2ControlFields), ('val', c_u64)]
    _di_pi_sz    = ['512B', '4KiB']
    _special = {'DIPIBlockSize': _di_pi_sz
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class DestTableCAP1(SpecialField, Union):
    class DestTableCAP1Fields(Structure):
        _fields_ = [('EISup',                       c_u32,  1),
                    ('WildcardSSDTSup',             c_u32,  1),
                    ('WildcardMSDTSup',             c_u32,  1),
                    ('RITSSDTSup',                  c_u32,  1),
                    ('Rv',                          c_u32, 28),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', DestTableCAP1Fields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class DestTableControl(SpecialField, Union):
    class DestTableControlFields(Structure):
        _fields_ = [('PeerAuthEnb',                 c_u32,  1),
                    ('RITSSDTEnb',                  c_u32,  1),
                    ('Rv',                          c_u32, 30),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', DestTableControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class EControl(SpecialField, Union):
    class EControlFields(Structure):
        _fields_ = [('Rv',                          c_u16,  3),
                    ('TrigCompContain',             c_u16,  1),
                    ('ErrLogLevel',                 c_u16,  3),
                    ('ErrUEPTgt',                   c_u16,  2),
                    ('EventUEPTgt',                 c_u16,  2),
                    ('MechUEPTgt',                  c_u16,  2),
                    ('MediaUEPTgt',                 c_u16,  2),
                    ('ErrFaultInjEnb',              c_u16,  1),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', EControlFields), ('val', c_u16)]
    _err_log    = ['Crit', 'Crit+Caution', 'Crit+Caution+NonCrit']
    _err_tgt    = ['TgtPM', 'TgtPFMSFM', 'TgtErrMgrCID',   'TgtErrMgrGCID']
    _event_tgt  = ['TgtPM', 'TgtPFMSFM', 'TgtEventMgrCID', 'TgtEventMgrGCID']
    _mech_tgt   = ['TgtPM', 'TgtPFMSFM', 'TgtMechMgrCID',  'TgtMechMgrGCID']
    _media_tgt  = ['TgtPM', 'TgtPFMSFM', 'TgtMediaMgrCID', 'TgtMediaMgrGCID']
    _special = {'ErrLogLevel': _err_log, 'ErrUEPTgt': _err_tgt,
                'EventUEPTgt': _event_tgt, 'MechUEPTgt': _mech_tgt,
                'MediaUEPTgt': _media_tgt,
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class EControl2(SpecialField, Union):
    class EControl2Fields(Structure):
        _fields_ = [('PwrUEPTgt',                   c_u32,  2),
                    ('Rv',                          c_u32, 30),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', EControl2Fields), ('val', c_u32)]
    _pwr_tgt    = ['TgtPM', 'TgtPFMSFM', 'TgtPwrMgrCID',   'TgtPwrMgrGCID']
    _special = {'PwrUEPTgt': _pwr_tgt,
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class EStatus(SpecialField, Union):
    class EStatusFields(Structure):
        _fields_ = [('LoggingFailed',               c_u16,  1), # RW1CS
                    ('CritLogEntryConsumed',        c_u16,  1), # RW1CS
                    ('Rv',                          c_u16, 14),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', EStatusFields), ('val', c_u16)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class ErrSigCAP1(SpecialField, Union):
    class ErrSigCAP1Fields(Structure):
        _fields_ = [('SigIntrAddr0Sup',             c_u16,  1),
                    ('SigIntrAddr1Sup',             c_u16,  1),
                    ('CEventDetectSup',             c_u16,  1),
                    ('CEventInjSup',                c_u16,  1),
                    ('IEventDetectSup',             c_u16,  1),
                    ('IEventInjSup',                c_u16,  1),
                    ('VdefErrLogUUID',              c_u16,  2),
                    ('Rv',                          c_u16,  8),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', ErrSigCAP1Fields), ('val', c_u16)]
    _vdef_err   = ['Unsup', 'CUUID', 'VdefUUID']
    _special = {'VdefErrLogUUID': _vdef_err,
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class ErrSigCAP1Control(SpecialField, Union):
    class ErrSigCAP1ControlFields(Structure):
        _fields_ = [('SigIntr0Enb',                 c_u16,  1),
                    ('SigIntr1Enb',                 c_u16,  1),
                    ('CEventInjEnb',                c_u16,  1),
                    ('IEventInjEnb',                c_u16,  1),
                    ('Rv',                          c_u16, 12),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', ErrSigCAP1ControlFields), ('val', c_u16)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class IntCompErrorES(SpecialField, Union):
    class IntCompErrorESFields(Structure):
        _fields_ = [('InvalidIndex',               c_u32,  1),
                    ('LogEntryIndex',              c_u32, 16),
                    ('Rv',                         c_u32, 15),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IntCompErrorESFields), ('val', c_u32)]

class ProtocolErrorES(SpecialField, Union):
    class ProtocolErrorESFields(Structure):
        _fields_ = [('ReasonCode',                 c_u32,  6),
                    ('Rv',                         c_u32, 26),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', ProtocolErrorESFields), ('val', c_u32)]

class MechFWErrorES(SpecialField, Union):
    class MechFWErrorESFields(Structure):
        _fields_ = [('BitK',                       c_u32,  5),
                    ('Rv',                         c_u32, 27),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', MechFWErrorESFields), ('val', c_u32)]

class MediaMaintEventES(SpecialField, Union):
    class MediaMaintEventESFields(Structure):
        _fields_ = [('Secondary',                  c_u32,  1),
                    ('NumberUsec',                 c_u32, 17),
                    ('Rv',                         c_u32, 14),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', MediaMaintEventESFields), ('val', c_u32)]

class MediaOverrideEventES(SpecialField, Union):
    class MediaOverrideEventESFields(Structure):
        _fields_ = [('Secondary',                  c_u32,  1),
                    ('Rv',                         c_u32, 31),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', MediaOverrideEventESFields), ('val', c_u32)]

class DlpLpEventES(SpecialField, Union):
    class DlpLpEventESFields(Structure):
        _fields_ = [('LP',                         c_u32,  1),
                    ('Rv',                         c_u32, 31),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', DlpLpEventESFields), ('val', c_u32)]

class AuxPwrEventES(SpecialField, Union):
    class AuxPwrEventESFields(Structure):
        _fields_ = [('Off',                        c_u32,  1),
                    ('Rv',                         c_u32, 31),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', AuxPwrEventESFields), ('val', c_u32)]

class LowPwrEventES(SpecialField, Union):
    class LowPwrEventESFields(Structure):
        _fields_ = [('BitK',                       c_u32,  3),
                    ('Rv',                         c_u32, 29),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', LowPwrEventESFields), ('val', c_u32)]

class OpcodeEventES(SpecialField, Union):
    class OpcodeEventESFields(Structure):
        _fields_ = [('OpClass',                    c_u32,  5),
                    ('OpCode',                     c_u32,  5),
                    ('Rv',                         c_u32, 22),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', OpcodeEventESFields), ('val', c_u32)]

# Base class for CError{Status,Detect,Trig,FaultInj}
class CError(SpecialField, Union):
    class CErrorFields(Structure):
        _fields_ = [('CompContain',                 c_u64,  1),
                    ('NonFatalCompErr',             c_u64,  1),
                    ('FatalCompErr',                c_u64,  1),
                    ('E2EUnicastUR',                c_u64,  1),
                    ('E2EUnicastMP',                c_u64,  1),
                    ('E2EUnicastEXENonFatal',       c_u64,  1),
                    ('E2EUnicastEXEFatal',          c_u64,  1),
                    ('E2EUnicastUP',                c_u64,  1),
                    ('AEInvAKey',                   c_u64,  1),
                    ('AEInvAccPerm',                c_u64,  1),
                    ('E2EUnicastEXEAbort',          c_u64,  1),
                    ('MaxReqPktRetrans',            c_u64,  1),
                    ('FatalMediaErrContain',        c_u64,  1),
                    ('SecurityErr',                 c_u64,  1),
                    ('E2EMulticastUR',              c_u64,  1),
                    ('E2EMulticastMP',              c_u64,  1),
                    ('E2EMulticastEXENonFatal',     c_u64,  1),
                    ('E2EMulticastEXEFatal',        c_u64,  1),
                    ('E2EMulticastUP',              c_u64,  1),
                    ('SODUP',                       c_u64,  1),
                    ('UnexpCompPwrLoss',            c_u64,  1),
                    ('InsufficientSpace',           c_u64,  1),
                    ('UnsupServiceAddr',            c_u64,  1),
                    ('InsufficientRspRes',          c_u64,  1),
                    ('WakeFailure',                 c_u64,  1),
                    ('PersFlushFailure',            c_u64,  1),
                    ('IfaceContainOE',              c_u64,  1),
                    ('BufAEADFailure',              c_u64,  1),
                    ('SecSessionFailure',           c_u64,  1),
                    ('SecEncryptKeyFailure',        c_u64,  1),
                    ('Rv',                          c_u64, 26),
                    ('Vdef',                        c_u64,  8),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', CErrorFields), ('val', c_u64)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

    @staticmethod
    def uep_map(key, esVal):
        # Revisit: bit 26 IfaceContainOE has no UEP Event code
        val = eventData[key][1]
        if val is None or isinstance(val, int):
            return val
        return val(esVal)

class CErrorStatus(CError):
    pass # All bits: RW1CS

class CErrorDetect(CError):
    pass # All bits: RW

class CErrorTrig(CError):
    pass # Bit 0: WO, All other bits: RW

class CErrorFaultInj(CError):
    pass # Bits 0 & 12: RsvdZ, All other bits: WO

class CErrorSigTgt(SpecialField, Union):
    class CErrorSigTgtFields(Structure):
        _fields_ = [('CompContain',                 c_u64,  3), # All bits RW
                    ('NonFatalCompErr',             c_u64,  3),
                    ('FatalCompErr',                c_u64,  3),
                    ('E2EUnicastUR',                c_u64,  3),
                    ('E2EUnicastMP',                c_u64,  3),
                    ('E2EUnicastEXENonFatal',       c_u64,  3),
                    ('E2EUnicastEXEFatal',          c_u64,  3),
                    ('E2EUnicastUP',                c_u64,  3),
                    ('AEInvAKey',                   c_u64,  3),
                    ('AEInvAccPerm',                c_u64,  3),
                    ('E2EUnicastEXEAbort',          c_u64,  3),
                    ('MaxReqPktRetrans',            c_u64,  3),
                    ('FatalMediaErrContain',        c_u64,  3),
                    ('SecurityErr',                 c_u64,  3),
                    ('E2EMulticastUR',              c_u64,  3),
                    ('E2EMulticastMP',              c_u64,  3),
                    ('E2EMulticastEXENonFatal',     c_u64,  3),
                    ('E2EMulticastEXEFatal',        c_u64,  3),
                    ('E2EMulticastUP',              c_u64,  3),
                    ('SODUP',                       c_u64,  3),
                    ('UnexpCompPwrLoss',            c_u64,  3),
                    ('InsufficientSpacel',          c_u64,  1),
                    ('InsufficientSpaceh',          c_u64,  2),
                    ('UnsupServiceAddr',            c_u64,  3),
                    ('InsufficientRspRes',          c_u64,  3),
                    ('WakeFailure',                 c_u64,  3),
                    ('PersFlushFailure',            c_u64,  3),
                    ('IfaceContainOE',              c_u64,  3),
                    ('BufAEADFailure',              c_u64,  3),
                    ('SecSessionFailure',           c_u64,  3),
                    ('SecEncryptKeyFailure',        c_u64,  3),
                    ('RvM',                         c_u64, 38),
                    ('RvH',                         c_u64, 40),
                    ('Vdef0',                       c_u64,  3),
                    ('Vdef1',                       c_u64,  3),
                    ('Vdef2',                       c_u64,  3),
                    ('Vdef3',                       c_u64,  3),
                    ('Vdef4',                       c_u64,  3),
                    ('Vdef5',                       c_u64,  3),
                    ('Vdef6',                       c_u64,  3),
                    ('Vdef7',                       c_u64,  3),
        ]

        @property
        def InsufficientSpace(self):
            return (self.InsufficientSpaceh << 1) | self.InsufficientSpacel

        @InsufficientSpace.setter
        def InsufficientSpace(self, val):
            if val < 0 or val > 7:
                raise(ValueError)
            self.InsufficientSpaceh = (val >> 1) & 0x3
            self.InsufficientSpacel = val & 0x1

    _anonymous_ = ('field',)
    _fields_    = [('field', CErrorSigTgtFields), ('val', c_u64 * 3)]

    def __init__(self, value, parent, verbosity=0):
        arr_val = (c_u64 * 3)(*value)
        super().__init__(arr_val, parent, verbosity=verbosity)
        self.val = arr_val

# Base class for CEvent{Status,Detect,Inj}
class CEvent(SpecialField, Union):
    class CEventFields(Structure):
        _fields_ = [('BISTFailure',                 c_u64,  1),
                    ('UnableToCommAuthDest',        c_u64,  1),
                    ('ExcessiveRNRNAK',             c_u64,  1),
                    ('PeerCompCDLPExit',            c_u64,  1), # Rv in Inj
                    ('CompThermShutdown',           c_u64,  1),
                    ('PossibleMaliciousPkt',        c_u64,  1),
                    ('InvalidCompImage',            c_u64,  1),
                    ('CLPEntry',                    c_u64,  1),
                    ('CLPExit',                     c_u64,  1),
                    ('CDLPEntry',                   c_u64,  1),
                    ('CDLPExit',                    c_u64,  1),
                    ('PeerCompCDLPEntry',           c_u64,  1),
                    ('EmergencyPowerReduction',     c_u64,  1),
                    ('Rv13',                        c_u64,  1),
                    ('CompPowerOffTransition',      c_u64,  1),
                    ('CompPowerRestoration',        c_u64,  1),
                    ('PriMediaMaintRequired',       c_u64,  1),
                    ('PriMediaMaintOverride',       c_u64,  1),
                    ('SecMediaMaintRequired',       c_u64,  1),
                    ('SecMediaMaintOverride',       c_u64,  1),
                    ('CompThermPerfThrottle',       c_u64,  1),
                    ('CompThermThrottleRestore',    c_u64,  1),
                    ('P2PNonTransient',             c_u64,  1),
                    ('PeerCompCLPEntry',            c_u64,  1),
                    ('PeerCompCLPExit',             c_u64,  1),
                    ('Rv',                          c_u64, 35),
                    ('Vdef',                        c_u64,  4),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', CEventFields), ('val', c_u64)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class CEventStatus(CEvent):
    pass # All bits: RW1CS

class CEventDetect(CEvent):
    pass # All bits: RW

class CEventInj(CEvent):
    pass # Bit 3: RsvdZ, All other bits: WO

class CEventSigTgt(SpecialField, Union):
    class CEventSigTgtFields(Structure):
        _fields_ = [('BISTFailure',                 c_u64,  3), # All bits RW
                    ('UnableToCommAuthDest',        c_u64,  3),
                    ('ExcessiveRNRNAK',             c_u64,  3),
                    ('PeerCompCDLPExit',            c_u64,  3),
                    ('CompThermShutdown',           c_u64,  3),
                    ('PossibleMaliciousPkt',        c_u64,  3),
                    ('InvalidCompImage',            c_u64,  3),
                    ('CLPEntry',                    c_u64,  3),
                    ('CLPExit',                     c_u64,  3),
                    ('CDLPEntry',                   c_u64,  3),
                    ('CDLPExit',                    c_u64,  3),
                    ('PeerCompCDLPEntry',           c_u64,  3),
                    ('EmergencyPowerReduction',     c_u64,  3),
                    ('Rv',                          c_u64,  3),
                    ('CompPowerOffTransition',      c_u64,  3),
                    ('CompPowerRestoration',        c_u64,  3),
                    ('PriMediaMaintRequired',       c_u64,  3),
                    ('PriMediaMaintOverride',       c_u64,  3),
                    ('SecMediaMaintRequired',       c_u64,  3),
                    ('SecMediaMaintOverride',       c_u64,  3),
                    ('CompThermPerfThrottle',       c_u64,  3),
                    ('CompThermThrottleRestorel',   c_u64,  1),
                    ('CompThermThrottleRestoreh',   c_u64,  2),
                    ('P2PNonTransient',             c_u64,  3),
                    ('PeerCompCLPEntry',            c_u64,  3),
                    ('PeerCompCLPExit',             c_u64,  3),
                    ('RvM',                         c_u64, 53),
                    ('RvH',                         c_u64, 52),
                    ('Vdef0',                       c_u64,  3),
                    ('Vdef1',                       c_u64,  3),
                    ('Vdef2',                       c_u64,  3),
                    ('Vdef3',                       c_u64,  3),
        ]

        @property
        def CompThermThrottleRestore(self):
            return ((self.CompThermThrottleRestoreh << 1) |
                    self.CompThermThrottleRestorel)

        @CompThermThrottleRestore.setter
        def CompThermThrottleRestore(self, val):
            if val < 0 or val > 7:
                raise(ValueError)
            self.CompThermThrottleRestoreh = (val >> 1) & 0x3
            self.CompThermThrottleRestorel = val & 0x1

    _anonymous_ = ('field',)
    _fields_    = [('field', CEventSigTgtFields), ('val', c_u64 * 3)]

    def __init__(self, value, parent, verbosity=0):
        arr_val = (c_u64 * 3)(*value)
        super().__init__(arr_val, parent, verbosity=verbosity)
        self.val = arr_val

# Base class for IEvent{Status,Detect,Inj}
class IEvent(SpecialField, Union):
    class IEventFields(Structure):
        _fields_ = [('FullIfaceReset',              c_u64,  1),
                    ('WarmIfaceReset',              c_u64,  1),
                    ('NewPeerComp',                 c_u64,  1),
                    ('ExceededTransientErrThresh',  c_u64,  1),
                    ('Rv4',                         c_u64,  1),
                    ('IfacePerfDegradation',        c_u64,  1),
                    ('Rv',                          c_u64, 54),
                    ('Vdef',                        c_u64,  4),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IEventFields), ('val', c_u64)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

    @staticmethod
    def uep_map(key):
        return eventData[key][1]

class IEventStatus(IEvent):
    pass

class IEventDetect(IEvent):
    pass

class IEventInj(IEvent):
    pass

class IEventSigTgt(SpecialField, Union):
    class IEventSigTgtFields(Structure):
        _fields_ = [('FullIfaceReset',              c_u64,  3), # All bits RW
                    ('WarmIfaceReset',              c_u64,  3),
                    ('NewPeerComp',                 c_u64,  3),
                    ('ExceededTransientErrThresh',  c_u64,  3),
                    ('Rv',                          c_u64,  3),
                    ('IfacePerfDegradation',        c_u64,  3),
                    ('RvL',                         c_u64, 46),
                    ('RvM',                         c_u64, 64),
                    ('RvH',                         c_u64, 52),
                    ('Vdef0',                       c_u64,  3),
                    ('Vdef1',                       c_u64,  3),
                    ('Vdef2',                       c_u64,  3),
                    ('Vdef3',                       c_u64,  3),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IEventSigTgtFields), ('val', c_u64 * 3)]

    def __init__(self, value, parent, verbosity=0):
        arr_val = (c_u64 * 3)(*value)
        super().__init__(arr_val, parent, verbosity=verbosity)
        self.val = arr_val

class OpCodeSetCAP1(SpecialField, Union):
    class CAP1Fields(Structure):
        _fields_ = [('P2PVdefSup',          c_u64,  1),
                    ('VDO1Sup',             c_u64,  1),
                    ('VDO2Sup',             c_u64,  1),
                    ('VDO3Sup',             c_u64,  1),
                    ('VDO4Sup',             c_u64,  1),
                    ('VDO5Sup',             c_u64,  1),
                    ('VDO6Sup',             c_u64,  1),
                    ('VDO7Sup',             c_u64,  1),
                    ('VDO8Sup',             c_u64,  1),
                    ('AtomicEndian',        c_u64,  2),
                    ('ProtocolVersion',     c_u64,  4),
                    ('InterruptRole',       c_u64,  2),
                    ('MultiOpCodeSetSup',   c_u64,  1),
                    ('PerDestOpCodeSetSup', c_u64,  1),
                    ('LDM1ReadRspMetaSup',  c_u64,  1),
                    ('UniformOpClassSup',   c_u64,  1),
                    ('Rv',                  c_u64, 43),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', CAP1Fields), ('val', c_u64)]
    _endian     = ['Unsup', 'Little', 'Big', 'LittleBig']
    _prot       = ['V1']
    _role       = ['Unsup', 'Req', 'Rsp', 'ReqRsp']
    _special = {'AtomicEndian': _endian, 'ProtocolVersion': _prot,
                'InterruptRole': _role,
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class OpCodeSetCAP1Control(SpecialField, Union):
    class CAP1ControlFields(Structure):
        _fields_ = [('EnbCacheLineSz',             c_u32,  3),
                    ('IfaceUniformOpClass',        c_u32,  2),
                    ('Rv',                         c_u32, 27),
        ]

    _anonymous_ = ('field',)
    _fields_     = [('field', CAP1ControlFields), ('val', c_u32)]
    _cache_sz    = ['Disabled', '32B', '64B', '128B', '256B']
    _uniform     = ['None', 'Explicit', 'P2P64', 'P2PVdef']
    _special = {'EnbCacheLineSz': _cache_sz, 'IfaceUniformOpClass': _uniform,
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class OpCodeSetIDControl1(SpecialField, Union):
    class Control1Fields(Structure):
        _fields_ = [('OpCodeSetEnb',               c_u16,  1),
                    ('Rv',                         c_u16, 15),
        ]

    _anonymous_ = ('field',)
    _fields_     = [('field', Control1Fields), ('val', c_u16)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class IStatus(SpecialField, Union):
    class IStatusFields(Structure):
        _fields_ = [('IState',                     c_u32,  3),
                    ('FullIfaceReset',             c_u32,  1),
                    ('WarmIfaceReset',             c_u32,  1),
                    ('LinkRFCStatus',              c_u32,  1),
                    ('PeerLinkRFCReady',           c_u32,  1),
                    ('PeerLinkRFCTTC',             c_u32,  1),
                    ('ExceededTransientErrThresh', c_u32,  1),
                    ('LUpToLLPTransitionFailed',   c_u32,  1),
                    ('LinkCTLCompleted',           c_u32,  1),
                    ('LinkCTLComplStatus',         c_u32,  5),
                    ('IfaceContainment',           c_u32,  1),
                    ('IfaceCompContainment',       c_u32,  1),
                    ('PeerIfaceIncompat',          c_u32,  1),
                    ('PeerNonceDetected',          c_u32,  1),
                    ('LLRStatus',                  c_u32,  1),
                    ('Rv',                         c_u32, 11),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IStatusFields), ('val', c_u32)]
    _i_state    = ['I-Down', 'I-CFG', 'I-Up', 'I-LP']
    _ctl_stat   = ['InProgress', 'ACKReceived', 'UnsupLinkCTL',
                   'UnableToCompleteLinkCTLReq', 'UnsupLLR', 'UnauthLinkCTL',
                   'UnsupPHYStateReq', 'UnableToCompleteLUpLLP']
    _special = {'IState': _i_state, 'LinkCTLComplStatus': _ctl_stat}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

    @property
    def istate(self):
        try:
            ist = self._i_state[self.field.IState]
        except IndexError:
            ist = 'Unknown'
        return ist

class IControl(SpecialField, Union):
    class IControlFields(Structure):
        _fields_ = [('IfaceEnb',                   c_u32,  1),
                    ('FullIfaceReset',             c_u32,  1), # WO
                    ('WarmIfaceReset',             c_u32,  1), # WO
                    ('LinkRFCDisable',             c_u32,  1),
                    ('PeerCReset',                 c_u32,  1), # WO
                    ('PeerCUpTransition',          c_u32,  1), # WO
                    ('PeerAttr1Req',               c_u32,  1), # WO
                    ('IfaceAKeyValidationEnb',     c_u32,  1),
                    ('LUpTransition',              c_u32,  1), # WO
                    ('AutoStop',                   c_u32,  1),
                    ('PathTimeReq',                c_u32,  1), # WO
                    ('ForcePLARetraining',         c_u32,  1), # WO
                    ('LLPTransition',              c_u32,  3), # WO
                    ('LUpLPTransition',            c_u32,  3), # WO
                    ('PeerSetAttrReq',             c_u32,  1), # WO
                    ('IngressDREnb',               c_u32,  1),
                    ('P2PNextHdrEnb',              c_u32,  1),
                    ('IfaceContainment',           c_u32,  1), # WO
                    ('PeerNonceReq',               c_u32,  1), # WO
                    ('P2PAEADEnb',                 c_u32,  1),
                    ('P2PAEADEKeyUpdateEnb',       c_u32,  1),
                    ('Rv',                         c_u32,  7),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class ICAP1(SpecialField, Union):
    class ICAP1Fields(Structure):
        _fields_ = [('IfaceContainmentSup',      c_u32,  1),
                    ('IfaceErrFieldsSup',        c_u32,  1),
                    ('IfaceErrLogSup',           c_u32,  1),
                    ('TransientErrThreshSup',    c_u32,  1),
                    ('IErrFaultInjSup',          c_u32,  1),
                    ('LPRTWildcardSup',          c_u32,  1),
                    ('MPRTWildcardSup',          c_u32,  1),
                    ('IfaceLoopbackSup',         c_u32,  1),
                    ('ImplicitFCSup',            c_u32,  1),
                    ('ExplicitFCSup',            c_u32,  1),
                    ('Rv10',                     c_u32,  1),
                    ('P2P64Sup',                 c_u32,  1),
                    ('P2PVdefSup',               c_u32,  1),
                    ('Rv13',                     c_u32,  1),
                    ('ExplicitOpClassSup',       c_u32,  1),
                    ('DROpClassSup',             c_u32,  1),
                    ('PktRelayAKeyFields',       c_u32,  1),
                    ('IfaceAKeyValidationSup',   c_u32,  1),
                    ('LLRSup',                   c_u32,  1),
                    ('TRIfaceSup',               c_u32,  1),
                    ('SrcCIDPktValidationSup',   c_u32,  1),
                    ('SrcSIDPktValidationSup',   c_u32,  1),
                    ('AdaptiveFCCreditSup',      c_u32,  1),
                    ('PCOCommSup',               c_u32,  1),
                    ('Rv24',                     c_u32,  1),
                    ('AggIfaceSup',              c_u32,  1),
                    ('AggIfaceRole',             c_u32,  1),
                    ('PeerNonceValidationSup',   c_u32,  1),
                    ('P2PStandaloneAckRequired', c_u32,  1),
                    ('IfaceGroupSup',            c_u32,  1),
                    ('IfaceGroupSingleOpClass',  c_u32,  1),
                    ('P2PBackupSup',             c_u32,  1),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', ICAP1Fields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class ICAP1Control(SpecialField, Union):
    class ICAP1ControlFields(Structure):
        _fields_ = [('Rv0',                              c_u32,  1),
                    ('TransientErrThreshEnb',            c_u32,  1),
                    ('IErrFaultInjEnb',                  c_u32,  1),
                    ('WildcardPktRelayEnb',              c_u32,  1),
                    ('IfaceLoopbackEnb',                 c_u32,  1),
                    ('FlowControlType',                  c_u32,  1),
                    ('OpClassSelect',                    c_u32,  3),
                    ('CtlOpClassPktFiltEnb',             c_u32,  1),
                    ('UnreliableCtlWriteMSGPktFiltEnb',  c_u32,  1),
                    ('LPRTEnb',                          c_u32,  1),
                    ('MPRTEnb',                          c_u32,  1),
                    ('Rv13',                             c_u32,  1),
                    ('LLRCRCTrigger',                    c_u32,  1),
                    ('SrcCIDPktValidationEnb',           c_u32,  1),
                    ('SrcSIDPktValidationEnb',           c_u32,  1),
                    ('PeerCIDConfigured',                c_u32,  1),
                    ('PeerSIDConfigured',                c_u32,  1),
                    ('AdaptiveFCCreditEnb',              c_u32,  1),
                    ('OmitP2PStandaloneAck',             c_u32,  1),
                    ('IfaceCompContainmentEnb',          c_u32,  1),
                    ('PeerNonceValidationEnb',           c_u32,  1),
                    ('PCOCommEnb',                       c_u32,  1),
                    ('LLREnb',                           c_u32,  1),
                    ('AggIfaceCtl',                      c_u32,  2),
                    ('TRCIDValid',                       c_u32,  1),
                    ('PrecisionTimeEnb',                 c_u32,  1),
                    ('Rv',                               c_u32,  3),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', ICAP1ControlFields), ('val', c_u32)]

    _opclass    = ['NotConfig', 'Explicit', 'P2P64', 'P2PVdef',
                   'Rv', 'Rv', 'Rv', 'Incompatible']
    _agg_iface  = ['Independent', 'NAI', 'SAI', 'Rv']
    _special = {'OpClassSelect': _opclass, 'AggIfaceCtl': _agg_iface}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class ICAP2(SpecialField, Union):
    class ICAP2Fields(Structure):
        _fields_ = [('TEHistSize',               c_u32,  3),
                    ('Rv',                       c_u32, 29),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', ICAP2Fields), ('val', c_u32)]

    _te_hist_sz = ['256', '512', '1024']
    _special = {'TEHistSize': _te_hist_sz}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class ICAP2Control(SpecialField, Union):
    class ICAP2ControlFields(Structure):
        _fields_ = [('SWMgmtI0',                         c_u32,  1),
                    ('SWMgmtI1',                         c_u32,  1),
                    ('Rv',                               c_u32, 30),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', ICAP2ControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

# Base class for IError{Status,Detect,Trig,FaultInj}
class IError(SpecialField, Union):
    class IErrorFields(Structure):
        _fields_ = [('ExcessivePHYRetraining',           c_u16,  1),
                    ('NonTransientLinkErr',              c_u16,  1),
                    ('IfaceContainment',                 c_u16,  1), # Rv in Inj
                    ('IfaceAKEYViolation',               c_u16,  1),
                    ('IfaceFCFwdProgressViolation',      c_u16,  1),
                    ('UnexpectedPHYFailure',             c_u16,  1),
                    ('P2PSECE',                          c_u16,  1),
                    ('IfaceAE',                          c_u16,  1),
                    ('SwitchPktRelayFailure',            c_u16,  1),
                    ('Rv',                               c_u16,  7),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IErrorFields), ('val', c_u16)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class IErrorStatus(IError):
    pass # All bits: RW1CS

class IErrorDetect(IError):
    pass # All bits: RW

class IErrorTrig(IError):
    pass # All bits: RW

class IErrorFaultInj(IError):
    pass # Bit 2: RsvdZ, All other bits: WO

class IErrorES(SpecialField, Union):
    class IErrorESFields(Structure):
        _fields_ = [('BitK',                       c_u32,  4),
                    ('Containment',                c_u32,  1),
                    ('RootCauseAvail',             c_u32,  1),
                    ('RootCause',                  c_u32,  7),
                    ('Rv',                         c_u32, 19),
                    ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IErrorESFields), ('val', c_u32)]

    # Revisit: names here duplicate class IErrorFields names
    iErrorData = { 0: ('ExcessivePHYRetraining',      ErrSeverity.Caution),
                   1: ('NonTransientLinkErr',         ErrSeverity.Critical),
                   2: ('IfaceContainment',            ErrSeverity.Critical),
                   3: ('IfaceAKEYViolation',          ErrSeverity.Critical),
                   4: ('IfaceFCFwdProgressViolation', ErrSeverity.Caution),
                   5: ('UnexpectedPHYFailure',        ErrSeverity.Critical),
                   6: ('P2PSECE',                     ErrSeverity.Critical),
                   7: ('IfaceAE',                     ErrSeverity.Critical),
                   8: ('SwitchPktRelayFailure',       ErrSeverity.Caution),
                  }

    def __init__(self, value, parent=None, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

    @property
    def errName(self):
        return self.iErrorData[self.field.BitK][0]

    @property
    def errSeverity(self):
        return self.iErrorData[self.field.BitK][1]

class IErrorSigTgt(SpecialField, Union):
    class IErrorSigTgtFields(Structure):
        _fields_ = [('ExcessivePHYRetraining',           c_u16,  3),
                    ('NonTransientLinkErr',              c_u16,  3),
                    ('IfaceContainment',                 c_u16,  3),
                    ('IfaceAKEYViolation',               c_u16,  3),
                    ('IfaceFCFwdProgressViolation',      c_u16,  3),
                    ('UnexpectedPHYFailurel',            c_u16,  1),
                    ('UnexpectedPHYFailureh',            c_u16,  2),
                    ('P2PSECE',                          c_u16,  3),
                    ('IfaceAE',                          c_u16,  3),
                    ('SwitchPktRelayFailure',            c_u16,  3),
                    ('RvM',                              c_u16,  5),
                    ('RvH',                              c_u16, 16),
        ]

        @property
        def UnexpectedPHYFailure(self):
            return (self.UnexpectedPHYFailureh << 1) | self.UnexpectedPHYFailurel

        @UnexpectedPHYFailure.setter
        def UnexpectedPHYFailure(self, val):
            if val < 0 or val > 7:
                raise(ValueError)
            self.UnexpectedPHYFailureh = (val >> 1) & 0x3
            self.UnexpectedPHYFailurel = val & 0x1

    _anonymous_ = ('field',)
    _fields_    = [('field', IErrorSigTgtFields), ('val', c_u16 * 3)]

    def __init__(self, value, parent, verbosity=0, check=False):
        v_list = [((value >> (i*16)) & 0xffff) for i in range(3)]
        arr_val = (c_u16 * 3)(*v_list)
        super().__init__(arr_val, parent, verbosity=verbosity)
        if check:
            if value == 0xffffffffffff:
                raise AllOnesData(f'{type(self).__name__}: all-ones data')
        self.val = arr_val

class PeerState(SpecialField, Union):
    class PeerStateFields(Structure):
        _fields_ = [('PeerCState',                       c_u32,  3),
                    ('PeerMgrType',                      c_u32,  1),
                    ('PeerCIDValid',                     c_u32,  1),
                    ('PeerSIDValid',                     c_u32,  1),
                    ('PeerIfaceIDValid',                 c_u32,  1),
                    ('Rv7',                              c_u32,  1),
                    ('PeerIfaceP2P64Sup',                c_u32,  1),
                    ('PeerIfaceP2PVdefSup',              c_u32,  1),
                    ('PeerIfaceExplicitSup',             c_u32,  1),
                    ('PeerMultipleCIDConf',              c_u32,  1),
                    ('PeerOOBMgmtDisabled',              c_u32,  1),
                    ('PeerHomeAgentSup',                 c_u32,  1),
                    ('PeerCachingAgentSup',              c_u32,  1),
                    ('PeerIfaceFCSup',                   c_u32,  2),
                    ('PeerBaseCClassValid',              c_u32,  1),
                    ('PeerInbandMgmtDisabled',           c_u32,  1),
                    ('PeerUniformOpClassSup',            c_u32,  1),
                    ('PeerLLRSup',                       c_u32,  1),
                    ('PeerUniformOpClassSelected',       c_u32,  2),
                    ('PeerP2PAEADSup',                   c_u32,  1),
                    ('PeerP2PNextHdrSup',                c_u32,  1),
                    ('PeerDROpClassSup',                 c_u32,  1),
                    ('Rv',                               c_u32,  6),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', PeerStateFields), ('val', c_u32)]

    _c_state    = ['C-Down', 'C-CFG', 'C-Up', 'C-LP', 'C-DLP']
    _mgr_type   = ['Primary', 'Fabric']
    _opclass    = ['NotConfig', 'Explicit', 'P2P64', 'P2PVdef']
    _fc_sup     = ['Implicit', 'Explicit', 'Implicit+Explicit']
    _special = {'PeerCState': _c_state, 'PeerMgrType': _mgr_type,
                'PeerIfaceFCSup': _fc_sup,
                'PeerUniformOpClassSelected': _opclass}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class LinkCTLControl(SpecialField, Union):
    class LinkCTLControlFields(Structure):
        _fields_ = [('Rv0',                              c_u32,  2),
                    ('XmitPeerCUpEnb',                   c_u32,  1),
                    ('RecvPeerCUpEnb',                   c_u32,  1),
                    ('XmitPeerCResetEnb',                c_u32,  1),
                    ('RecvPeerCResetEnb',                c_u32,  1),
                    ('XmitPeerEnterLinkUpLPEnb',         c_u32,  1),
                    ('RecvPeerEnterLinkUpLPEnb',         c_u32,  1),
                    ('XmitPeerEnterLinkLPEnb',           c_u32,  1),
                    ('RecvPeerEnterLinkLPEnb',           c_u32,  1),
                    ('XmitLinkResetEnb',                 c_u32,  1),
                    ('RecvLinkResetEnb',                 c_u32,  1),
                    ('Rv',                               c_u32, 20),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', LinkCTLControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class PHYStatus(SpecialField, Union):
    class PHYStatusFields(Structure):
        _fields_ = [('PHYLayerOpStatus',         c_u32,  4),
                    ('PrevPHYLayerOpStatus',     c_u32,  4),
                    ('PHYLayerTrainingStatus',   c_u32,  2),
                    ('PHYLayerRetrainingStatus', c_u32,  2),
                    ('PHYTxLinkWidthReduced',    c_u32,  1),
                    ('PHYRxLinkWidthReduced',    c_u32,  1),
                    ('PHYTxErrDetected',         c_u32,  1),
                    ('PHYRxErrDetected',         c_u32,  1),
                    ('Rv',                       c_u32, 16),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', PHYStatusFields), ('val', c_u32)]
    _phy_op_status = ['PHY-Down', 'PHY-Up', 'PHY-Down-Retrain',
                      'PHY-Up-LP1', 'PHY-Up-LP2', 'PHY-Up-LP3', 'PHY-Up-LP4',
                      'PHY-LP1', 'PHY-LP2', 'PHY-LP3', 'PHY-LP4',]
    _phy_train_status = ['NoTraining', 'TrainingSuccess', 'TrainingFailed']
    _phy_retrain_status = ['NoRetraining', 'RetrainingSuccess', 'RetrainingFailed']
    _special = {'PHYLayerOpStatus': _phy_op_status,
                'PrevPHYLayerOpStatus': _phy_op_status,
                'PHYLayerTrainingStatus': _phy_train_status,
                'PHYLayerRetrainingStatus': _phy_retrain_status,
    }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class PHYType(SpecialField, Union):
    class PHYTypeFields(Structure):
        _fields_ = [('PHYType',             c_u8,   8)]

    _anonymous_ = ('field',)
    _fields_    = [('field', PHYTypeFields), ('val', c_u8)]
    _phy_type = ['25GFabric', '25GLocal', 'PCIe', '50GFabric', '50GLocal',
                 'NullPHY']
    _special = {'PHYType': _phy_type}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class IStatStatus(SpecialField, Union):
    class IStatStatusFields(Structure):
        _fields_ = [('IStatsResetStatus',          c_u8,  1), # RW1C
                    ('SnapshotStatus',             c_u8,  1), # RW1C
                    ('Rv',                         c_u8,  6),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IStatStatusFields), ('val', c_u8)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class IStatControl(SpecialField, Union):
    class IStatControlFields(Structure):
        _fields_ = [('StatsEnb',                   c_u8,  1), # RW
                    ('StatsReset',                 c_u8,  1), # WO
                    ('InitiateStatsSnapshot',      c_u8,  1), # WO
                    ('Rv',                         c_u8,  5),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IStatControlFields), ('val', c_u8)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class IStatCAP1(SpecialField, Union):
    class IStatCAP1Fields(Structure):
        _fields_ = [('ProvisionedStatsFields',   c_u16,  2),
                    ('MaxSnapshotTime',          c_u16,  2),
                    ('Rv',                       c_u16, 12),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', IStatCAP1Fields), ('val', c_u16)]
    _provisioned = ['Common', 'CommonReqRsp', 'CommonPktRelay', 'CommonReqRspPktRelay']
    _snap_time = ['1ms', '10ms', '100ms', '1s']
    _special = {'ProvisionedStatsFields': _provisioned,
                'MaxSnapshotTime': _snap_time,
                }

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class PACAP1(SpecialField, Union):
    class PACAP1Fields(Structure):
        _fields_ = [('PAIdxSz',             c_u32,  2),
                    ('PAEntrySz',           c_u32,  2),
                    ('Rv4',                 c_u32,  2),
                    ('WildcardAKeySup',     c_u32,  1),
                    ('WildcardPASup',       c_u32,  1),
                    ('Rv8',                 c_u32,  1),
                    ('WildcardACREQSup',    c_u32,  1),
                    ('WildcardACRSPSup',    c_u32,  1),
                    ('Rv',                  c_u32, 21),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', PACAP1Fields), ('val', c_u32)]
    _pa_idx_sz = ['0bits', '8bits', '16bits']
    _pa_ent_sz = ['16bits']
    _special = {'PAIdxSz': _pa_idx_sz, 'PAEntrySz': _pa_ent_sz}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class PACAP1Control(SpecialField, Union):
    class PACAP1ControlFields(Structure):
        _fields_ = [('AKeyEnb',                          c_u32,  1),
                    ('Rv',                               c_u32, 31),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', PACAP1ControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class CPageSz(SpecialField, Union):
    class CPageSzFields(Structure):
        _fields_ = [('CPageSz',             c_u8,   4)]

    _anonymous_ = ('field',)
    _fields_    = [('field', CPageSzFields), ('val', c_u8)]
    _cpage_sz = ['4KiB', '64KiB', '1MiB', '32MiB']
    _special = {'CPageSz': _cpage_sz}
    _ps = [12, 16, 20, 25]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

    def ps(self):
        return None if self.val >= len(self._ps) else self._ps[self.val]

class CAccessCAP1(SpecialField, Union):
    class CAccessCAP1Fields(Structure):
        _fields_ = [('LACSup',                 c_u8,  1),
                    ('P2PACSup',               c_u8,  1),
                    ('Rv',                     c_u8,  2),
        ]


    _anonymous_ = ('field',)
    _fields_    = [('field', CAccessCAP1Fields), ('val', c_u8)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class CAccessCTL(SpecialField, Union):
    class CAccessCTLFields(Structure):
        _fields_ = [('RKeyEnb',                c_u8,  1),
                    ('ResetTables',            c_u8,  1),
                    ('LACEnb',                 c_u8,  1),
                    ('P2PACEnb',               c_u8,  1),
                    ('Rv',                     c_u8,  4),
        ]


    _anonymous_ = ('field',)
    _fields_    = [('field', CAccessCTLFields), ('val', c_u8)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class PGZMMUCAP1(SpecialField, Union):
    class PGZMMUCAP1Fields(Structure):
        _fields_ = [('ZMMUType',                 c_u32,  1),
                    ('LPDRspNoBypassSup',        c_u32,  1),
                    ('LPDRspBypassSup',          c_u32,  1),
                    ('LPDRspBypassCtlSup',       c_u32,  1),
                    ('Rv',                       c_u32, 28),
        ]


    _anonymous_ = ('field',)
    _fields_    = [('field', PGZMMUCAP1Fields), ('val', c_u32)]
    _type    = ['ReqZMMU', 'RspZMMU']
    _special = {'ZMMUType': _type}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class PTZMMUCAP1(SpecialField, Union):
    class PTZMMUCAP1Fields(Structure):
        _fields_ = [('ZMMUType',                 c_u32,  1),
                    ('LPDRspNoBypassSup',        c_u32,  1),
                    ('LPDRspBypassSup',          c_u32,  1),
                    ('LPDRspBypassCtlSup',       c_u32,  1),
                    ('Rv',                       c_u32, 28),
        ]


    _anonymous_ = ('field',)
    _fields_    = [('field', PTZMMUCAP1Fields), ('val', c_u32)]
    _type    = ['ReqZMMU', 'RspZMMU']
    _special = {'ZMMUType': _type}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class PTEATTRl(SpecialField, Union):
    class ReqPTEATTRlFields(Structure):
        _fields_ = [('GdSz',                     c_u64,  5),
                    ('Rv5',                      c_u64,  5),
                    ('PASIDSz',                  c_u64,  5),
                    ('PFMESup',                  c_u64,  1),
                    ('WPESup',                   c_u64,  1),
                    ('RKeySup',                  c_u64,  1),
                    ('NSESup',                   c_u64,  1),
                    ('LPESup',                   c_u64,  1),
                    ('CESup',                    c_u64,  1),
                    ('STDRCSup',                 c_u64,  1),
                    ('CCESup',                   c_u64,  1),
                    ('WriteMode0Sup',            c_u64,  1),
                    ('WriteMode1Sup',            c_u64,  1),
                    ('WriteMode2Sup',            c_u64,  1),
                    ('WriteMode3Sup',            c_u64,  1),
                    ('WriteMode4Sup',            c_u64,  1),
                    ('WriteMode5Sup',            c_u64,  1),
                    ('WriteMode6Sup',            c_u64,  1),
                    ('WriteMode7Sup',            c_u64,  1),
                    ('PECSup',                   c_u64,  1),
                    ('MCSup',                    c_u64,  1),
                    ('TCSz',                     c_u64,  2),
                    ('TRIdxSup',                 c_u64,  1),
                    ('COSup',                    c_u64,  1),
                    ('Rv',                       c_u64, 27),
        ]

    class RspPTEATTRlFields(Structure):
        _fields_ = [('RkMgrSIDSz',               c_u64,  5),
                    ('Rv5',                      c_u64,  5),
                    ('PASIDSz',                  c_u64,  5),
                    ('WPESup',                   c_u64,  1),
                    ('RKeySup',                  c_u64,  1),
                    ('LPESup',                   c_u64,  1),
                    ('CESup',                    c_u64,  1),
                    ('CCESup',                   c_u64,  1),
                    ('PASup',                    c_u64,  1),
                    ('RkMgrCIDSup',              c_u64,  1),
                    ('ASz',                      c_u64,  7),
                    ('WSz',                      c_u64,  7),
                    ('IESup',                    c_u64,  1),
                    ('PFERSup',                  c_u64,  1),
                    ('Rv',                       c_u64, 26),
        ]

    _fields_    = [('rsp', RspPTEATTRlFields),
                   ('req', ReqPTEATTRlFields), ('val', c_u64)]
    _tc_sz   = ['None', '4bits']
    _special = {'TCSz': _tc_sz}

    def __init__(self, value, parent, verbosity=0, check=False):
        # Revisit: PG vs PT
        cap1 = PGZMMUCAP1(parent.PGZMMUCAP1, parent)
        self.zmmuType = cap1.field.ZMMUType
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

    @property
    def field(self):
        return self.rsp if self.zmmuType == 1 else self.req

class PTCAP1(SpecialField, Union):
    class PTCAP1Fields(Structure):
        _fields_ = [('PTReqSup',               c_u16,  1),
                    ('PTRspSup',               c_u16,  1),
                    ('PTGTCSup',               c_u16,  1),
                    ('CompPTGranUnit',         c_u16,  1),
                    ('Rv',                     c_u16, 12),
        ]


    _anonymous_ = ('field',)
    _fields_    = [('field', PTCAP1Fields), ('val', c_u16)]
    _gran    = ['ns', 'ps']
    _special = {'CompPTGranUnit': _gran}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class PTCTL(SpecialField, Union):
    class PTCTLFields(Structure):
        _fields_ = [('PTReqEnb',               c_u16,  1),
                    ('PTRspEnb',               c_u16,  1),
                    ('PTGTCEnb',               c_u16,  1),
                    ('MigratePTAltRsp',        c_u16,  1),
                    ('PTDGranUnit',            c_u16,  1),
                    ('GTCSIDEnb',              c_u16,  1),
                    ('PTRspSIDEnb',            c_u16,  1), # Not in v1.1e
                    ('AltPTRspSIDEnb',         c_u16,  1), # Not in v1.1e
                    ('Rv',                     c_u16,  8), # 10 bits in v1.1e
        ]


    _anonymous_ = ('field',)
    _fields_    = [('field', PTCTLFields), ('val', c_u16)]
    _gran    = ['ns', 'ps']
    _special = {'PTDGranUnit': _gran}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class RCCAP1(SpecialField, Union):
    class RCCAP1Fields(Structure):
        _fields_ = [('RtCtlTableSz',                      c_u16,  2),
                    ('MSS',                               c_u16,  1),
                    ('HCS',                               c_u16,  1),
                    ('Rv',                                c_u16, 12),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', RCCAP1Fields), ('val', c_u16)]
    _tbl_sz     = ['48B']
    _special = {'RtCtlTableSz': _tbl_sz}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class RKDCAP1(SpecialField, Union):
    class RKDCAP1Fields(Structure):
        _fields_ = [('RKDTableType',                      c_u16,  3),
                    ('Rv',                                c_u16, 13),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', RKDCAP1Fields), ('val', c_u16)]
    _tbl_type   = ['Fixed4096bit']
    _special = {'RKDTableType': _tbl_type}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class RKDControl1(SpecialField, Union):
    class RKDControl1Fields(Structure):
        _fields_ = [('RKDValidationEnb',                  c_u16,  1),
                    ('TrustedThreadEnb',                  c_u16,  1),
                    ('Rv',                                c_u16, 14),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', RKDControl1Fields), ('val', c_u16)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class SwitchCAP1(SpecialField, Union):
    class SwitchCAP1Fields(Structure):
        _fields_ = [('CtlOpClassPktFilteringSup',         c_u32,  1),
                    ('ULATScale',                         c_u32,  1),
                    ('MLATScale',                         c_u32,  1),
                    ('PCOCommSup',                        c_u32,  1),
                    ('UnreliableCtlWrMSGPktFilteringSup', c_u32,  1),
                    ('DefaultCollPktRelaySup',            c_u32,  1),
                    ('Rv',                                c_u32, 26),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', SwitchCAP1Fields), ('val', c_u32)]
    _scale   = ['ps', 'ns']
    _special = {'ULATScale': _scale, 'MLATScale': _scale}

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class SwitchCAP1Control(SpecialField, Union):
    class SwitchCAP1ControlFields(Structure):
        _fields_ = [('MCPRTEnb',                          c_u32,  1),
                    ('MSMCPRTEnb',                        c_u32,  1),
                    ('DefaultMCPktRelayEnb',              c_u32,  1),
                    ('DefaultCollPktRelayEnb',            c_u32,  1),
                    ('Rv',                                c_u32, 28),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', SwitchCAP1ControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class SwitchOpCTL(SpecialField, Union):
    class SwitchOpCTLFields(Structure):
        _fields_ = [('PktRelayEnb',                       c_u16,  1),
                    ('Rv',                                c_u16, 15),
        ]

    _anonymous_ = ('field',)
    _fields_    = [('field', SwitchOpCTLFields), ('val', c_u16)]

    def __init__(self, value, parent, verbosity=0, check=False):
        super().__init__(value, parent, verbosity=verbosity, check=check)
        self.val = value

class OpClasses():
    _map = {  'Core64'                              : 0x00,
              'Control'                             : 0x01,
              'Atomic1'                             : 0x02,
              'LDM1'                                : 0x03,
              'Adv1'                                : 0x04,
              'Adv2'                                : 0x05,
              'DR'                                  : 0x14,
              'CtxId'                               : 0x15,
              'Multicast'                           : 0x16,
              'SOD'                                 : 0x17,
              'VDOpc1'                              : 0x18,
              'VDOpc2'                              : 0x19,
              'VDOpc3'                              : 0x1a,
              'VDOpc4'                              : 0x1b,
              'VDOpc5'                              : 0x1c,
              'VDOpc6'                              : 0x1d,
              'VDOpc7'                              : 0x1e,
              'VDOpc8'                              : 0x1f,
    }

    _inverted_map = {v : k for k, v in _map.items()}

    def ocl(self, name):
        return self._map[name]

    def name(self, ocl):
        return self._inverted_map[ocl]

    def opClass(self, ocl):
        opc = globals()[self.name(ocl) + 'Opcodes'](0, None)
        return opc

class P2P64Opcodes(Opcodes):
    _map = {  'StandaloneAck'                       : 0x00,
              'ReadResponse'                        : 0x01,
              'CacheLineAttrResponse'               : 0x02,
              'SubOp1Response'                      : 0x03,
              'Write'                               : 0x04,
              'Read'                                : 0x05,
              'ReadExclusive'                       : 0x06,
              'ReadShared'                          : 0x07,
              'Release'                             : 0x08,
              'Writeback'                           : 0x0a,
              'CacheLineAttrRequest'                : 0x0b,
              'Exclusive'                           : 0x0c,
              'WritePoison'                         : 0x0d,
              'Interrupt'                           : 0x0e,
              'TrustedRead'                         : 0x0f,
              'TrustedWrite'                        : 0x10,
              'Enqueue'                             : 0x11,
              'Dequeue'                             : 0x12,
              'CapabilitiesRead'                    : 0x13,
              'CapabilitiesWrite'                   : 0x14,
              'PersistentFlush'                     : 0x1b,
              'Meta32Write'                         : 0x1c,
              'Meta64Write'                         : 0x1d,
              'WritePartial'                        : 0x1e,
              'SubOp1Request'                       : 0x1f,
    }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class Core64Opcodes(Opcodes):
    _map = {  'StandaloneAck'                       : 0x00,
              'ReadResponse'                        : 0x01,
              'CacheLineAttrResponse'               : 0x02,
              'Write'                               : 0x04,
              'WritePoison'                         : 0x07,
              'Interrupt'                           : 0x08,
              'PersistentFlush'                     : 0x09,
              'Writeback'                           : 0x0b,
              'ReadExclusive'                       : 0x0c,
              'ReadShared'                          : 0x0d,
              'Release'                             : 0x0e,
              'CacheLineAttrRequest'                : 0x0f,
              'WakeThread'                          : 0x10,
              'CapabilitiesRead'                    : 0x11,
              'CapabilitiesWrite'                   : 0x12,
              'WritePartial'                        : 0x13,
              'Exclusive'                           : 0x14,
              'MultiOp'                             : 0x1a,
              'Read'                                : 0x1b,
              'WriteUnderMask'                      : 0x1c,
              'NIRRelease'                          : 0x1d,
    }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class ControlOpcodes(Opcodes):
    _map = {  'StandaloneAck'                       : 0x00,
              'ReadResponse'                        : 0x01,
              'Write'                               : 0x04,
              'Interrupt'                           : 0x08,
              'NoOp'                                : 0x09,
              'UnsolicitedEvent'                    : 0x0a,
              'CStatePowerCtl'                      : 0x0b,
              'RKeyUpdate'                          : 0x0c,
              'AEAD'                                : 0x0d,
              'WritePartial'                        : 0x13,
              'Read'                                : 0x1b,
              'CtlCTXIDNIRRelease'                  : 0x1c,
              'CtlNIRRelease'                       : 0x1d,
              'UnrelWriteMSG'                       : 0x1e,
              'WriteMSG'                            : 0x1f,
    }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class Atomic1Opcodes(Opcodes):
    _map = {  'AtomicResponse'                      : 0x00,
              'AtomicResultsResponse'               : 0x01,
              'Add'                                 : 0x04,
              'Sum'                                 : 0x05,
              'Swap'                                : 0x06,
              'CAS'                                 : 0x07,
              'CASNotEqual'                         : 0x08,
              'LogicalOR'                           : 0x09,
              'LogicalXOR'                          : 0x0a,
              'LogicalAND'                          : 0x0b,
              'LoadMax'                             : 0x0c,
              'LoadMin'                             : 0x0d,
              'TestZeroAndModify'                   : 0x0e,
              'IncrementBounded'                    : 0x0f,
              'IncrementEqual'                      : 0x10,
              'DecrementBounded'                    : 0x11,
              'CompareStoreTwin'                    : 0x12,
              'AtomicVectorSum'                     : 0x13,
              'AtomicVectorLogical'                 : 0x14,
              'AtomicFetch'                         : 0x15,
    }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class LDM1Opcodes(Opcodes):
    _map = {  'LDM1ReadResponse'                    : 0x00,
              'BufferAllocateResponse'              : 0x01,
              'LDM1Read'                            : 0x04,
              'BufferPut'                           : 0x05,
              'BufferGet'                           : 0x06,
              'BufferPutv'                          : 0x07,
              'BufferGetv'                          : 0x08,
              'SignaledBufferPut'                   : 0x09,
              'SignaledBufferGet'                   : 0x0a,
              'DynamicBufferPut'                    : 0x0b,
              'DynamicBufferGet'                    : 0x0c,
              'SignaledDynamicBufferPut'            : 0x0e,
              'SignaledDynamicBufferGet'            : 0x0f,
              'DynamicBufferAllocate'               : 0x10,
              'DynamicBufferRelease'                : 0x11,
              'BufferSecuredPut'                    : 0x12,
              'BufferSecuredGet'                    : 0x13,
              'DynamicBufferSecuredPut'             : 0x14,
              'DynamicBufferSecuredGet'             : 0x15,
    }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class Adv1Opcodes(Opcodes):
    _map = {  'PatternResponse'                     : 0x00,
              'PatternSet'                          : 0x04,
              'PatternCount'                        : 0x05,
              'PatternMatch'                        : 0x06,
    }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class Adv2Opcodes(Opcodes):
    _map = {  'EncapResponse'                       : 0x00,
              'PTRSP'                               : 0x01,
              'MACK'                                : 0x02,
              'EncapRequest'                        : 0x04,
              'PTREQ'                               : 0x1f,
    }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class MulticastOpcodes(Opcodes):
    _map = {  'VendorDefinedResponse1'              : 0x02,
              'VendorDefinedResponse2'              : 0x03,
              'UnrelEncapRequest'                   : 0x04,
              'Write'                               : 0x05,
              'ReliableEncapRequest'                : 0x06,
              'UnrelWrite'                          : 0x08,
              'VendorDefined1'                      : 0x1a,
              'VendorDefined2'                      : 0x1b,
              'VendorDefined3'                      : 0x1c,
              'VendorDefined4'                      : 0x1d,
              'UnrelWriteMSG'                       : 0x1e,
              'WriteMSG'                            : 0x1f,
              }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class SODOpcodes(Opcodes):
    _map = {  'ACK'                                 : 0x00,
              'ReadResponse'                        : 0x01,
              'EncapResponse'                       : 0x02,
              'Write'                               : 0x04,
              'Sync'                                : 0x05,
              'WritePersistent'                     : 0x06,
              'Interrupt'                           : 0x08,
              'Enqueue'                             : 0x09,
              'Dequeue'                             : 0x0a,
              'NIRR'                                : 0x0b,
              'Read'                                : 0x1b,
              'EncapRequest'                        : 0x1c,
              'WriteMSG'                            : 0x1f,
              }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class CtxIdOpcodes(Opcodes):
    _map = {  'TranslationRsp'                      : 0x01,
              'TranslationInvalidateRsp'            : 0x02,
              'CollectiveRsp'                       : 0x03,
              'TranslationReq'                      : 0x04,
              'PRGReq'                              : 0x05,
              'PRGRspNotif'                         : 0x06,
              'TranslationInvalidateReq'            : 0x07,
              'StopMarkerReq'                       : 0x08,
              'PRGRelese'                           : 0x09,
              'PRGEvictionNotif'                    : 0x0a,
              'CollectiveReq'                       : 0x0b,
              'Enqueue'                             : 0x0c,
              'Dequeue'                             : 0x0d,
              'CTXIDNIRRelease'                     : 0x1d,
              'UnrelWriteMSG'                       : 0x1e,
              'WriteMSG'                            : 0x1f,
              }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class DROpcodes(Opcodes):
    _map = {  'StandaloneAck'                       : 0x00,
              'ReadResponse'                        : 0x01,
              'Write'                               : 0x04,
              'Read'                                : 0x1b,
              'UnrelWriteMSG'                       : 0x1e,
    }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class ControlStructureMap(LittleEndianStructure):
    _map = {  'CoreStructure'                       : 0x00,
              'OpCodeSetStructure'                  : 0x01,
              'InterfaceStructure'                  : 0x02,
              'InterfacePHYStructure'               : 0x03,
              'InterfaceStatisticsStructure'        : 0x04,
              'ComponentErrorSignalStructure'       : 0x05,
              'ComponentMediaStructure'             : 0x06,
              'ComponentSwitchStructure'            : 0x07,
              'ComponentStatisticsStructure'        : 0x08,
              'ComponentExtensionStructure'         : 0x09,
              'VendorDefinedStructure'              : 0x0a,
              'VendorDefinedUUIDStructure'          : 0x0b,
              'ComponentMulticastStructure'         : 0x0c,
              'ComponentTRStructure'                : 0x0e,
              'ComponentImageStructure'             : 0x0f,
              'ComponentPrecisionTimeStructure'     : 0x10,
              'ComponentMechanicalStructure'        : 0x11,
              'ComponentDestinationTableStructure'  : 0x12,
              'ServiceUUIDStructure'                : 0x13,
              'ComponentCAccessStructure'           : 0x14,
              'RequesterP2PStructure'               : 0x16,
              'ComponentPAStructure'                : 0x17,
              'ComponentEventStructure'             : 0x18,
              'ComponentLPDStructure'               : 0x19,
              'ComponentSODStructure'               : 0x1a,
              'CongestionManagementStructure'       : 0x1b,
              'ComponentRKDStructure'               : 0x1c,
              'ComponentPMStructure'                : 0x1d,
              'ComponentATPStructure'               : 0x1e,
              'ComponentRETableStructure'           : 0x1f,
              'ComponentLPHStructure'               : 0x20,
              'ComponentPageGridStructure'          : 0x21,
              'ComponentPageTableStructure'         : 0x22,
              'ComponentInterleaveStructure'        : 0x23,
              'ComponentFirmwareStructure'          : 0x24,
              'ComponentSWManagementStructure'      : 0x25,
              }

    _inverted_map = {v : k for k, v in _map.items()}

    _struct = { 'header'                      : 'ControlHeader',
                'core'                        : 'CoreStructure',
                'opcode_set'                  : 'OpCodeSetStructure',
                'interface'                   : 'InterfaceFactory',
                'interface_phy'               : 'InterfacePHYStructure',
                'interface_statistics'        : 'InterfaceStatisticsFactory',
                'component_error_and_signal_event' : 'ComponentErrorSignalStructure',
                'component_media'             : 'ComponentMediaStructure',
                'component_switch'            : 'ComponentSwitchStructure',
                'component_statistics'        : 'ComponentStatisticsStructure',
                'component_extension'         : 'ComponentExtensionStructure',
                'vendor_defined'              : 'VendorDefinedStructure',
                'vendor_defined_with_uuid'    : 'VendorDefinedUUIDStructure',
                'component_multicast'         : 'ComponentMulticastStructure',
                'component_tr'                : 'ComponentTRStructure',
                'component_image'             : 'ComponentImageStructure',
                'component_precision_time'    : 'ComponentPrecisionTimeStructure',
                'component_mechanical'        : 'ComponentMechanicalStructure',
                'component_destination_table' : 'ComponentDestinationTableStructure',
                'service_uuid'                : 'ServiceUUIDFactory',
                'component_c_access'          : 'ComponentCAccessStructure',
                'requester_p2p'               : 'RequesterP2PStructure',
                'component_pa'                : 'ComponentPAStructure',
                'component_event'             : 'ComponentEventStructure',
                'component_lpd'               : 'ComponentLPDStructure',
                'component_sod'               : 'ComponentSODStructure',
                'congestion_management'       : 'CongestionManagementStructure',
                'component_rkd'               : 'ComponentRKDStructure',
                'component_pm'                : 'ComponentPMStructure',
                'component_atp'               : 'ComponentATPStructure',
                'component_re_table'          : 'ComponentRETableStructure',
                'component_lph'               : 'ComponentLPHStructure',
                'component_page_grid'         : 'ComponentPageGridStructure',
                'component_page_table'        : 'ComponentPageTableStructure',
                'component_interleave'        : 'ComponentInterleaveStructure',
                'component_firmware'          : 'ComponentFirmwareStructure',
                'component_sw_management'     : 'ComponentSWManagementStructure',
                'unknown'                     : 'UnknownStructure',
                # Revisit: add more tables
                'opcode_set_table'            : 'OpCodeSetTableFactory',
                'opcode_set_uuid'             : 'OpCodeSetUUIDTable',
                'req_vcat'                    : 'RequesterVCATTable',
                'rsp_vcat'                    : 'ResponderVCATTable',
                'rit'                         : 'RITTable',
                'ssdt'                        : 'SSDTTable',
                'msdt'                        : 'MSDTTable',
                'lprt'                        : 'LPRTTable',
                'mprt'                        : 'MPRTTable',
                'vcat'                        : 'VCATTable',
                'route_control'               : 'RouteControlTable',
                'c_access_r_key'              : 'CAccessRKeyTable',
                'c_access_l_p2p'              : 'CAccessLP2PTable',
                'pg_table'                    : 'PGTable',
                'restricted_pg_table'         : 'PGTable',
                'pte_table'                   : 'PTETable',
                'restricted_pte_table'        : 'PTETable',
                'pa'                          : 'PATable',
                'ssap'                        : 'SSAPTable',
                'mcap'                        : 'MCAPTable',
                'msap'                        : 'MSAPTable',
                'msmcap'                      : 'MSMCAPTable',
                'i_snapshot'                  : 'ISnapshotFactory',
                's_uuid'                      : 'ServiceUUIDTable',
    }

    def nameToId(self, name):
        return self._map[name]

    def idToName(self, id):
        return self._inverted_map[id]

    def fileToStruct(self, file, data, verbosity=0, fd=None, path=None,
                     parent=None, core=None, offset=0, size=None):
        try:
            # first try file as a file name, e.g., 'core'
            struct = globals()[self._struct[file]].from_buffer_kw(data, offset,
                                                               parent=parent)
        except KeyError:
            # next try file as a structure name, e.g., 'CoreStructure'
            struct = globals()[file].from_buffer_kw(data, offset, parent=parent)
        struct.data = data
        struct.offset = offset
        struct.verbosity = verbosity
        struct.fd = fd
        struct.path = path
        struct.parent = parent
        struct.core = core
        struct._stat = None
        struct._size = size
        struct.fileToStructInit()
        return struct

    def set_fd(self, f):
        self.fd = f.fileno()

def add_from_buffer_kw(cls):
    def from_buffer_kw(data, offset=0, **kwargs):
        return cls.from_buffer(data, offset)

    setattr(cls, 'from_buffer_kw', from_buffer_kw)
    return cls

#Revisit: jmh - this is almost totally version independent
class ControlStructure(ControlStructureMap):
    fullEntryWrite = False

    def __init__(self, verbosity=0, **kwargs):
        self.verbosity = verbosity
        super().__init__(**kwargs)

    def all_ones_type_vers_size(self):
        return self.Type == 0xfff and self.Vers == 0xf and self.Size == 0xffff

    @property
    def sz_bytes(self):
        return self.Size << 4

    def sz_0_special(self, fld_val, fld_bits):
        return fld_val if fld_val != 0 else (1 << fld_bits)

    def ptr_off(self, ptr):
        return ptr << 4

    @property
    def ptrs(self):
        if hasattr(self, '_ptr_fields'):
            for ptr in self._ptr_fields:
                val = getattr(self, ptr)
                if (val != 0):
                    yield (ptr, val * 16) # 16-byte granularity

    def uuid(self, uuidField):
        # UUIDs are stored big-endian, but this class is a
        # LittleEndianStructure, so use byteorder='little'
        high = getattr(self, uuidField[0])
        low = getattr(self, uuidField[1])
        return uuid.UUID(bytes=(high << 64 | low).to_bytes(
            16, byteorder='little'))

    @property
    def uuids(self):
        if hasattr(self, '_uuid_fields'):
            for uuidField in self._uuid_fields:
                uu = self.uuid(uuidField)
                yield (uuidField[0], uuidField[1], uu)

    def isUuid(self, field):
        if hasattr(self, '_uuid_dict'):
            uuid_tuple = self._uuid_dict.get(field)
            if uuid_tuple is not None:
                return self.uuid(uuid_tuple)
        return None

    def isSpecial(self, field):
        if hasattr(self, '_special_dict'):
            special_class = self._special_dict.get(field)
            if special_class is not None:
                return special_class(getattr(self, field), self,
                                     verbosity=self.verbosity)
        return None

    def bitField(self, width, bitOffset):
        byteOffset = bitOffset // 64 * 8
        lowBit = bitOffset % 64
        highBit = lowBit + width - 1
        hexWidth = (width + 3) // 4
        return (byteOffset, highBit, lowBit, hexWidth)

    def __str__(self):
        r = '{}'.format(type(self).__name__)
        if self.verbosity < 2:
            return r
        r += ':\n'
        max_len = max(len(field[0]) for field in self._fields_)
        bitOffset = 0
        skipNext = False
        for field in self._fields_:
            name = field[0]
            try:
                width = field[2]
            except IndexError:
                width = 0
            if skipNext:
                bitOffset += width
                skipNext = False
                continue
            byteOffset, highBit, lowBit, hexWidth = self.bitField(width, bitOffset)
            if self.Size > 0 and byteOffset >= self.Size * 16:
                break
            uu = self.isUuid(name)
            if uu is not None:
                r += '    {0:{nw}}@0x{1:0>3x} = {2}\n'.format(
                    name[:-1], byteOffset, uu, nw=max_len)
                skipNext = True
            elif width == 0:
                arrayStr = textwrap.indent(str(self.embeddedArray), '  ')
                r += '    {0:{nw}}@0x{1:0>3x} = {2}\n'.format(
                    name, byteOffset, arrayStr[2:], nw=max_len)
            else:
                if rv_re.match(name) is not None and self.verbosity < 6:
                    bitOffset += width
                    continue
                r += '    {0:{nw}}@0x{1:0>3x}{{{2:2}:{3:2}}} = 0x{4:0>{hw}x}\n'.format(
                    name, byteOffset, highBit, lowBit,
                    getattr(self, name),
                    nw=max_len, hw=hexWidth)
                if self.verbosity < 3:
                    bitOffset += width
                    continue
                special = self.isSpecial(name)
                if special is not None:
                    specialStr = textwrap.fill(
                        str(special), expand_tabs=False, width=cols,
                        initial_indent='      ', subsequent_indent='      ')
                    if specialStr != '':
                        r += '{}\n'.format(specialStr)
            bitOffset += width
        # end for field
        return r

    def __repr__(self):
        r = type(self).__name__ + '('
        l = len(self._fields_)
        skipNext = False
        for i, field in enumerate(self._fields_, start=1):
            if skipNext:
                skipNext = False
                if i == l:
                    r += ')'
                continue
            name = field[0]
            try:
                width = field[2]
            except IndexError:
                width = 0
            uu = self.isUuid(name)
            if uu is not None:
                fmt = '{}={}, ' if i < l else '{}={})'
                r += fmt.format(name[:-1], uu)
                skipNext = True
            elif width == 0:
                r += repr(self.embeddedArray)
                #set_trace() # Revisit: temp debug
            else:
                fmt = '{}=0x{:x}, ' if i < l else '{}=0x{:x})'
                r += fmt.format(name, getattr(self, name))
        return r

    def fileToStructInit(self):
        pass

class ControlTable(ControlStructure):
    def fileToStructInit(self):
        if self.path is not None:
            self._stat = self.path.stat()

    def all_ones_type_vers_size(self):
        # tables have no Type/Vers/Size
        return False

    @property
    def Size(self):
        if self._size is not None:
            return self._size
        self._size = self._stat.st_size
        return self._size

# for PATable, RIT, SSAP, MCAP, MSAP, MSMCAP,
# CAccessRKeyTable, CAccessLP2PTable, PGTable, PTETable, ServiceUUIDTable
class ControlTableArray(ControlTable):
    def cs_offset(self, row, *unused):
        return sizeof(self.element) * row

    def __getitem__(self, key):
        return self.array[key]

    def __len__(self):
        return len(self.array)

    def __iter__(self):
        return iter(self.array)

    def __str__(self):
        r = type(self).__name__
        if self.verbosity < 2:
            return r
        r += ':\n'
        if self.verbosity < 4:
            return r
        elif self.verbosity == 4:
            name = type(self.array[0]).__name__
            hasV = hasattr(self.array[0], 'V')
            for i in range(len(self)):
                v = self.array[i].V if hasV else 1
                if v:
                    r += '    {}[{}]={}\n'.format(name, i, repr(self.array[i]))
        else:
            # Revisit: the str() output should be indented another 2 spaces
            name = type(self.array[0]).__name__
            hasV = hasattr(self.array[0], 'V')
            for i in range(len(self)):
                v = self.array[i].V if hasV and self.verbosity < 6 else 1
                if v:
                    r += '    {}[{}]={}\n'.format(name, i, str(self.array[i]))

        return r

    def __repr__(self):
        return repr(self.array)

# for RequesterVCAT, ResponderVCAT, VCAT, SSDT, MSDT, LPRT, MPRT
class ControlTable2DArray(ControlTableArray):
    fullEntryWrite = True

    @property
    def rows(self):
        return len(self.array)

    @property
    def cols(self):
        return len(self.array[0])

    def cs_offset(self, row, col):
        return sizeof(self.element) * ((row * self.cols) + col)

    def __str__(self):
        r = type(self).__name__
        if self.verbosity < 2:
            return r
        r += ':\n'
        if self.verbosity < 4:
            return r
        elif self.verbosity == 4:
            name = type(self.array[0][0]).__name__
            hasV = hasattr(self.array[0][0], 'V')
            for i in range(self.rows):
                for j in range(self.cols):
                    v = self.array[i][j].V if hasV else 1
                    if v:
                        r += '    {}[{}][{}]={}\n'.format(name, i, j,
                                                      repr(self.array[i][j]))
        else:
            # Revisit: the str() output should be indented another 2 spaces
            name = type(self.array[0][0]).__name__
            hasV = hasattr(self.array[0][0], 'V')
            for i in range(self.rows):
                for j in range(self.cols):
                    v = self.array[i][j].V if hasV and self.verbosity < 6 else 1
                    if v:
                        r += '    {}[{}][{}]={}\n'.format(name, i, j,
                                                      str(self.array[i][j]))

        return r

#Revisit: jmh - this is version independent
class ControlHeader(ControlStructure):
    _fields_ = [('Type',          c_u64, 12),
                ('Vers',          c_u64,  4),
                ('Size',          c_u64, 16),
                ]

    def __str__(self):
        return self.__repr__()

@add_from_buffer_kw
class CoreStructure(ControlStructure):
    _fields_ = [('Type',          c_u64, 12), # 0x0
                ('Vers',          c_u64,  4),
                ('Size',          c_u64, 16),
                ('R0',            c_u64, 32),
                ('CStatus',       c_u64, 64), # 0x8
                ('CControl',      c_u64, 64), # 0x10
                ('BaseCClass',    c_u64, 16), # 0x18
                ('MaxInterface',  c_u64, 12),
                ('RBIST',         c_u64,  4),
                ('RDLAT',         c_u64, 16),
                ('WRLAT',         c_u64, 16),
                ('MaxRSPSuppReqs',c_u64, 20), # 0x20
                ('MaxREQSuppReqs',c_u64, 20),
                ('COpClock',      c_u64, 24),
                ('MaxData',       c_u64, 64), # 0x28
                ('MaxCTL',        c_u64, 52), # 0x30
                ('MaxRNR',        c_u64,  3),
                ('R1',            c_u64,  9),
                ('CStateTransLat',c_u64, 32), # 0x38
                ('CIdleTimes',    c_u64, 16),
                ('R2',            c_u64, 16),
                ('LPWR',          c_u64, 10), # 0x40
                ('NPWR',          c_u64, 10),
                ('HPWR',          c_u64, 10),
                ('EPWR',          c_u64, 10),
                ('APWR',          c_u64, 10),
                ('R3',            c_u64, 14),
                ('StructPTR0',    c_u64, 32), # 0x48
                ('StructPTR1',    c_u64, 32),
                ('StructPTR2',    c_u64, 32), # 0x50
                ('StructPTR3',    c_u64, 32),
                ('StructPTR4',    c_u64, 32), # 0x58
                ('StructPTR5',    c_u64, 32),
                ('StructPTR6',    c_u64, 32), # 0x60
                ('StructPTR7',    c_u64, 32),
                ('StructPTR8',    c_u64, 32), # 0x68
                ('CoreLPDBDFPTR', c_u64, 32),
                ('OpcodeSetPTR',  c_u64, 32), # 0x70
                ('CAccessPTR',    c_u64, 32),
                ('CompDestPTR',   c_u64, 32), # 0x78
                ('Interface0PTR', c_u64, 32),
                ('CompExtPTR',    c_u64, 32), # 0x80
                ('CompErrSigPTR', c_u64, 32),
                ('LLMUTO',        c_u64, 16), # 0x88
                ('CRPTO',         c_u64, 16),
                ('CCTO',          c_u64, 16),
                ('FAILTO',        c_u64, 16),
                ('R4',            c_u64, 48), # 0x90
                ('UNRSP',         c_u64, 16),
                ('UERT',          c_u64, 16), # 0x98
                ('NIRT',          c_u64, 16),
                ('ATSTO',         c_u64, 16),
                ('UNREQ',         c_u64, 16),
                ('LLReqDeadline', c_u64, 10), # 0xa0
                ('NLLReqDeadline',c_u64, 10),
                ('DeadlineTick',  c_u64, 12),
                ('FPST',          c_u64, 16),
                ('PCOFPST',       c_u64, 16),
                ('LLRspDeadline', c_u64, 10), # 0xa8
                ('NLLRspDeadline',c_u64, 10),
                ('RspDeadline',   c_u64, 10),
                ('R5',            c_u64, 18),
                ('SFMSID',        c_u64, 16),
                ('PMCID',         c_u64, 12), # 0xb0
                ('PWRMGRCID',     c_u64, 12),
                ('PFMCID',        c_u64, 12),
                ('PFMSID',        c_u64, 16),
                ('SFMCID',        c_u64, 12),
                ('SID0',          c_u64, 16), # 0xb8
                ('DRReqDeadline', c_u64, 10),
                ('R6',            c_u64, 38),
                ('CV',            c_u64,  8), # 0xc0
                ('CID0',          c_u64, 12),
                ('CID1',          c_u64, 12),
                ('CID2',          c_u64, 12),
                ('CID3',          c_u64, 12),
                ('R7',            c_u64,  4),
                ('BufferTC',      c_u64,  4),
                ('MaxRequests',   c_u64, 20), # 0xc8
                ('R8',            c_u64, 14),
                ('PWRMGRSID',     c_u64, 16),
                ('R9',            c_u64, 14),
                ('ControlTO',     c_u64, 16), # 0xd0
                ('ControlDRTO',   c_u64, 16),
                ('NLMUTO',        c_u64, 16),
                ('NOPDESTCID',    c_u64, 12),
                ('NOPDESTSIDl',   c_u64,  4),
                ('NOPDESTSIDh',   c_u64, 12),
                ('NOPSRCCID',     c_u64, 12),
                ('NOPSRCSID',     c_u64, 16),
                ('AEC',           c_u64,  4),
                ('R10',           c_u64, 20),
                ('R11l',          c_u64, 64), #0xe0
                ('R11h',          c_u64, 64), #0xe8
                ('R12l',          c_u64, 64), #0xf0
                ('R12h',          c_u64, 64), #0xf8
                ('R13l',          c_u64, 64), #0x100
                ('R13h',          c_u64, 64), #0x108
                ('R14l',          c_u64, 64), #0x110
                ('R14h',          c_u64, 64), #0x118
                ('R15l',          c_u64, 64), #0x120
                ('R15h',          c_u64, 64), #0x128
                ('StructPTR9',    c_u64, 32), #0x130
                ('StructPTR10',   c_u64, 32),
                ('StructPTR11',   c_u64, 32), #0x138
                ('StructPTR12',   c_u64, 32),
                ('StructPTR13',   c_u64, 48), #0x140
                ('StructPTR14l',  c_u64, 16),
                ('StructPTR14h',  c_u64, 32), #0x148
                ('StructPTR15',   c_u64, 32),
                ('CAP1',          c_u64, 64), #0x150
                ('CAP1Control',   c_u64, 64), #0x158
                ('CAP2',          c_u64, 64), #0x160
                ('CAP2Control',   c_u64, 64), #0x168
                ('CAP3',          c_u64, 64), #0x170
                ('CAP3Control',   c_u64, 64), #0x178
                ('CAP4',          c_u64, 64), #0x180
                ('CAP4Control',   c_u64, 64), #0x188
                ('R16l',          c_u64, 64), #0x190
                ('R16h',          c_u64, 20), #0x198
                ('UWMSGSZ',       c_u64, 11),
                ('WMSGSZ',        c_u64, 11),
                ('CWMSGSZ',       c_u64, 11),
                ('UCWMSGSZ',      c_u64, 11),
                ('COHLAT',        c_u64, 16), #0x1a0
                ('OOOTO',         c_u64, 16),
                ('REQNIRTO',      c_u64, 16),
                ('REQABNIRTO',    c_u64, 16),
                ('CompNonce',     c_u64, 64), #0x1a8
                ('MGRUUIDl',      c_u64, 64), #0x1b0
                ('MGRUUIDh',      c_u64, 64), #0x1b8
                ('SerialNumber',  c_u64, 64), #0x1c0
                ('ThermAttribs',  c_u64, 16), #0x1c8
                ('UpperThermLim', c_u64, 10),
                ('CautionThermLim',c_u64, 10),
                ('LowestThermLim',c_u64, 11),
                ('CurrentTherm',  c_u64, 11),
                ('R17',           c_u64,  6),
                ('ZUUIDl',        c_u64, 64), #0x1d0
                ('ZUUIDh',        c_u64, 64), #0x1d8
                ('CUUIDl',        c_u64, 64), #0x1e0
                ('CUUIDh',        c_u64, 64), #0x1e8
                ('FRUUUIDl',      c_u64, 64), #0x1f0
                ('FRUUUIDh',      c_u64, 64), #0x1f8
                ]

    _ptr_fields = ['CoreLPDBDFPTR', 'OpcodeSetPTR', 'CAccessPTR',
                   'CompDestPTR','Interface0PTR', 'CompExtPTR',
                   'CompErrSigPTR',
                   'StructPTR0', 'StructPTR1', 'StructPTR2', 'StructPTR3',
                   'StructPTR4', 'StructPTR5', 'StructPTR6', 'StructPTR7',
                   'StructPTR8', 'StructPTR9', 'StructPTR10', 'StructPTR11',
                   'StructPTR12', 'StructPTR13', 'StructPTR14', 'StructPTR15']

    _uuid_fields = [('MGRUUIDh', 'MGRUUIDl'), ('ZUUIDh', 'ZUUIDl'),
                    ('CUUIDh', 'CUUIDl'), ('FRUUUIDh', 'FRUUUIDl')]

    _uuid_dict = dict(zip([item for sublist in zip(*_uuid_fields) for item in sublist],
                          _uuid_fields * 2))

    _special_dict = { 'CStatus': CStatus, 'CControl': CControl,
                      'CAP1': CAP1, 'CAP1Control': CAP1Control,
                      'CAP2': CAP2, 'CAP2Control': CAP2Control }

    @property
    def CUUID(self): # Revisit: generate this (and others) from _uuid_fields
        return self.uuid(('CUUIDh', 'CUUIDl'))

    @property
    def MGRUUID(self): # Revisit: generate this (and others) from _uuid_fields
        return self.uuid(('MGRUUIDh', 'MGRUUIDl'))

    @property
    def ZUUID(self): # Revisit: generate this (and others) from _uuid_fields
        return self.uuid(('ZUUIDh', 'ZUUIDl'))

    def fileToStructInit(self):
        self.sw = None
        self.comp_dest = None

@add_from_buffer_kw
class ComponentDestinationTableStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('DestTableCAP1',              c_u64, 32),
                ('DestTableControl',           c_u64, 32),
                ('SSDTSize',                   c_u64, 12),
                ('HCSize',                     c_u64,  4),
                ('MHCSize',                    c_u64,  4),
                ('MaxRoutes',                  c_u64, 12),
                ('REQVCATSZ',                  c_u64,  5),
                ('RSPVCATSZ',                  c_u64,  5),
                ('RITPadSize',                 c_u64,  5),
                ('R0',                         c_u64, 17),
                ('SSDTMSDTRowSize',            c_u64, 16),
                ('MSDTSize',                   c_u64, 16),
                ('RITSize',                    c_u64, 12),
                ('R1',                         c_u64, 20),
                ('RtCtlPTR',                   c_u64, 32),
                ('SSDTPTR',                    c_u64, 32),
                ('MSDTPTR',                    c_u64, 32),
                ('REQVCATPTR',                 c_u64, 32),
                ('RITPTR',                     c_u64, 32),
                ('RSPVCATPTR',                 c_u64, 32),
                ('R2',                         c_u64, 32),
                ('R3',                         c_u64, 64)]

    _special_dict = {'DestTableCAP1': DestTableCAP1,
                     'DestTableControl': DestTableControl}

    _ptr_fields = ['RouteControlPtr', 'SSDTPTR', 'MSDTPTR', 'REQVCATPTR',
                   'RITPTR', 'RSPVCATPTR']

@add_from_buffer_kw
class OpCodeSetStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('CAP1Control',                c_u64, 32),
                ('CAP1',                       c_u64, 64),
                ('CacheLineSizes',             c_u64,  4),
                ('R0',                         c_u64,  4),
                ('WritePoisonSizes',           c_u64,  8),
                ('ArithAtomicSizes',           c_u64,  8),
                ('LogFetchAtomicSizes',        c_u64,  8),
                ('FloatAtomicSizes',           c_u64,  8),
                ('SwapCmpAtomicSizes',         c_u64,  8),
                ('AtomicLAT',                  c_u64, 16),
                ('OpCodeSetUUIDPTR',           c_u64, 32),
                ('OpCodeSetPTR',               c_u64, 32),
                ('SupportedUN',                c_u64, 16),
                ('SupportedFL',                c_u64,  8),
                ('VOCL1',                      c_u64,  5),
                ('VOCL2',                      c_u64,  5),
                ('VOCL3',                      c_u64,  5),
                ('VOCL4',                      c_u64,  5),
                ('VOCL5',                      c_u64,  5),
                ('VOCL6',                      c_u64,  5),
                ('VOCL7',                      c_u64,  5),
                ('VOCL8',                      c_u64,  5),
                ('R1',                         c_u64, 64)
    ]


    _special_dict = {'CAP1': OpCodeSetCAP1, 'CAP1Control': OpCodeSetCAP1Control}

# base class from which to dynamically build OpCodeSetTable
@add_from_buffer_kw
class OpCodeSetTableTemplate(ControlTable):
    _fields  = [('SetID',                          c_u64,  3), #0x0
                ('R0',                             c_u64,  5),
                ('Version',                        c_u64,  8),
                ('Control1',                       c_u64, 16),
                ('NextOpcodeSetPtr',               c_u64, 32),
                ('R1',                             c_u64, 64), #0x8
                ('SupportedCore64OpCodeSet',       c_u64, 64), #0x10
                ('EnabledCore64OpCodeSet',         c_u64, 64), #0x18
                ('SupportedControlOpCodeSet',      c_u64, 64), #0x20
                ('EnabledControlOpCodeSet',        c_u64, 64), #0x28
                ('SupportedP2P64OpCodeSet',        c_u64, 64), #0x30
                ('EnabledP2P64OpCodeSet',          c_u64, 64), #0x38
                ('SupportedAtomic1OpCodeSet',      c_u64, 64), #0x40
                ('EnabledAtomic1OpCodeSet',        c_u64, 64), #0x48
                ('SupportedLDM1OpCodeSet',         c_u64, 64), #0x50
                ('EnabledLDM1OpCodeSet',           c_u64, 64), #0x58
                ('SupportedAdvanced1OpCodeSet',    c_u64, 64), #0x60
                ('EnabledAdvanced1OpCodeSet',      c_u64, 64), #0x68
                ]
    _v0_fields = [
                ('SupportedOpClass0x6OpCodeSet',   c_u64, 64), #0x70
                ('EnabledOpClass0x6OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x7OpCodeSet',   c_u64, 64), #0x80
                ('EnabledOpClass0x7OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x8OpCodeSet',   c_u64, 64), #0x90
                ('EnabledOpClass0x8OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x9OpCodeSet',   c_u64, 64), #0xA0
                ('EnabledOpClass0x9OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xaOpCodeSet',   c_u64, 64), #0xB0
                ('EnabledOpClass0xaOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xbOpCodeSet',   c_u64, 64), #0xC0
                ('EnabledOpClass0xbOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xcOpCodeSet',   c_u64, 64), #0xD0
                ('EnabledOpClass0xcOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xdOpCodeSet',   c_u64, 64), #0xE0
                ('EnabledOpClass0xdOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xeOpCodeSet',   c_u64, 64), #0xF0
                ('EnabledOpClass0xeOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xfOpCodeSet',   c_u64, 64), #0x100
                ('EnabledOpClass0xfOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x10OpCodeSet',  c_u64, 64), #0x110
                ('EnabledOpClass0x10OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x11OpCodeSet',  c_u64, 64), #0x120
                ('EnabledOpClass0x11OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x12OpCodeSet',  c_u64, 64), #0x130
                ('EnabledOpClass0x12OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x13OpCodeSet',  c_u64, 64), #0x140
                ('EnabledOpClass0x13OpCodeSet',    c_u64, 64),
                ('SupportedDROpCodeSet',           c_u64, 64), #0x150
                ('EnabledDROpCodeSet',             c_u64, 64),
                ('SupportedCtxIdOpCodeSet',        c_u64, 64), #0x160
                ('EnabledCtxIdOpCodeSet',          c_u64, 64),
                ('SupportedMulticastOpCodeSet',    c_u64, 64), #0x170
                ('EnabledMulticastOpCodeSet',      c_u64, 64),
                ('SupportedSODOpCodeSet',          c_u64, 64), #0x180
                ('EnabledSODOpCodeSet',            c_u64, 64),
                ('SupportedMultiOpReqSubOpSet',    c_u64, 64), #0x190
                ('EnabledMultiOpReqSubOpSet',      c_u64, 64),
                ('SupportedReadMultiOpSet',        c_u64, 32), #0x1A0
                ('EnabledReadMultiOpSet',          c_u64, 32),
                ('R2',                             c_u64, 64), #0x1A8
                ]
    _v1_fields = [
                ('SupportedAdvanced2OpCodeSet',    c_u64, 64), #0x70
                ('EnabledAdvanced2OpCodeSet',      c_u64, 64),
                ('SupportedOpClass0x6OpCodeSet',   c_u64, 64), #0x80
                ('EnabledOpClass0x6OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x7OpCodeSet',   c_u64, 64), #0x90
                ('EnabledOpClass0x7OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x8OpCodeSet',   c_u64, 64), #0xA0
                ('EnabledOpClass0x8OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x9OpCodeSet',   c_u64, 64), #0xB0
                ('EnabledOpClass0x9OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xaOpCodeSet',   c_u64, 64), #0xC0
                ('EnabledOpClass0xaOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xbOpCodeSet',   c_u64, 64), #0xD0
                ('EnabledOpClass0xbOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xcOpCodeSet',   c_u64, 64), #0xE0
                ('EnabledOpClass0xcOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xdOpCodeSet',   c_u64, 64), #0xF0
                ('EnabledOpClass0xdOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xeOpCodeSet',   c_u64, 64), #0x100
                ('EnabledOpClass0xeOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xfOpCodeSet',   c_u64, 64), #0x110
                ('EnabledOpClass0xfOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x10OpCodeSet',  c_u64, 64), #0x120
                ('EnabledOpClass0x10OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x11OpCodeSet',  c_u64, 64), #0x130
                ('EnabledOpClass0x11OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x12OpCodeSet',  c_u64, 64), #0x140
                ('EnabledOpClass0x12OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x13OpCodeSet',  c_u64, 64), #0x150
                ('EnabledOpClass0x13OpCodeSet',    c_u64, 64),
                ('SupportedDROpCodeSet',           c_u64, 64), #0x160
                ('EnabledDROpCodeSet',             c_u64, 64),
                ('SupportedCtxIdOpCodeSet',        c_u64, 64), #0x170
                ('EnabledCtxIdOpCodeSet',          c_u64, 64),
                ('SupportedMulticastOpCodeSet',    c_u64, 64), #0x180
                ('EnabledMulticastOpCodeSet',      c_u64, 64),
                ('SupportedSODOpCodeSet',          c_u64, 64), #0x190
                ('EnabledSODOpCodeSet',            c_u64, 64),
                ('SupportedMultiOpReqSubOpSet',    c_u64, 64), #0x1A0
                ('EnabledMultiOpReqSubOpSet',      c_u64, 64),
                ('SupportedReadMultiOpSet',        c_u64, 32), #0x1B0
                ('EnabledReadMultiOpSet',          c_u64, 32),
                ('R2',                             c_u64, 64), #0x1B8
                ]

    _ptr_fields = ['NextOpcodeSetPtr']

    _special_dict = { 'Control1'                      : OpCodeSetIDControl1,
                      'SupportedCore64OpCodeSet'      : Core64Opcodes,
                      'EnabledCore64OpCodeSet'        : Core64Opcodes,
                      'SupportedControlOpCodeSet'     : ControlOpcodes,
                      'EnabledControlOpCodeSet'       : ControlOpcodes,
                      'SupportedP2P64OpCodeSet'       : P2P64Opcodes,
                      'EnabledP2P64OpCodeSet'         : P2P64Opcodes,
                      'SupportedAtomic1OpCodeSet'     : Atomic1Opcodes,
                      'EnabledAtomic1OpCodeSet'       : Atomic1Opcodes,
                      'SupportedLDM1OpCodeSet'        : LDM1Opcodes,
                      'EnabledLDM1OpCodeSet'          : LDM1Opcodes,
                      'SupportedAdvanced1OpCodeSet'   : Adv1Opcodes,
                      'EnabledAdvanced1OpCodeSet'     : Adv1Opcodes,
                      'SupportedAdvanced2OpCodeSet'   : Adv2Opcodes,
                      'EnabledAdvanced2OpCodeSet'     : Adv2Opcodes,
                      'SupportedDROpCodeSet'          : DROpcodes,
                      'EnabledDROpCodeSet'            : DROpcodes,
                      'SupportedCtxIdOpCodeSet'       : CtxIdOpcodes,
                      'EnabledCtxIdOpCodeSet'         : CtxIdOpcodes,
                      'SupportedMulticastOpCodeSet'   : MulticastOpcodes,
                      'EnabledMulticastOpCodeSet'     : MulticastOpcodes,
                      'SupportedSODOpCodeSet'         : SODOpcodes,
                      'EnabledSODOpCodeSet'           : SODOpcodes,
                      # Revisit: jmh - finish this - MultiOp
                      }

# factory class to dynamically build OpCodeSetTable
class OpCodeSetTableFactory(ControlTable):
    def from_buffer_kw(data, offset=0, **kwargs):
        sz = len(data)
        opcode_set = OpCodeSetTable.from_buffer(data, offset)
        if opcode_set.Version == 0:
            fields = OpCodeSetTableTemplate._fields + OpCodeSetTableTemplate._v0_fields
        elif opcode_set.Version == 1:
            fields = OpCodeSetTableTemplate._fields + OpCodeSetTableTemplate._v1_fields
        else: # unknown version - guess format based on sz
            if sz == 432:
                fields = OpCodeSetTableTemplate._fields + OpCodeSetTableTemplate._v0_fields
            else:
                fields = OpCodeSetTableTemplate._fields + OpCodeSetTableTemplate._v1_fields
        OpCodeSet = type('OpCodeSetTable',
                         (OpCodeSetTableTemplate,), {'_fields_': fields,
                                                     'Size': sz})
        return OpCodeSet.from_buffer(data, offset)

class OpCodeSetTable(ControlTable):
    _fields_ = OpCodeSetTableTemplate._fields

@add_from_buffer_kw
class OpCodeSetUUIDTable(ControlTable):
    _fields_ = [('SupportedP2PVdefSet',            c_u64, 64),
                ('EnabledP2PVdefSet',              c_u64, 64),
                ('SupportedVDO1OpCodeSet',         c_u64, 64),
                ('EnabledVDO1OpCodeSet',           c_u64, 64),
                ('SupportedVDO2OpCodeSet',         c_u64, 64),
                ('EnabledVDO2OpCodeSet',           c_u64, 64),
                ('SupportedVDO3OpCodeSet',         c_u64, 64),
                ('EnabledVDO3OpCodeSet',           c_u64, 64),
                ('SupportedVDO4OpCodeSet',         c_u64, 64),
                ('EnabledVDO4OpCodeSet',           c_u64, 64),
                ('SupportedVDO5OpCodeSet',         c_u64, 64),
                ('EnabledVDO5OpCodeSet',           c_u64, 64),
                ('SupportedVDO6OpCodeSet',         c_u64, 64),
                ('EnabledVDO6OpCodeSet',           c_u64, 64),
                ('SupportedVDO7OpCodeSet',         c_u64, 64),
                ('EnabledVDO7OpCodeSet',           c_u64, 64),
                ('SupportedVDO8OpCodeSet',         c_u64, 64),
                ('EnabledVDO8OpCodeSet',           c_u64, 64),
                ('SupportedP2P264SubOpReqSetl',    c_u64, 64),
                ('SupportedP2P264SubOpReqSeth',    c_u64, 64),
                ('EnabledP2P264SubOpReqSetl',      c_u64, 64),
                ('EnabledP2P264SubOpReqSeth',      c_u64, 64),
                ('SupportedP2P264SubOpRspSetl',    c_u64, 64),
                ('SupportedP2P264SubOpRspSeth',    c_u64, 64),
                ('EnabledP2P264SubOpRspSetl',      c_u64, 64),
                ('EnabledP2P264SubOpRspSeth',      c_u64, 64),
                ('PMUUIDl',                        c_u64, 64),
                ('PMUUIDh',                        c_u64, 64),
                ('VDO1UUIDl',                      c_u64, 64),
                ('VDO1UUIDh',                      c_u64, 64),
                ('VDO2UUIDl',                      c_u64, 64),
                ('VDO2UUIDh',                      c_u64, 64),
                ('VDO3UUIDl',                      c_u64, 64),
                ('VDO3UUIDh',                      c_u64, 64),
                ('VDO4UUIDl',                      c_u64, 64),
                ('VDO4UUIDh',                      c_u64, 64),
                ('VDO5UUIDl',                      c_u64, 64),
                ('VDO5UUIDh',                      c_u64, 64),
                ('VDO6UUIDl',                      c_u64, 64),
                ('VDO6UUIDh',                      c_u64, 64),
                ('VDO7UUIDl',                      c_u64, 64),
                ('VDO7UUIDh',                      c_u64, 64),
                ('VDO8UUIDl',                      c_u64, 64),
                ('VDO8UUIDh',                      c_u64, 64),
                ]

    _uuid_fields = [('PMUUIDh',   'PMUUIDl'),
                    ('VDO1UUIDh', 'VDO1UUIDl'),
                    ('VDO2UUIDh', 'VDO2UUIDl'),
                    ('VDO3UUIDh', 'VDO3UUIDl'),
                    ('VDO4UUIDh', 'VDO4UUIDl'),
                    ('VDO5UUIDh', 'VDO5UUIDl'),
                    ('VDO6UUIDh', 'VDO6UUIDl'),
                    ('VDO7UUIDh', 'VDO7UUIDl'),
                    ('VDO8UUIDh', 'VDO8UUIDl')]

    _uuid_dict = dict(zip([item for sublist in zip(*_uuid_fields) for item in sublist],
                          _uuid_fields * 2))

# base class from which to dynamically build InterfaceStructure
class InterfaceTemplate(ControlStructure):
    _fields  = [('Type',                       c_u64, 12), #0x0
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('InterfaceID',                c_u64, 12),
                ('HVS',                        c_u64,  5),
                ('R0',                         c_u64,  7),
                ('PHYPowerEnb',                c_u64,  8),
                ('IStatus',                    c_u64, 32), #0x8
                ('IControl',                   c_u64, 32),
                ('ICAP1',                      c_u64, 32), #0x10
                ('ICAP1Control',               c_u64, 32),
                ('ICAP2',                      c_u64, 32), #0x18
                ('ICAP2Control',               c_u64, 32),
                ('IErrorStatus',               c_u64, 16), #0x20
                ('IErrorDetect',               c_u64, 16),
                ('IErrorFaultInj',             c_u64, 16),
                ('IErrorTrig',                 c_u64, 16),
                ('IErrorSigTgt',               c_u64, 48), #0x28
                ('TETH',                       c_u64,  4),
                ('TETE',                       c_u64,  4),
                ('FCFWDProgress',              c_u64,  8),
                ('LLTxPktAlignment',           c_u64,  8), #0x30
                ('LLRxPktAlignment',           c_u64,  8),
                ('MaxImplicitFCCredits',       c_u64, 16),
                ('PeerInterfaceID',            c_u64, 12),
                ('R1',                         c_u64,  4),
                ('PeerBaseCClass',             c_u64, 16),
                ('PeerCID',                    c_u64, 12), #0x38
                ('R2',                         c_u64,  4),
                ('PeerSID',                    c_u64, 16),
                ('PeerState',                  c_u64, 32),
                ('PathPropagationTime',        c_u64, 16), #0x40
                ('TRIndex',                    c_u64,  4),
                ('TRCID',                      c_u64, 12),
                ('VCPCOEnabled',               c_u64, 32),
                ('EETxPktAlignment',           c_u64,  8), #0x48
                ('EERxPktAlignment',           c_u64,  8),
                ('EETxMinPktStart',            c_u64,  8),
                ('EERxMinPktStart',            c_u64,  8),
                ('HVE',                        c_u64,  5),
                ('R3',                         c_u64,  9),
                ('TTCUnit',                    c_u64,  2),
                ('PeerComponentTTC',           c_u64, 16),
                ('PeerNonce',                  c_u64, 64), #0x50
                ('AggregationSup',             c_u64,  8), #0x58
                ('CLPCTL',                     c_u64,  4),
                ('CDLPCTL',                    c_u64,  4),
                ('MaxPHYRetrainEvents',        c_u64,  8),
                ('TxLLRTACK',                  c_u64, 20),
                ('RxLLRTACK',                  c_u64, 20),
                ('TEHistoryThresh',            c_u64, 12), #0x60
                ('R4',                         c_u64, 20),
                ('LinkCTLControl',             c_u64, 32),
                ('R5',                         c_u64, 64), #0x68
                ('NextInterfacePTR',           c_u64, 32), #0x70
                ('R6',                         c_u64, 32),
                ('NextAIPTR',                  c_u64, 32), #0x78
                ('NextIGPTR',                  c_u64, 32),
                ('IPHYPTR',                    c_u64, 32), #0x80
                ('ISTATSPTR',                  c_u64, 32),
                ('MechanicalPTR',              c_u64, 32), #0x88
                ('VDPTR',                      c_u64, 32),
                ]

    _optional_fields = [
                ('VCATPTR',                    c_u64, 32), #0x90
                ('LPRTPTR',                    c_u64, 32),
                ('MPRTPTR',                    c_u64, 32), #0x98
                ('R7',                         c_u64, 32),
                ('IngressAKeyMask',            c_u64, 64), #0xA0
                ('EgressAKeyMask',             c_u64, 64), #0xA8
                ]

    #_ptr_fields = ['NextIPTR', 'IPHYPTR', 'VDPTR', 'ISTATSPTR', 'IARBPTR', 'MechanicalPTR']
    _special_dict = {'IStatus': IStatus, 'IControl': IControl,
                     'ICAP1': ICAP1, 'ICAP1Control': ICAP1Control,
                     'ICAP2': ICAP2, 'ICAP2Control': ICAP2Control,
                     'IErrorStatus': IErrorStatus, 'IErrorDetect': IErrorDetect,
                     'IErrorFaultInj': IErrorFaultInj, 'IErrorTrig': IErrorTrig,
                     'PeerState': PeerState, 'LinkCTLControl': LinkCTLControl}

    def __str__(self):
        r = super().__str__()
        if self.verbosity == 1:
            istatus = IStatus(self.IStatus, self)
            r = f'{istatus.istate:6s}'
            peer_state = PeerState(self.PeerState, self)
            cstate = CState(peer_state.PeerCState)
            peer_cid = self.PeerCID if peer_state.field.PeerCIDValid else None
            peer_sid = (self.PeerSID if peer_state.field.PeerSIDValid else
                        0) # Revisit
            try:
                peer_gcid = GCID(sid=peer_sid, cid=peer_cid)
            except TypeError:
                peer_gcid = None
            peer_iface = (self.PeerInterfaceID
                          if peer_state.field.PeerIfaceIDValid == 1 else None)
            if peer_gcid:
                r += f' Peer {peer_gcid}.{peer_iface} ({cstate})'
            elif istatus.IState != IState.IDown:
                r += f' Peer GCID Not Set ({cstate})'
        return r

# factory class to dynamically build InterfaceStructure
class InterfaceFactory(ControlStructure):
    def from_buffer_kw(data, offset=0, **kwargs):
        sz = len(data)
        if sz > 0x90: # Revisit: hardcoded value
            fields = InterfaceTemplate._fields + InterfaceTemplate._optional_fields
        else:
            fields = InterfaceTemplate._fields
        Interface = type('InterfaceStructure',
                         (InterfaceTemplate,), {'_fields_': fields,
                                                'Size': sz})
        return Interface.from_buffer(data, offset)

class InterfaceStructure(ControlStructure):
    _fields_ = InterfaceTemplate._fields

@add_from_buffer_kw
class InterfacePHYStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),  # Basic PHY Fields
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('PHYType',                    c_u64,  8),
                ('TxDLY',                      c_u64,  4),
                ('R0',                         c_u64, 20),
                ('NextIPHYPTR',                c_u64, 32),
                ('VDPTR',                      c_u64, 32),
                ('PHYStatus',                  c_u64, 32),
                ('PHYControl',                 c_u64, 32),
                ('PHYCAP1',                    c_u64, 32),
                ('PHYCAP1Control',             c_u64, 32),
                ('PHYEvents',                  c_u64, 32),
                ('R1',                         c_u64, 32),
                ('R2',                         c_u64, 64),
                ('PHYLaneStatus',              c_u64, 32),
                ('PHYLaneControl',             c_u64, 32),
                ('PHYLaneCAP',                 c_u64, 32),
                ('PHYRemoteLaneCAP',           c_u64, 32),
                ('PHYLPCAP',                   c_u64, 32),
                ('PHYLPTimingCAP',             c_u64, 32),
                ('PHYUPLPCAP',                 c_u64, 32),
                ('PHYUPLPTimingCAP',           c_u64, 32),
                ('PHYExtendedStatus',          c_u64, 32),
                ('PHYExtendedControl',         c_u64, 32),
                ('PHYExtendedCAP',             c_u64, 32),
                ('PHYRemoteExtendedCAP',       c_u64, 32),
                # Revisit: figure out how to handle PHY-specific fields
                ]

    _special_dict = {'PHYType': PHYType, 'PHYStatus': PHYStatus}

@add_from_buffer_kw
class ComponentPAStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('PACAP1',                     c_u64, 32),
                ('PACAP1Control',              c_u64, 32),
                ('SSAPSz',                     c_u64, 12),
                ('MCAPSz',                     c_u64, 12),
                ('R0',                         c_u64,  3),
                ('PadSz',                      c_u64,  5),
                ('PASz',                       c_u64, 16),
                ('R1',                         c_u64, 16),
                ('MSAPSz',                     c_u64, 28),
                ('R2',                         c_u64,  4),
                ('MSMCAPSz',                   c_u64, 28),
                ('R3',                         c_u64,  4),
                ('PAPTR',                      c_u64, 32),
                ('SSAPPTR',                    c_u64, 32),
                ('MSAPPTR',                    c_u64, 32),
                ('MCAPPTR',                    c_u64, 32),
                ('MSMCAPPTR',                  c_u64, 32),
                ('R4',                         c_u64, 64),
                ('R5',                         c_u64, 64),
                ('R6',                         c_u64, 32),
                ('WildcardPA',                 c_u64, 16),
                ('WildcardAKey',               c_u64,  6),
                ('WACREQ',                     c_u64,  2),
                ('WACRSP',                     c_u64,  2),
                ('R7',                         c_u64,  6),
                ('R8',                         c_u64, 64),
                ('MSEUUIDl',                   c_u64, 64),
                ('MSEUUIDh',                   c_u64, 64),
                ]

    _uuid_fields = [('MSEUUIDh', 'MSEUUIDl')]

    _uuid_dict = dict(zip([item for sublist in zip(*_uuid_fields) for item in sublist],
                          _uuid_fields * 2))

    _special_dict = {'PACAP1': PACAP1, 'PACAP1Control': PACAP1Control}

@add_from_buffer_kw
class ComponentCAccessStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('NextCAccessPTR',             c_u64, 32),
                ('CPageSz',                    c_u64,  4),
                ('R0',                         c_u64,  8),
                ('BaseAddr',                   c_u64, 40),
                ('CAccessCAP1',                c_u64,  4),
                ('CAccessCTL',                 c_u64,  8),
                ('CAccessTableSz',             c_u64, 40),
                ('R1',                         c_u64, 24),
                ('CAccessRKeyPTR',             c_u64, 32),
                ('CAccessLP2PPTR',             c_u64, 32),
                ]

    _special_dict = {'CPageSz': CPageSz, 'CAccessCAP1': CAccessCAP1,
                     'CAccessCTL': CAccessCTL}

@add_from_buffer_kw
class ComponentErrorSignalStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12), # 0x0
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('EControl',                   c_u64, 16),
                ('EStatus',                    c_u64, 16),
                ('ErrorMgrCID',                c_u64, 12), # 0x8
                ('ErrorMgrSID',                c_u64, 16),
                ('R0',                         c_u64,  4),
                ('ErrSigCAP1',                 c_u64, 16),
                ('ErrSigCAP1Control',          c_u64, 16),
                ('EventMgrCID',                c_u64, 12), # 0x10
                ('EventMgrSID',                c_u64, 16),
                ('R1',                         c_u64,  4),
                ('ELogPTR',                    c_u64, 32),
                ('SigIntrAddr0',               c_u64, 64), # 0x18
                ('SigIntrAddr1',               c_u64, 64), # 0x20
                ('SigIntrData0',               c_u64, 32), # 0x28
                ('SigIntrData1',               c_u64, 32),
                ('CErrorStatus',               c_u64, 64), # 0x30
                ('CErrorDetect',               c_u64, 64), # 0x38
                ('R2',                         c_u64, 64), # 0x40
                ('CErrorTrig',                 c_u64, 64), # 0x48
                ('CErrorFaultInj',             c_u64, 64), # 0x50
                ('CErrorSigTgtl',              c_u64, 64), # 0x58
                ('CErrorSigTgtm',              c_u64, 64), # 0x60
                ('CErrorSigTgth',              c_u64, 64), # 0x68
                ('CEventDetect',               c_u64, 64), # 0x70
                ('CEventInj',                  c_u64, 64), # 0x78
                ('CEventSigTgtl',              c_u64, 64), # 0x80
                ('CEventSigTgtm',              c_u64, 64), # 0x88
                ('CEventSigTgth',              c_u64, 64), # 0x90
                ('IEventDetect',               c_u64, 64), # 0x98
                ('IEventInj',                  c_u64, 64), # 0xa0
                ('IEventSigTgtl',              c_u64, 64), # 0xa8
                ('IEventSigTgtm',              c_u64, 64), # 0xb0
                ('IEventSigTgth',              c_u64, 64), # 0xb8
                # MVk/MgmtVCk/MgmtIfacek are for UEPs
                ('MV0',                        c_u64,  1), # 0xc0
                ('MgmtVC0',                    c_u64,  5),
                ('MgmtIface0',                 c_u64, 12),
                ('MV1',                        c_u64,  1),
                ('MgmtVC1',                    c_u64,  5),
                ('MgmtIface1',                 c_u64, 12),
                ('MV2',                        c_u64,  1),
                ('MgmtVC2',                    c_u64,  5),
                ('MgmtIface2',                 c_u64, 12),
                ('R3',                         c_u64, 10),
                ('MV3',                        c_u64,  1), # 0xc8
                ('MgmtVC3',                    c_u64,  5),
                ('MgmtIface3',                 c_u64, 12),
                ('MV4',                        c_u64,  1),
                ('MgmtVC4',                    c_u64,  5),
                ('MgmtIface4',                 c_u64, 12),
                ('MV5',                        c_u64,  1),
                ('MgmtVC5',                    c_u64,  5),
                ('MgmtIface5',                 c_u64, 12),
                ('R4',                         c_u64, 10),
                ('MV6',                        c_u64,  1), # 0xd0
                ('MgmtVC6',                    c_u64,  5),
                ('MgmtIface6',                 c_u64, 12),
                ('MV7',                        c_u64,  1),
                ('MgmtVC7',                    c_u64,  5),
                ('MgmtIface7',                 c_u64, 12),
                ('R5',                         c_u64, 28),
                ('PMUEPMask',                  c_u64,  8), # 0xd8
                ('PFMUEPMask',                 c_u64,  8),
                ('SFMUEPMask',                 c_u64,  8),
                ('ErrorUEPMask',               c_u64,  8),
                ('EventUEPMask',               c_u64,  8),
                ('MediaUEPMask',               c_u64,  8),
                ('PwrMgrUEPMask',              c_u64,  8),
                ('MechMgrUEPMask',             c_u64,  8),
                ('MechMgrCID',                 c_u64, 12), #0xe0
                ('MechMgrSID',                 c_u64, 16),
                ('R6',                         c_u64,  4),
                ('MediaMgrCID',                c_u64, 12),
                ('MediaMgrSID',                c_u64, 16),
                ('R7',                         c_u64,  4),
                ('R8',                         c_u64, 64), #0xe8
                ('EControl2',                  c_u64, 32), #0xf0
                ('R9',                         c_u64, 32),
                ('CEventStatus',               c_u64, 64), #0xf8
                ('IEventStatus',               c_u64, 64), #0x100
                ('R10',                        c_u64, 64), #0x108
                ]

    _special_dict = {'EControl': EControl, 'EControl2': EControl2,
                     'EStatus': EStatus, 'ErrSigCAP1': ErrSigCAP1,
                     'ErrSigCAP1Control': ErrSigCAP1Control,
                     'CErrorStatus': CErrorStatus, 'CErrorDetect': CErrorDetect,
                     'CErrorTrig': CErrorTrig, 'CErrorFaultInj': CErrorFaultInj,
                     'CEventStatus': CEventStatus, 'CEventDetect': CEventDetect,
                     'CEventInj': CEventInj,
                     'IEventStatus': IEventStatus, 'IEventDetect': IEventDetect,
                     'IEventInj': IEventInj,
                     # Revisit: CErrorSigTgt, CEventSigTgt, IEventSigTgt
                     }

@add_from_buffer_kw
class ComponentPageGridStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('PTETableSz',                 c_u64, 32),
                ('PGZMMUCAP1',                 c_u64, 32),
                ('PGZMMUCAP1Control',          c_u64, 32),
                ('PGTableSz',                  c_u64,  8),
                ('PTESz',                      c_u64, 10),
                ('R0',                         c_u64, 46),
                ('PGBasePTR',                  c_u64, 32),
                ('PTEBasePTR',                 c_u64, 32),
                ('VDefPTR',                    c_u64, 32),
                ('NextCompPGPTR',              c_u64, 32),
                ('RestrictedPGBasePTR',        c_u64, 32),
                ('RestrictedPTEBasePTR',       c_u64, 32),
                ('PTEATTRl',                   c_u64, 64),
                ('PTEATTRh',                   c_u64, 64),
                ('R1',                         c_u64, 64),
                ('ZMMUSupPageSizes',           c_u64, 52),
                ('R2',                         c_u64, 12),
                ('PGPTEUUIDl',                 c_u64, 64),
                ('PGPTEUUIDh',                 c_u64, 64),
                ]

    _uuid_fields = [('PGPTEUUIDh', 'PGPTEUUIDl')]

    _uuid_dict = dict(zip([item for sublist in zip(*_uuid_fields) for item in sublist],
                          _uuid_fields * 2))

    _special_dict = {'PGZMMUCAP1': PGZMMUCAP1, 'PTEATTRl': PTEATTRl}

@add_from_buffer_kw
class ComponentPageTableStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('VDefPTR',                    c_u64, 32),
                ('PTZMMUCAP1',                 c_u64, 32),
                ('PTZMMUCAP1Control',          c_u64, 32),
                ('PTECachePTR',                c_u64, 32),
                ('PTECacheLen',                c_u64, 32),
                ('PTAddr',                     c_u64, 64),
                ('PTEATTRl',                   c_u64, 64),
                ('PTEATTRh',                   c_u64, 64),
                ('R0',                         c_u64, 32),
                ('NextCompPTPTR',              c_u64, 32),
                ('SupPageSizes',               c_u64, 52),
                ('PTESz',                      c_u64, 10),
                ('R1',                         c_u64,  2),
                ('PTPTEUUIDl',                 c_u64, 64),
                ('PTPTEUUIDh',                 c_u64, 64),
                ]

    _uuid_fields = [('PTPTEUUIDh', 'PTPTEUUIDl')]

    _uuid_dict = dict(zip([item for sublist in zip(*_uuid_fields) for item in sublist],
                          _uuid_fields * 2))

    _special_dict = {'PTZMMUCAP1': PTZMMUCAP1, 'PTEATTRl': PTEATTRl}

@add_from_buffer_kw
class ComponentPrecisionTimeStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12), #0x0
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('PTCAP1',                     c_u64, 16),
                ('PTCTL',                      c_u64, 16),
                ('GTCCID',                     c_u64, 12), #0x8
                ('R0',                         c_u64,  4),
                ('GTCSID',                     c_u64, 16),
                ('PTRspCID',                   c_u64, 12),
                ('R1',                         c_u64,  4),
                ('PTRspSID',                   c_u64, 16),
                ('AltPTRspCID',                c_u64, 12), #0x10
                ('TC',                         c_u64,  4),
                ('AltPTRspSID',                c_u64, 16),
                ('CompPTGranularity',          c_u64, 10),
                ('PTDGranularity',             c_u64, 10),
                ('PTDIface',                   c_u64, 12),
                ('AltPTDIface',                c_u64, 12), #0x18
                ('R2',                         c_u64, 20),
                ('NextPTPTR',                  c_u64, 32),
                ('MasterTime',                 c_u64, 64), #0x20 Not in v1.1e
                ('LocalOffset',                c_u64, 64), #0x28 Not in v1.1e
                ('PTRT',                       c_u64, 40), #0x30 Not in v1.1e
                ('R3',                         c_u64, 24),     # Not in v1.1e
                ('R4',                         c_u64, 64), #0x38 Not in v1.1e
                ]

    _special_dict = {'PTCAP1': PTCAP1, 'PTCTL': PTCTL}

@add_from_buffer_kw
class ComponentSwitchStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('SwitchCAP1',                 c_u64, 32),
                ('SwitchCAP1Control',          c_u64, 32),
                ('SwitchStatus',               c_u64, 16),
                ('SwitchOpCTL',                c_u64, 16),
                ('LPRTSize',                   c_u64, 12),
                ('HCSize',                     c_u64,  4),
                ('MHCSize',                    c_u64,  4),
                ('MaxRoutes',                  c_u64, 12),
                ('UVCATSZ',                    c_u64,  5),
                ('MVCATSZ',                    c_u64,  5),
                ('MCPRTMSMCPRTPadSize',        c_u64,  5),
                ('R0',                         c_u64, 17),
                ('LPRTMPRTRowSize',            c_u64, 16),
                ('MCPRTMSMCPRTRowSize',        c_u64, 16),
                ('DefaultMCEgressIface',       c_u64, 12),
                ('DefaultCollEgressIface',     c_u64, 12),
                ('R1',                         c_u64,  8),
                ('MaxULAT',                    c_u64, 16),
                ('MaxMLAT',                    c_u64, 16),
                ('MCPRTSize',                  c_u64, 12),
                ('R2',                         c_u64, 20),
                ('MPRTSize',                   c_u64, 16),
                ('R3',                         c_u64, 16),
                ('MSMCPRTSize',                c_u64, 28),
                ('R4',                         c_u64,  4),
                ('MVCATPTR',                   c_u64, 32),
                ('RtCtlPTR',                   c_u64, 32),
                ('MCPRTPTR',                   c_u64, 32),
                ('MSMCPRTPTR',                 c_u64, 32),
                ('MCEUUIDl',                   c_u64, 64),
                ('MCEUUIDh',                   c_u64, 64),
                # MVk/MgmtVCk/MgmtIfacek are for UnrelCtlWriteMSG
                ('MV0',                        c_u64,  1),
                ('MgmtVC0',                    c_u64,  5),
                ('MgmtIface0',                 c_u64, 12),
                ('MV1',                        c_u64,  1),
                ('MgmtVC1',                    c_u64,  5),
                ('MgmtIface1',                 c_u64, 12),
                ('MV2',                        c_u64,  1),
                ('MgmtVC2',                    c_u64,  5),
                ('MgmtIface2',                 c_u64, 12),
                ('R5',                         c_u64, 10),
                ('MV3',                        c_u64,  1),
                ('MgmtVC3',                    c_u64,  5),
                ('MgmtIface3',                 c_u64, 12),
                ('R6',                         c_u64, 46),
                ('R7',                         c_u64, 64),
                ('R8',                         c_u64, 64),
                ]

    _uuid_fields = [('MCEUUIDh', 'MCEUUIDl')]

    _uuid_dict = dict(zip([item for sublist in zip(*_uuid_fields) for item in sublist],
                          _uuid_fields * 2))

    _special_dict = {'SwitchCAP1': SwitchCAP1,
                     'SwitchCAP1Control': SwitchCAP1Control,
                     'SwitchOpCTL': SwitchOpCTL}

@add_from_buffer_kw
class MaxSIClassArray(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Per-Service MaxSI/Class Fields
        fields = [('Class',              c_u32, 16),
                  ('MaxSI',              c_u32, 16),
                  ]
        MaxSIClass = type('MaxSIClass', (ControlTableElement,), {'_fields_': fields,
                                                             'verbosity': self.verbosity,
                                                             'Size': 4}) # Revisit
        elems = self.parent.SUUIDTableSz
        self.array = (MaxSIClass * elems).from_buffer(self.data, self.offset)
        self.element = MaxSIClass

    def __format__(self, spec):
        return 'maxsi-class' # Revisit: fix this

# base class from which to dynamically build ServiceUUIDStructure
class ServiceUUIDTemplate(ControlStructure):
    _fields  = [('Type',                       c_u64, 12), #0x0
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('SUUIDTableSz',               c_u64, 16),
                ('R0',                         c_u64, 16),
                ('SUUIDPTR',                   c_u64, 32), #0x8
                ('R1',                         c_u64, 32),
                ]
    _arr =  [('MaxSIClassArray',            MaxSIClassArray), #0x10
                ]

    def fileToStructInit(self):
        super().fileToStructInit()
        self.embeddedArray = self.MaxSIClassArray.fileToStruct('MaxSIClassArray',
                                    self.data,
                                    verbosity=self.verbosity, fd=self.fd,
                                    path=self.path, parent=self,
                                    core=self.core, offset=self.offset+16)

# factory class to dynamically build ServiceUUIDStructure
class ServiceUUIDFactory(ControlStructure):
    def from_buffer_kw(data, offset=0, **kwargs):
        sz = len(data)
        serv = ServiceUUIDStructure.from_buffer(data, offset)
        elems = serv.sz_0_special(serv.SUUIDTableSz, 16)
        fields = ServiceUUIDTemplate._fields + ServiceUUIDTemplate._arr
        ServeUUID = type('ServiceUUIDStructure',
                         (ServiceUUIDTemplate,), {'_fields_': fields,
                                                  'arrElems': elems,
                                                  'Size': sz})
        return ServeUUID.from_buffer(data, offset)

class ServiceUUIDStructure(ControlStructure):
    _fields_ = ServiceUUIDTemplate._fields

@add_from_buffer_kw
class BaseLenArray(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Per-Service Base/Len Fields
        fields = [('DSBase',                     c_u64, 52), #0x0
                  ('R0',                         c_u64, 12),
                  ('DSLen',                      c_u64, 52), #0x8
                  ('R1',                         c_u64, 12),
                  ('CSBase',                     c_u64, 40), #0x10
                  ('R2',                         c_u64,  4),
                  ('InstanceID',                 c_u64, 20),
                  ('CSLen',                      c_u64, 40), #0x18
                  ('R3',                         c_u64, 24),
                  ]
        BaseLen = type('BaseLen', (ControlTableElement,), {'_fields_': fields,
                                                        'verbosity': self.verbosity,
                                                        'Size': 32}) # Revisit
        #set_trace() # Revisit: temp debug
        elems = self.parent.arrElems # parent is ServiceUUIDTableElement
        self.array = (BaseLen * elems).from_buffer(self.data, self.offset)
        self.element = BaseLen

    def __format__(self, spec):
        return 'base-len' # Revisit: fix this

# base class from which to dynamically build ServiceUUIDTableElement
class ServiceUUIDTableElementTemplate(ControlTable):
    _fields  = [('ServiceUUIDl',   c_u64, 64), #0x0
                ('ServiceUUIDh',   c_u64, 64),
                ]
    _arr =  [('BaseLenArray',            BaseLenArray), #0x10
                ]

    _uuid_fields = [('ServiceUUIDh', 'ServiceUUIDl')]

    _uuid_dict = dict(zip([item for sublist in zip(*_uuid_fields) for item in sublist],
                          _uuid_fields * 2))

    @property
    def ServiceUUID(self): # Revisit: generate this (and others) from _uuid_fields
        return self.uuid(('ServiceUUIDh', 'ServiceUUIDl'))

    def fileToStructInit(self):
        self.embeddedArray = self.BaseLenArray.fileToStruct('BaseLenArray',
                                    self.data,
                                    verbosity=self.verbosity, fd=self.fd,
                                    path=self.path, parent=self,
                                    core=self.core, offset=self.offset+16)

# factory class to dynamically build ServiceUUIDTableElement
class ServiceUUIDTableElementFactory(ControlTable):
    def from_buffer_kw(data, offset=0, parent=None, elems=None, verbosity=0):
        sz = len(data)
        #set_trace() # Revisit: temp debug
        fields = (ServiceUUIDTableElementTemplate._fields +
                  ServiceUUIDTableElementTemplate._arr)
        ServUUIDElem = type('ServiceUUIDTableElement',
                            (ServiceUUIDTableElementTemplate,),
                            {'_fields_': fields,
                             'arrElems': elems,
                             'verbosity': verbosity,
                             'Size': sz})
        return ServUUIDElem.from_buffer(data, offset)

@add_from_buffer_kw
class ServiceUUIDTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        elems = self.parent.SUUIDTableSz # parent is ServiceUUIDStructure
        offset = 0
        #set_trace() # Revisit: temp debug
        self.array = []
        for i in range(elems):
            maxSI = self.parent.embeddedArray[i].MaxSI
            sz = 16 + (maxSI * 32)
            serv = ServiceUUIDTableElementFactory.from_buffer_kw(
                self.data, self.offset + offset,
                parent=self, elems=maxSI, verbosity=self.verbosity)
            self.array.extend([serv])
            serv.data = self.data
            serv.offset = self.offset + offset
            serv.verbosity = self.verbosity
            serv.fd = self.fd
            serv.path = self.path
            serv.parent = self.parent
            serv.core = self.core
            serv._stat = None
            serv._size = sz
            serv.fileToStructInit()
            offset += sz

    def cs_offset(self, row, *unused):
        '''Each element may have a different size, so the standard
        method of doing "sizeof(element) * row" will not work.
        Instead, each array element stores its offset.
        '''
        return self.array[row].cs_offset

@add_from_buffer_kw
class VendorDefinedStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12), #0x0
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('VdefData0',                  c_u64, 32),
                ('VdefData1',                  c_u64, 64)]
    # Revisit: print rest of structure in hex?

@add_from_buffer_kw
class VendorDefinedUUIDStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12), #0x0
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('VdefData0',                  c_u64, 32),
                ('VdefData1',                  c_u64, 64),
                ('VDUUIDl',                    c_u64, 64),
                ('VDUUIDh',                    c_u64, 64),
    ]
    # Revisit: print rest of structure in hex?

    _uuid_fields = [('VDUUIDh',   'VDUUIDl')]

    _uuid_dict = dict(zip([item for sublist in zip(*_uuid_fields) for item in sublist],
                          _uuid_fields * 2))

class UnknownStructure(ControlStructure):
    _fields_ = [('Type',                       c_u32, 12),
                ('Vers',                       c_u32,  4),
                ('Size',                       c_u32, 16)]
    # Revisit: print rest of structure in hex?

class ControlTableElement(ControlStructure):
    def __str__(self):
        if self.verbosity <= 4:
            return super().__repr__()
        return super().__str__()

@add_from_buffer_kw
class PATable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('OpCodeSetTableID',   c_u16,  3),
                  ('LatencyDomain',      c_u16,  1),
                  ('PeerNextHdrEnb',     c_u16,  1),
                  ('Rv1',                c_u16,  1),
                  ('PeerPrecTimeEnb',    c_u16,  1),
                  ('PeerAEADEnb',        c_u16,  1),
                  ('Rv2',                c_u16,  2),
                  ('WriteMSGEmbedRdEnb', c_u16,  1),
                  ('MetaRdWrEnb',        c_u16,  1),
                  ('Rv4',                c_u16,  4),
        ]
        PA = type('PA', (ControlTableElement,), {'_fields_': fields,
                                              'verbosity': self.verbosity,
                                              'Size': 2}) # Revisit
        items = self.Size // sizeof(PA)
        self.array = (PA * items).from_buffer(self.data)
        self.element = PA

class RKDArray(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('RKDAuth',  c_u64, 64)
        ]
        RKD = type('RKD', (ControlTableElement,), {'_fields_': fields,
                                                   'verbosity': self.verbosity,
                                                   'Size': 8}) # Revisit
        items = 64 # always 64 elements
        self.array = (RKD * items).from_buffer(self.data, self.offset)
        self.element = RKD

@add_from_buffer_kw
class ComponentRKDStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('RKDCAP1',                    c_u64, 16),
                ('RKDControl1',                c_u64, 16),
                ('R0',                         c_u64, 64),
                ('AuthArray',                  RKDArray)
                ]

    _special_dict = {'RKDCAP1': RKDCAP1, 'RKDControl1': RKDControl1}

    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: saving as self.AuthArray doesn't work
        self.embeddedArray = self.AuthArray.fileToStruct('RKDArray', self.data,
                                    verbosity=self.verbosity, fd=self.fd,
                                    path=self.path, parent=self,
                                    core=self.core, offset=self.offset+0x10)

    def assign_rkd(self, rkd, val) -> int:
        row = rkd // 64
        bit = rkd % 64
        mask = 1 << bit
        rkdAuth = self.embeddedArray[row].RKDAuth
        rkdAuth &= ~mask
        if val:
            rkdAuth |= mask
        self.embeddedArray[row].RKDAuth = rkdAuth
        return row

@add_from_buffer_kw
class IStatsVCArray(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Per-VC Relay Statistics Fields
        fields = [('TotalXmitPkts',              c_u64, 64), #0x50/0x90
                  ('TotalXmitBytes',             c_u64, 64), #0x58/0x98
                  ('TotalRecvPkts',              c_u64, 64), #0x60/0xA0
                  ('TotalRecvBytes',             c_u64, 64), #0x68/0xA8
                  ('Occupancy',                  c_u64, 64), #0x70/0xB0
                  ]
        IStatsVC = type('IStatsVC', (ControlTableElement,), {'_fields_': fields,
                                                             'verbosity': self.verbosity,
                                                             'Size': 40}) # Revisit
        sz = self.Size - self.parent.relayOff
        items = sz // 40
        self.array = (IStatsVC * items).from_buffer(self.data, self.offset)
        self.element = IStatsVC

# base class from which to dynamically build InterfaceStatisticsStructure
class InterfaceStatisticsTemplate(ControlStructure):
                # Structure Header/Control/PTRs
    _control = [('Type',                       c_u64, 12), #0x0
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('IStatCAP1',                  c_u64, 16),
                ('IStatControl',               c_u64,  8),
                ('IStatStatus',                c_u64,  8),
                ('VendorDefinedPTR',           c_u64, 32), #0x8
                ('ISnapshotPTR',               c_u64, 32),
                ]
                # Common Statistics Fields
    _common =  [('ISnapshotInterval',          c_u64, 64), #0x10 snapshot starts here
                ('PCRCErrors',                 c_u64, 32), #0x18
                ('ECRCErrors',                 c_u64, 32),
                ('TxStompedECRC',              c_u64, 32), #0x20
                ('RxStompedECRC',              c_u64, 32),
                ('NonCRCTransientErrors',      c_u64, 32), #0x28
                ('LLRRecovery',                c_u64, 32),
                ('PktDeadlineDiscards',        c_u64, 32), #0x30
                ('MarkedECN',                  c_u64, 32),
                ('ReceivedECN',                c_u64, 32), #0x38
                ('LinkNTE',                    c_u64, 16),
                ('AKEYViolations',             c_u64, 16),
                ('R0',                         c_u64, 64), #0x40
                ('R1',                         c_u64, 64), #0x48
                ]
                # Requester/Responder Statistics Fields
    _req_rsp = [('TotalXmitReqs',              c_u64, 64), #0x50
                ('TotalXmitReqBytes',          c_u64, 64), #0x58
                ('TotalRecvReqs',              c_u64, 64), #0x60
                ('TotalRecvReqBytes',          c_u64, 64), #0x68
                ('TotalXmitRsps',              c_u64, 64), #0x70
                ('TotalXmitRspBytes',          c_u64, 64), #0x78
                ('TotalRecvRsps',              c_u64, 64), #0x80
                ('TotalRecvRspBytes',          c_u64, 64), #0x88
                ]
    _vc_arr =  [('VCArray',                    IStatsVCArray), #0x50/0x90
                ]

    _fields = _control + _common

    _relay_offset = (0x50, 0x90) # Revisit: hardcoded values

    _special_dict = {'IStatStatus': IStatStatus, 'IStatControl': IStatControl,
                     'IStatCAP1': IStatCAP1}

    @staticmethod
    def fields_relay_offset(cls, cap1):
        if cap1.ProvisionedStatsFields == ProvisionedIStats.Common:
            fields = cls._fields
            relay_offset = 0
        elif cap1.ProvisionedStatsFields == ProvisionedIStats.CommonReqRsp:
            fields = cls._fields + cls._req_rsp
            relay_offset = 0
        elif cap1.ProvisionedStatsFields == ProvisionedIStats.CommonPktRelay:
            fields = cls._fields
            relay_offset = cls._relay_offset[0]
        else:  # CommonReqRspPktRelay
            fields = cls._fields + cls._req_rsp
            relay_offset = cls._relay_offset[1]
        return (fields, relay_offset)

    def fileToStructInit(self):
        super().fileToStructInit()
        if self.relayOff > 0:
            # Revisit: saving as self.VCArray doesn't work
            self.embeddedArray = self.VCArray.fileToStruct('IStatsVCArray', self.data,
                                    verbosity=self.verbosity, fd=self.fd,
                                    path=self.path, parent=self,
                                    core=self.core, offset=self.offset+self.relayOff)
        else:
            self.embeddedArray = None

# factory class to dynamically build InterfaceStatisticsStructure
class InterfaceStatisticsFactory(ControlStructure):
    def from_buffer_kw(data, offset=0, **kwargs):
        sz = len(data)
        elems = 0
        stats = InterfaceStatisticsStructure.from_buffer(data, offset)
        cap1 = IStatCAP1(stats.IStatCAP1, stats)
        fields, relay_offset = InterfaceStatisticsTemplate.fields_relay_offset(
            InterfaceStatisticsTemplate, cap1)
        if relay_offset > 0:
            elems = (sz - relay_offset) // (5 * 8) # Revisit: hardcoded value
            fields.extend(InterfaceStatisticsTemplate._vc_arr)
        InterfaceStats = type('InterfaceStatisticsStructure',
                         (InterfaceStatisticsTemplate,), {'_fields_': fields,
                                                          'relayOff': relay_offset,
                                                          'vcElems': elems,
                                                          'Size': sz})
        return InterfaceStats.from_buffer(data, offset)

class InterfaceStatisticsStructure(ControlStructure):
    _fields_ = InterfaceStatisticsTemplate._fields

# base class from which to dynamically build ISnapshotTable
class ISnapshotTemplate(ControlTable):
    _fields = InterfaceStatisticsTemplate._common

    _req_rsp = InterfaceStatisticsTemplate._req_rsp

    _vc_arr = InterfaceStatisticsTemplate._vc_arr

    _relay_offset = (0x40, 0x80) # Revisit: hardcoded values

    def fileToStructInit(self):
        super().fileToStructInit()
        if self.relayOff > 0:
            # Revisit: saving as self.VCArray doesn't work
            self.embeddedArray = self.VCArray.fileToStruct('IStatsVCArray', self.data,
                                    verbosity=self.verbosity, fd=self.fd,
                                    path=self.path, parent=self,
                                    core=self.core, offset=self.offset+self.relayOff)
        else:
            self.embeddedArray = None

# factory class to dynamically build ISnapshotTable
class ISnapshotFactory(ControlTable):
    def from_buffer_kw(data, offset=0, parent=None):
        sz = len(data)
        elems = 0
        cap1 = IStatCAP1(parent.IStatCAP1, parent)
        fields, relay_offset = InterfaceStatisticsTemplate.fields_relay_offset(
            ISnapshotTemplate, cap1)
        if relay_offset > 0:
            elems = (sz - relay_offset) // (5 * 8) # Revisit: hardcoded value
            fields.extend(ISnapshotTemplate._vc_arr)
        ISnapshot = type('ISnapshotTable',
                         (ISnapshotTemplate,), {'_fields_': fields,
                                                          'relayOff': relay_offset,
                                                          'vcElems': elems,
                                                          'Size': sz})
        return ISnapshot.from_buffer(data, offset)

class ISnapshotTable(ControlTable):
    _fields_ = InterfaceStatisticsTemplate._common

@add_from_buffer_kw
class RequesterVCATTable(ControlTable2DArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('VCM',       c_u32, 32)
        ]
        sz = 4
        if self.parent.HCS:
            fields.extend([('TH', c_u32, 7), ('R0', c_u32, 25)])
            sz = 8
        VCAT = type('VCAT', (ControlTableElement,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': sz})
        rows = 16  # always 16 rows
        cols = self.sz_0_special(self.parent.REQVCATSZ, 5)
        self.array = ((VCAT * cols) * rows).from_buffer(self.data)
        self.element = VCAT

@add_from_buffer_kw
class ResponderVCATTable(ControlTable2DArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('VCM',       c_u32, 32)
        ]
        sz = 4
        if self.parent.HCS:
            fields.extend([('TH', c_u32, 7), ('R0', c_u32, 25)])
            sz = 8
        VCAT = type('VCAT', (ControlTableElement,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': sz})
        items = self.Size // sizeof(VCAT)
        cols = self.sz_0_special(self.parent.RSPVCATSZ, 5)
        rows = items // cols
        self.array = ((VCAT * cols) * rows).from_buffer(self.data)
        self.element = VCAT

@add_from_buffer_kw
class VCATTable(ControlTable2DArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('VCM',       c_u32, 32)
        ]
        sz = 4
        if self.core.sw.HCS:
            fields.extend([('TH', c_u32, 7), ('R0', c_u32, 25)])
            sz = 8
        VCAT = type('VCAT', (ControlTableElement,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': sz})
        items = self.Size // sizeof(VCAT)
        cols = self.sz_0_special(self.core.sw.UVCATSZ, 5)
        rows = items // cols
        self.array = ((VCAT * cols) * rows).from_buffer(self.data)
        self.element = VCAT

@add_from_buffer_kw
class RITTable(ControlTableArray):
    fullEntryWrite = True

    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: need parent/core so we can dynamically build RIT based on
        # MaxInterface, RITPadSize, etc.
        fields = [('EIM',       c_u32, 32)
        ]
        RIT = type('RIT', (ControlTableElement,), {'_fields_': fields,
                                                'verbosity': self.verbosity,
                                                'Size': 4}) # Revisit
        items = self.Size // sizeof(RIT)
        self.array = (RIT * items).from_buffer(self.data)
        self.element = RIT

# for SSDT, MSDT, LPRT, and MPRT
class SSDTMSDTLPRTMPRTTable(ControlTable2DArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('MHC',       c_u32,  6),
                  ('R0',        c_u32,  2),
                  ('V',         c_u32,  1),
                  ('HC',        c_u32,  6),
                  ('VCA',       c_u32,  5),
                  ('EI',        c_u32, 12),
        ]
        SSDT = type(self._name, (ControlTableElement,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 4})
        rows = self.rows
        cols = self.cols
        self.array = ((SSDT * cols) * rows).from_buffer(self.data)
        self.element = SSDT

    def __str__(self):
        r = type(self).__name__
        if self.verbosity < 2:
            return r
        r += ':\n'
        if self.verbosity < 4:
            return r
        elif self.verbosity == 4:
            name = type(self.array[0][0]).__name__
            for i in range(self.rows):
                v0 = self.array[i][0].V
                for j in range(self.cols):
                    v = self.array[i][j].V
                    if v and not v0: # include 0th col (for MHC)
                        r += '    {}[{}][{}]={}\n'.format(name, i, 0,
                                                      repr(self.array[i][0]))
                        v0 = True
                    if v:
                        r += '    {}[{}][{}]={}\n'.format(name, i, j,
                                                      repr(self.array[i][j]))
        else:
            # Revisit: the str() output should be indented another 2 spaces
            name = type(self.array[0][0]).__name__
            for i in range(self.rows):
                v0 = self.array[i][0].V if self.verbosity < 6 else 1
                for j in range(self.cols):
                    v = self.array[i][j].V if self.verbosity < 6 else 1
                    if v and not v0: # include 0th col (for MHC)
                        r += '    {}[{}][{}]={}\n'.format(name, i, 0,
                                                      str(self.array[i][0]))
                        v0 = True
                    if v:
                        r += '    {}[{}][{}]={}\n'.format(name, i, j,
                                                      str(self.array[i][j]))

        return r

@add_from_buffer_kw
class SSDTTable(SSDTMSDTLPRTMPRTTable):
    @property
    def rows(self):
        return self.sz_0_special(self.parent.SSDTSize, 12)

    @property
    def cols(self):
        return self.parent.MaxRoutes

    def fileToStructInit(self):
        self._name = 'SSDT'
        super().fileToStructInit()

@add_from_buffer_kw
class MSDTTable(SSDTMSDTLPRTMPRTTable):
    @property
    def rows(self):
        return self.sz_0_special(self.parent.MSDTSize, 16)

    @property
    def cols(self):
        return self.parent.MaxRoutes

    def fileToStructInit(self):
        self._name = 'MSDT'
        super().fileToStructInit()

@add_from_buffer_kw
class LPRTTable(SSDTMSDTLPRTMPRTTable):
    @property
    def rows(self):
        return self.sz_0_special(self.core.sw.LPRTSize, 12)

    @property
    def cols(self):
        return self.core.sw.MaxRoutes

    def fileToStructInit(self):
        self._name = 'LPRT'
        super().fileToStructInit()

@add_from_buffer_kw
class MPRTTable(SSDTMSDTLPRTMPRTTable):
    @property
    def rows(self):
        return self.sz_0_special(self.core.sw.MPRTSize, 12)

    @property
    def cols(self):
        return self.core.sw.MaxRoutes

    def fileToStructInit(self):
        self._name = 'MPRT'
        super().fileToStructInit()

# for SSAP, MCAP, MSAP, and MSMCAP
class SSAPMCAPMSAPMSMCAPTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # use parent to dynamically build SSAP entry based on PAIdxSz & PadSz
        cap1 = PACAP1(self.parent.PACAP1, self.parent)
        self.pa_idx_sz = cap1.PAIdxSz * 8  # bytes to bits
        self.wc_akey = cap1.WildcardAKeySup
        self.wc_pa = cap1.WildcardPASup
        self.wc_acreq = cap1.WildcardACREQSup
        self.wc_acrsp = cap1.WildcardACRSPSup
        pad_sz = self.parent.PadSz
        fields = []
        if self.pa_idx_sz > 0:
            fields.append(('PAIdx',       c_u32,  self.pa_idx_sz))
        # Revisit: Gen-Z Core spec v1.1e does not state whether fields
        # corresponding to supported wildcards are Reserved or non-existent
        # This assumes non-existent.
        if not self.wc_akey:
            fields.append(('AKey',        c_u32,  6))
        if not self.wc_acreq:
            fields.append(('ACREQ',       c_u32,  2))
        if not self.wc_acrsp:
            fields.append(('ACRSP',       c_u32,  2))
        if pad_sz > 0:
            fields.append(('Pad',         c_u32,  pad_sz))
        SSAP = type(self._name, (ControlTableElement,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 4})
        items = self.Size // sizeof(SSAP)
        self.array = (SSAP * items).from_buffer(self.data)
        self.element = SSAP

@add_from_buffer_kw
class SSAPTable(SSAPMCAPMSAPMSMCAPTable):
    def fileToStructInit(self):
        self._name = 'SSAP'
        super().fileToStructInit()

@add_from_buffer_kw
class MCAPTable(SSAPMCAPMSAPMSMCAPTable):
    def fileToStructInit(self):
        self._name = 'MCAP'
        super().fileToStructInit()

@add_from_buffer_kw
class MSAPTable(SSAPMCAPMSAPMSMCAPTable):
    def fileToStructInit(self):
        self._name = 'MSAP'
        super().fileToStructInit()

@add_from_buffer_kw
class MSMCAPTable(SSAPMCAPMSAPMSMCAPTable):
    def fileToStructInit(self):
        self._name = 'MSMCAP'
        super().fileToStructInit()

@add_from_buffer_kw
class CAccessRKeyTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('RORKey',      c_u64, 32),
                  ('RWRKey',      c_u64, 32),
        ]
        RKey = type('RKey', (ControlTableElement,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 8})
        items = self.Size // sizeof(RKey)
        self.array = (RKey * items).from_buffer(self.data)
        self.element = RKey

@add_from_buffer_kw
class CAccessLP2PTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: decode subfield values
        fields = [('LAC',         c_u8,  3),
                  ('P2PAC',       c_u8,  3),
                  ('Rv',          c_u8,  2),
        ]
        LP2P = type('LP2P', (ControlTableElement,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 1})
        items = self.Size // sizeof(LP2P)
        self.array = (LP2P * items).from_buffer(self.data)
        self.element = LP2P

@add_from_buffer_kw
class PGTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('R0',          c_u64, 12),
                  ('PGBaseAddr',  c_u64, 52),
                  ('PageSz',      c_u64,  7),
                  ('RES',         c_u64,  1),
                  ('PageCount',   c_u64, 24),
                  ('BasePTEIdx',  c_u64, 32),
        ]
        PG = type('PG', (ControlTableElement,), {'_fields_': fields,
                                              'verbosity': self.verbosity,
                                              'Size': 16})
        items = self.Size // sizeof(PG)
        self.array = (PG * items).from_buffer(self.data)
        self.element = PG

def pte_ro_rkey_get(self):
    return (self.RORKeyh << self.ro_rkey_l_bits) | self.RORKeyl

def pte_ro_rkey_set(self, val):
    self.RORKeyl = val & ((1 << self.ro_rkey_l_bits) - 1)
    self.RORKeyh = val >> self.ro_rkey_l_bits

def pte_rw_rkey_get(self):
    return (self.RWRKeyh << self.rw_rkey_l_bits) | self.RWRKeyl

def pte_rw_rkey_set(self, val):
    self.RWRKeyl = val & ((1 << self.rw_rkey_l_bits) - 1)
    self.RWRKeyh = val >> self.rw_rkey_l_bits

def pte_addr_get(self):
    return (self.ADDRh << self.addr_l_bits) | self.ADDRl

def pte_addr_set(self, val):
    self.ADDRl = val & ((1 << self.addr_l_bits) - 1)
    self.ADDRh = val >> self.addr_l_bits

@add_from_buffer_kw
class PTETable(ControlTableArray):
    def splitField(self, fld, bits):
        fld_bits = fld[2]
        remain = 64 - (bits % 64)
        if fld_bits <= remain:
            return [fld]
        fldL = (fld[0] + 'l', fld[1], remain)
        fldH = (fld[0] + 'h', fld[1], fld_bits - remain)
        return [fldL, fldH]

    def padFields(self, bits, pte_sz):
        idx = 0
        flds = []
        remain = pte_sz - bits
        while remain > 0:
            pad_bits = 64 - (bits % 64)
            pad = ('R{}'.format(idx), c_u64, pad_bits)
            flds.append(pad)
            bits += pad_bits
            remain -= pad_bits
            idx += 1
        return flds

    def reqPteFields(self, pte_sz, cap1, attr):
        bits = 0
        fields = [('V',         c_u64,  1)] # the only required, fixed, field
        bits += fields[-1][2]
        if isinstance(self.parent, ComponentPageTableStructure):
            fields.append(('ET',        c_u64,  1))
            bits += fields[-1][2]
        fields.append(('DATTR',         c_u64,  3))
        bits += fields[-1][2]
        if attr.field.STDRCSup:
            fields.extend([('ST',       c_u64,  1),
                           ('DRCPP',    c_u64,  1)])
            bits += 2
        if attr.field.CCESup:
            fields.append(('CCE',       c_u64,  1))
            bits += fields[-1][2]
        if attr.field.CESup:
            fields.append(('CE',        c_u64,  1))
            bits += fields[-1][2]
        if attr.field.WPESup:
            fields.append(('WPE',       c_u64,  1))
            bits += fields[-1][2]
        pasid_sz = attr.field.PASIDSz
        if pasid_sz > 0:
            fields.append(('PSE',       c_u64,  1))
            bits += fields[-1][2]
        if attr.field.PFMESup:
            fields.append(('PFME',      c_u64,  1))
            bits += fields[-1][2]
        if attr.field.PECSup:
            fields.append(('PEC',       c_u64,  1))
            bits += fields[-1][2]
        if attr.field.LPESup:
            fields.append(('LPE',       c_u64,  1))
            bits += fields[-1][2]
        if attr.field.NSESup:
            fields.append(('NSE',       c_u64,  1))
            bits += fields[-1][2]
        fields.append(('WriteMode',     c_u64,  3))
        bits += fields[-1][2]
        if attr.field.TCSz == 1:
            fields.append(('TC',        c_u64,  4))
            bits += fields[-1][2]
        if pasid_sz > 0: # max 20 bits
            fields.append(('PASID',     c_u64, pasid_sz))
            bits += fields[-1][2]
        fields.append(('LclDest',       c_u64, 12))
        bits += fields[-1][2]
        # everything above is guaranteed to fit in the first c_u64
        # but any field below might need to be split across two c_u64s
        gbl_sz = attr.field.GdSz
        if gbl_sz > 0: # max 16 bits
            fields.extend(self.splitField(('GblDest', c_u64, gbl_sz), bits))
            bits += gbl_sz
        if attr.field.TRIdxSup:
            fields.extend(self.splitField(('TRIdx',   c_u64,  4), bits))
            bits += 4
        if attr.field.COSup:
            fields.extend(self.splitField(('CO',      c_u64,  2), bits))
            bits += 2
        if attr.field.RKeySup:
            fields.extend(self.splitField(('RKey',    c_u64, 32), bits))
            bits += 32
        fields.extend(self.splitField(('ADDR',        c_u64, 52), bits))
        bits += 52
        fields.extend(self.padFields(bits, pte_sz))
        # Revisit: return "need" values like rspPteFields
        return (fields, 0, 0, 0)

    def rspPteFields(self, pte_sz, cap1, attr):
        bits = 0
        fields = [('V',         c_u64,  1)] # the only required, fixed, field
        bits += fields[-1][2]
        if isinstance(self.parent, ComponentPageTableStructure):
            fields.append(('ET',        c_u64,  1))
            bits += fields[-1][2]
        if attr.field.PASup:
            fields.append(('PA',        c_u64,  1))
            bits += fields[-1][2]
        if attr.field.CCESup:
            fields.append(('CCE',       c_u64,  1))
            bits += fields[-1][2]
        if attr.field.CESup:
            fields.append(('CE',        c_u64,  1))
            bits += fields[-1][2]
        if attr.field.WPESup:
            fields.append(('WPE',       c_u64,  1))
            bits += fields[-1][2]
        pasid_sz = attr.field.PASIDSz
        if pasid_sz > 0:
            fields.append(('PSE',       c_u64,  1))
            bits += fields[-1][2]
        if attr.field.LPESup:
            fields.append(('LPE',       c_u64,  1))
            bits += fields[-1][2]
        if attr.field.IESup:
            fields.append(('IE',        c_u64,  1))
            bits += fields[-1][2]
        if attr.field.PFERSup:
            fields.append(('PFER',      c_u64,  1))
            bits += fields[-1][2]
        if attr.field.RkMgrCIDSup:
            fields.append(('RkMgr',     c_u64,  2))
            bits += fields[-1][2]
        if pasid_sz > 0: # max 20 bits
            fields.append(('PASID',     c_u64, pasid_sz))
            bits += fields[-1][2]
        if attr.field.RkMgrCIDSup:
            fields.append(('RkMgrCID',  c_u64, 12))
            bits += fields[-1][2]
        rk_mgr_sid_sz = attr.field.RkMgrSIDSz
        if rk_mgr_sid_sz > 0: # max 16 bits
            fields.append(('RkMgrSID',  c_u64, rk_mgr_sid_sz))
            bits += rk_mgr_sid_sz
        # everything above is guaranteed to fit in the first c_u64
        # but any field below might need to be split across two c_u64s
        if attr.field.RKeySup:
            s = self.splitField(('RORKey',  c_u64, 32), bits)
            needRORKey = s[0][2] if len(s) > 1 else 0
            fields.extend(s)
            bits += 32
            s = self.splitField(('RWRKey',  c_u64, 32), bits)
            needRWRKey = s[0][2] if len(s) > 1 else 0
            fields.extend(s)
            bits += 32
        else:
            needRORKey = 0
            needRWRKey = 0
        a_sz = attr.field.ASz
        if a_sz > 0: # max 64 bits
            s = self.splitField(('ADDR',    c_u64, a_sz), bits)
            needADDR = s[0][2] if len(s) > 1 else 0
            fields.extend(s)
            bits += a_sz
        else:
            needADDR = 0
        w_sz = attr.field.WSz
        if w_sz > 0: # max 64 bits
            fields.extend(self.splitField(('WinSz',   c_u64, w_sz), bits))
            bits += w_sz
        fields.extend(self.padFields(bits, pte_sz))
        return (fields, needRORKey, needRWRKey, needADDR)

    def fileToStructInit(self):
        super().fileToStructInit()
        # use parent to dynamically build PTE based on PTESz, PTEATTRl, etc.
        pte_sz = self.parent.PTESz  # in bits, guaranteed to be 32-bit multiple
        pte_bytes = pte_sz // 8
        cap1 = PGZMMUCAP1(self.parent.PGZMMUCAP1, self.parent)
        attr = PTEATTRl(self.parent.PTEATTRl, self.parent)
        if attr.zmmuType == 0:
            (fields, needRORKey, needRWRKey, needADDR) = self.reqPteFields(pte_sz, cap1, attr)
            pfx = 'Req'
        else:
            (fields, needRORKey, needRWRKey, needADDR) = self.rspPteFields(pte_sz, cap1, attr)
            pfx = 'Rsp'
        pte_dict = {'_fields_': fields,
                    'verbosity': self.verbosity,
                    'Size': pte_bytes}
        if needRORKey:
            pte_dict['ro_rkey_l_bits'] = needRORKey
            pte_dict['RORKey'] = property(pte_ro_rkey_get, pte_ro_rkey_set)
        if needRWRKey:
            pte_dict['rw_rkey_l_bits'] = needRWRKey
            pte_dict['RWRKey'] = property(pte_rw_rkey_get, pte_rw_rkey_set)
        if needADDR:
            pte_dict['addr_l_bits'] = needADDR
            pte_dict['ADDR'] = property(pte_addr_get, pte_addr_set)
        PTE = type('{}PTE'.format(pfx), (ControlTableElement,), pte_dict)
        items = self.Size // sizeof(PTE)
        self.array = (PTE * items).from_buffer(self.data)
        self.element = PTE

@add_from_buffer_kw
class RouteControlTable(ControlTable):
    _fields_ = [('RCCAP1',                         c_u64, 16),
                ('R0',                             c_u64, 10),
                ('DHC',                            c_u64,  6),
                ('ReqSimulTable',                  c_u64, 16),
                ('R1',                             c_u64, 16),
                ('ReqLocalTableFirst',             c_u64, 16),
                ('R2',                             c_u64, 16),
                ('ReqThreshEnb',                   c_u64, 16),
                ('R3',                             c_u64, 16),
                ('RspSimulTable',                  c_u64, 32),
                ('RspLocalTableFirst',             c_u64, 32),
                ('RspThreshEnb',                   c_u64, 32),
                ('RelaySimulTable',                c_u64, 32),
                ('RelayLocalTableFirst',           c_u64, 32),
                ('RelayThreshEnb',                 c_u64, 32),
                ('R4',                             c_u64, 32),
                ('R5',                             c_u64, 32),
                ]

    _special_dict = {'RCCAP1': RCCAP1}

class UEPEventRecord(ControlTable):
    _fields_ = [('A',                              c_u32,  1), #0x0
                ('Vers',                           c_u32,  2),
                ('CV',                             c_u32,  1),
                ('SV',                             c_u32,  1),
                ('GC',                             c_u32,  1),
                ('IV',                             c_u32,  1),
                ('R0',                             c_u32,  1),
                ('Event',                          c_u32,  8),
                ('R1',                             c_u32,  4),
                ('IfaceID',                        c_u32, 12),
                ('SCID',                           c_u32, 12), #0x4
                ('SSID',                           c_u32, 16),
                ('R2',                             c_u32,  4),
                ('RCCID',                          c_u32, 12), #0x8
                ('RCSID',                          c_u32, 16),
                ('R3',                             c_u32,  4),
                ('ES',                             c_u32, 32), #0xC
                ('EventID',                        c_u32, 16), #0x10
                ('R4',                             c_u32, 16),
                ]

    def __init__(self, verbosity=0, **kwargs):
        if 'EventName' in kwargs:
            del kwargs['EventName']
        self.Vers = 1
        super().__init__(verbosity=verbosity, **kwargs)

    def dataToRec(data, verbosity=0, csv=False):
        rec = UEPEventRecord.from_buffer(data)
        rec.data = data
        rec.verbosity = verbosity
        rec.csv = csv
        return rec

    def to_json(self):
        d = {}
        for field in self._fields_:
            name = field[0]
            # Revisit: skip Reserved fields
            d[name] = getattr(self, name)
        d['EventName'] = self.EventName
        return d

    @property
    def EventName(self):
        return (eventName[self.Event] if self.Event
                in eventName else 'Reserved')

    @property
    def Size(self):
        return 20

class Packet(LittleEndianStructure):
    _ocl = OpClasses()

    def __init__(self, verbosity=0, csv=False, data=None, **kwargs):
        self.data = data
        self.verbosity = verbosity
        self.csv = csv
        super().__init__(**kwargs)

    def bitField(self, width, bitOffset):
        byteOffset = bitOffset // 32 * 8
        lowBit = bitOffset % 32
        highBit = lowBit + width - 1
        hexWidth = (width + 3) // 4
        return (byteOffset, highBit, lowBit, hexWidth)

    def dataToPkt(data, verbosity=0, csv=False):
        # Revisit: other packet types (like P2P)
        pkt = ExplicitReqPkt.from_buffer(data)
        pkt.data = data
        pkt.verbosity = verbosity
        pkt.csv = csv
        return pkt.dataToPktInit(data, verbosity, csv)

    def uuid(self, uuidField):
        # Revisit: this is wrong for packets
        # UUIDs are stored big-endian, but this class is a
        # LittleEndianStructure, so use byteorder='little'
        w0 = getattr(self, uuidField[0])
        w1 = getattr(self, uuidField[1])
        w2 = getattr(self, uuidField[2])
        w3 = getattr(self, uuidField[3])
        return uuid.UUID(bytes=(w3 << 96 | w2 << 64 | w1 << 32 | w0).to_bytes(
            16, byteorder='little'))

    @property
    def uuids(self):
        if hasattr(self, '_uuid_fields'):
            for uuidField in self._uuid_fields:
                uu = self.uuid(uuidField)
                yield (uuidField[0], uuidField[1], uuidField[2], uuidField[3], uu)

    def isUuid(self, field):
        if hasattr(self, '_uuid_dict'):
            uuid_tuple = self._uuid_dict.get(field)
            if uuid_tuple is not None:
                return self.uuid(uuid_tuple)
        return None

    def multicast(self):
        return False

    def reliable(self):
        return True

    @staticmethod
    def className(ocl, opcode):
        return Packet._ocl.name(ocl) + Packet._ocl.opClass(ocl).name(opcode)

    @staticmethod
    def pay_len_and_pad_cnt(payloadLen):
        payLen4 = ceil_div(payloadLen, 4)
        padLen = payLen4 * 4 - payloadLen
        return (payLen4, padLen)

    def set_payload(self, payload, payLen = None):
        if payLen is None:
            payLen = len(payload)
        payLen4, padCnt = Packet.pay_len_and_pad_cnt(payLen)
        # Revisit: check payLen4 against self.pay_len
        pptr = (c_u8 * payLen).from_buffer(payload)
        memmove(self.Payload, pptr, payLen)
        self.PadCNT = padCnt

    def __len__(self):
        return self.LEN * 4

def PacketFactory(oclName: str, opcName: str, payLen: int = 0,
                  GC: bool = False, NH: bool = False, RK: bool = False,
                  RT: bool = False, verbosity = 0, csv = False, **kwargs):
    ocl = Packet._ocl.ocl(oclName)
    opclass = Packet._ocl.opClass(ocl)
    opcode = opclass.opCode(opcName)
    pkt = globals()[oclName + opcName + 'Pkt'](ocl, opcode, payLen,
                                               verbosity=verbosity,
                                               GC=GC, NH=NH, RK=RK, RT=RT,
                                               **kwargs)
    return pkt

class ExplicitHdr(Packet):
    ecrc = crcmod.mkCrcFun(0xade27a<<1|1, initCrc=0, xorOut=0xffffff, rev=True)

    # pcrc_table generated by pycrc and hand-converted to python:
    # pycrc.py --width 6 --poly 0x2f --reflect-in 1 --reflect-out 1 \
    #    --xor-in 0x3f --xor-out 0x3f --algorithm tbl --table-idx-width 4 \
    #    --generate c --symbol-prefix pcrc_ -o pcrc_tbl.c
    pcrc_table = [0x00, 0x16, 0x2c, 0x3a, 0x23, 0x35, 0x0f, 0x19,
                  0x3d, 0x2b, 0x11, 0x07, 0x1e, 0x08, 0x32, 0x24]

    hd_fields = [('DCIDl',                      c_u32,  5), # Byte 0
                 ('LENl',                       c_u32,  3),
                 ('DCIDm',                      c_u32,  4),
                 ('LENh',                       c_u32,  4),
                 ('DCIDh',                      c_u32,  3),
                 ('VC',                         c_u32,  5),
                 ('OpCodel',                    c_u32,  2),
                 ('PCRC',                       c_u32,  6),
                 ('OpCodeh',                    c_u32,  3), # Byte 4
                 ('OCL',                        c_u32,  5),
                 ('Tag',                        c_u32, 12),
                 ('SCID',                       c_u32, 12),
                 ('AKey',                       c_u32,  6), # Byte 8
                 ('Deadline',                   c_u32, 10),
                 ('ECN',                        c_u32,  1),
                 ('GC',                         c_u32,  1),
                 ('NH',                         c_u32,  1),
                 ('PM',                         c_u32,  1)]
    # OS1 is in each individual packet format
    ms_fields = [('DSID',                       c_u32, 16),
                 ('SSID',                       c_u32, 16)]
    rk_fields = [('RKey',                       c_u32, 32)]
    # Revisit: LPD fields
    nh_fields = [('NextHdr0',                   c_u32, 32),
                 ('NextHdr1',                   c_u32, 32),
                 ('NextHdr2',                   c_u32, 32),
                 ('NextHdr3',                   c_u32, 32)]

    def __init__(self, ocl, opcode, pktLen4,
                 verbosity=0, csv=False, data=None, **kwargs):
        super().__init__(verbosity=verbosity, csv=csv, data=data, **kwargs)
        self.OCL = ocl
        self.OpCode = opcode
        self.LEN = pktLen4

    def dataToPktInit(self, data, verbosity, csv):
        try:
            oclName = self.oclName
            opcName = self.opcName
            pkt = globals()[oclName + opcName + 'Pkt'].dataToPktInit(
                self, data, verbosity)
            pkt.data = data
            pkt.verbosity = verbosity
            pkt.csv = csv
            return pkt
        except:
            return self

    @property
    def DCID(self):
        return self.DCIDh << 9 | self.DCIDm << 5 | self.DCIDl

    @DCID.setter
    def DCID(self, val: int) -> None:
        if val < 0 or val > 4095:
            raise(ValueError)
        self.DCIDh = (val >> 9) & 0x7
        self.DCIDm = (val >> 5) & 0xf
        self.DCIDl = val & 0x1f

    @property
    def LEN(self):
        return self.LENh << 3 | self.LENl

    @LEN.setter
    def LEN(self, val:int) -> None:
        if val < 4 or val > 126:
            raise(ValueError)
        self.LENh = (val >> 3) & 0xf
        self.LENl = val & 0x7

    @property
    def OpCode(self):
        return self.OpCodeh << 2 | self.OpCodel

    @OpCode.setter
    def OpCode(self, val:int) -> None:
        if val < 0 or val > 31:
            raise(ValueError)
        self.OpCodeh = (val >> 2) & 0x7
        self.OpCodel = val & 0x3

    @property
    def oclName(self):
        #return self._ocl.name(self.OCL)
        try:
            name = self._ocl.name(self.OCL)
        except KeyError:
            name = 'Unknown'
        return name

    @property
    def DGCID(self):
        return self.DCID if not self.GC else (self.DSID << 12) | self.DCID

    @property
    def SGCID(self):
        return self.SCID if not self.GC else (self.SSID << 12) | self.SCID

    @property
    def isRequest(self):
        return self.OpCode >= 4

    @property
    def isResponse(self):
        return not self.isRequest

    @property
    def isRead(self):
        return hasattr(self, 'Addr') and hasattr(self, 'RDSize')

    @property
    def isWrite(self):
        return hasattr(self, 'Addr') and self.pay_len is not None

    def pcrc_init(self) -> int:
        return 0x3f

    def pcrc_finalize(self, crc: int) -> int:
        return crc ^ 0x3f

    def compute_pcrc(self) -> int:
        data = self.VC << 7 | self.LEN
        crc = self.pcrc_init()
        tbl_idx = crc ^ data
        crc = self.pcrc_table[tbl_idx & 0x0f] ^ (crc >> 4)
        tbl_idx = crc ^ (data >> 4);
        crc = self.pcrc_table[tbl_idx & 0x0f] ^ (crc >> 4)
        tbl_idx = crc ^ (data >> 8);
        crc = self.pcrc_table[tbl_idx & 0x0f] ^ (crc >> 4)

        return self.pcrc_finalize(crc & 0x3f)

    def chk_pcrc(self, crc=None) -> int:
        if crc is None:
            crc = self.compute_pcrc()
        return 0 if crc == self.PCRC else 1 if crc == 0 else -1

    @property
    def pcrc_sep(self) -> str:
        chk = self.chk_pcrc()
        return ' ' if chk == 0 else '?' if chk == 1 else '!'

    @property
    def expected_pcrc_str(self) -> str:
        if self.verbosity > 1 and not self.csv:
            crc = self.compute_pcrc()
            if self.chk_pcrc(crc) != 0:
                return f'[{crc:02x}]'
        return ''

    def compute_ecrc(self) -> int:
        return ExplicitHdr.ecrc(bytearray(self)[0:self.LEN*4-3])

    def chk_ecrc(self, crc=None) -> int:
        if crc is None:
            crc = self.compute_ecrc()
        return 0 if crc == self.ECRC else 1 if crc == 0xc0ffee else -1

    @property
    def ecrc_sep(self) -> str:
        chk = self.chk_ecrc()
        return ' ' if chk == 0 else '?' if chk == 1 else '!'

    @property
    def expected_ecrc_str(self) -> str:
        if self.verbosity > 1 and not self.csv:
            crc = self.compute_ecrc()
            if self.chk_ecrc(crc) != 0:
                return f'[{crc:06x}]'
        return ''

    def set_crcs(self):
        self.PCRC = self.compute_pcrc()
        self.ECRC = self.compute_ecrc()

    @property
    def uniqueness(self):
        if self.isRequest:
            return (self.SGCID << 40) | (self.DGCID << 12) | self.Tag
        else: # isResponse - swap SGCID/DGCID so it matches request
            return (self.DGCID << 40) | (self.SGCID << 12) | self.Tag

    @property
    def opcName(self):
        try:
            name = self._ocl.opClass(self.OCL).name(self.OpCode)
        except KeyError:
            name = 'Unknown'
        return name

    def to_json(self):
        jd = { 'name': type(self).__name__,
               'OCL': self.OCL,
               'OpCode': self.OpCode,
               'LEN': self.LEN,
               'VC': self.VC,
               'PCRC': self.PCRC,
               'DCID': self.DCID,
               'SCID': self.SCID,
               'ECRC': self.ECRC,
               'AKey': self.AKey,
               'Deadline': self.Deadline,
               'ECN': self.ECN,
               'GC': self.GC,
               'NH': self.NH,
               'PM': self.PM,
               # Revisit: finish this
              }
        noTag = getattr(self, 'noTag', False)
        if not noTag:
            jd['Tag'] = self.Tag
        return jd

    def __str__(self):
        noTag = getattr(self, 'noTag', False)
        r = ('{}' if self.csv else '{:>23s}').format(type(self).__name__)
        if self.csv or type(self).__name__[0:8] != 'Explicit':
            r += (',{},{}' if self.csv else '[{:02x}:{:02x}]').format(self.OCL, self.OpCode)
        else:
            r += ' OpClass: {}({:02x}), OpCode: {}({:02x})'.format(
                self.oclName, self.OCL, self.opcName, self.OpCode)
        r += (',{}' if self.csv else ', Length: {:2d}').format(self.LEN)
        if self.GC:
            # Revisit: CSV format
            try: # Revisit: workaround for Unknown packets
                r += ', SGCID: {:04x}:{:03x}, DGCID: {:04x}:{:03x}'.format(
                    self.SSID, self.SCID, self.DSID, self.DCID)
            except AttributeError:
                r += ', SGCID: ????:{:03x}, DGCID: ????:{:03x}'.format(
                    self.SCID, self.DCID)
        else:
            r += (',{},{}' if self.csv else ', SCID: {:03x}, DCID: {:03x}').format(self.SCID, self.DCID)
        r += (',{}' if self.csv else ', R0:  {:03x}' if noTag else ', Tag: {:03x}').format(
            self.Tag)
        r += (',{},{}' if self.csv else
              ', VC: {0}, PCRC:{2}{1:02x}').format(
            self.VC, self.PCRC, self.pcrc_sep)
        r += self.expected_pcrc_str
        r += (',{},{},{},{},{},{}' if self.csv else
              ', AKey: {:02x}, Deadline: {:4d}, ECN: {}, GC: {}, NH: {}, PM: {}').format(
            self.AKey, self.Deadline, self.ECN, self.GC, self.NH, self.PM)
        return r

class ExplicitReqHdr(ExplicitHdr):
    rq_fields = [('LP',                         c_u32,  1),
                 ('TA',                         c_u32,  1),
                 ('RK',                         c_u32,  1)]
    hd_fields = ExplicitHdr.hd_fields + rq_fields

    def __str__(self):
        r = super().__str__()
        r += (',{},{},{}' if self.csv else ', LP: {}, TA: {}, RK: {}').format(self.LP, self.TA, self.RK)
        if self.RK:
            r += (',{}' if self.csv else ', RKey: {:08x}').format(self.RKey)
        elif self.csv:
            r += ','
        return r

class ExplicitPkt(ExplicitHdr):
    _fields_ = ExplicitHdr.hd_fields

class ExplicitReqPkt(ExplicitReqHdr):
    _fields_ = ExplicitHdr.hd_fields + ExplicitReqHdr.rq_fields

class Core64ReadWriteMixin():
    '''Mix-in defining additional methods for Core64 Read/Write
    '''
    @property
    def Addr(self):
        return self.Addrh << 32 | self.Addrl

    @Addr.setter
    def Addr(self, val):
        self.Addrl = val & 0xffffffff
        self.Addrh = (val >> 32) & 0xffffffff

class Core64ReadBase(ExplicitReqHdr, Core64ReadWriteMixin):
    os1_fields = [('RDSize',                     c_u32,  9)]
    os2_fields = [('Addrh',                      c_u32, 32), # Byte 12
                  ('Addrl',                      c_u32, 32)] # Byte 16
    os3_fields = [('R0',                         c_u32,  5), # Byte 20
                  ('PD',                         c_u32,  1),
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0):
        fields = ExplicitReqHdr.hd_fields + Core64ReadBase.os1_fields
        hdr_len = 6 # Revisit: constant 6
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if RK:
            fields.extend(ExplicitHdr.rk_fields)
            hdr_len += 1
        fields.extend(Core64ReadBase.os2_fields)
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
            hdr_len += 4
        fields.extend(Core64ReadBase.os3_fields)
        pkt_type = type(className, (Core64ReadBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity})
        return (pkt_type, hdr_len) # no payload

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = Core64ReadBase.pkt_type(className, 0, exp_pkt.GC,
                        exp_pkt.NH, exp_pkt.RK, data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    def __str__(self):
        r = super().__str__()
        r += (',,,{},,{}' if self.csv else ', RDSize: {:3d}, Addr: {:016x}').format(self.RDSize, self.Addr)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:02x}'.format(self.R0)
        r += (',,,,,,,,,{},{},,,,,{}' if self.csv else ', PD: {0}, FPS: {1}, ECRC:{3}{2:06x}').format(self.PD, self.FPS, self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        return r

class Core64ReadPkt(Core64ReadBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, RK:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = Core64ReadBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH, RK=RK,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, RK=RK, data=data,
                        verbosity=verbosity, **kwargs)

class Core64ReadResponseBase(ExplicitHdr):
    os1_fields = [('LP',                         c_u32,  1),
                  ('R0',                         c_u32,  3),
                  ('PadCNT',                     c_u32,  2),
                  ('MS',                         c_u32,  2),
                  ('RRSPReason',                 c_u32,  4)]
    os3_fields = [('R1',                         c_u32,  8),
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitHdr.hd_fields + Core64ReadResponseBase.os1_fields
        hdr_len = 4 # Revisit: constant 4
        if NH:
            hdr_len += 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        # Revisit: LP (LPD) field
        # Revisit: MS (Meta) field
        pay_len = (Packet.pay_len_and_pad_cnt(payLen)[0] if pktLen is None
                   else (pktLen - hdr_len))
        fields.append(('Payload', c_u32 * pay_len))
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(Core64ReadResponseBase.os3_fields)
        pkt_type = type(className, (Core64ReadResponseBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity,
                         'pay_len': pay_len})
        return (pkt_type, hdr_len + pay_len)

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = Core64ReadResponseBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH, pktLen=exp_pkt.LEN,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    def __str__(self):
        r = super().__str__()
        r += (',{}' if self.csv else ', LP: {}').format(self.LP)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {}'.format(self.R0)
        r += (',,,,,,{},,,,,,,,,{},,,{}' if self.csv else ', PadCNT: {:3d}, MS: {}, RRSPReason: {}').format(
            self.PadCNT, self.MS, self.RRSPReason)
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {:02x}'.format(self.R1)
        r += (',,,,{}' if self.csv else ', ECRC:{1}{0:06x}').format(self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        if self.verbosity:
            byte_len = self.pay_len * 4 - self.PadCNT
            r += f'\n\tPayload[{byte_len}]:'
            for i in reversed(range(self.pay_len)):
                width = 8 if byte_len >= 4 else 2 * byte_len
                r += f' {self.Payload[i]:0{width}x}'
                byte_len -= width // 2
        return r

class Core64ReadResponsePkt(Core64ReadResponseBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = Core64ReadResponseBase.pkt_type(className, payLen,
                                GC=GC, NH=NH, data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, data=data,
                        verbosity=verbosity, **kwargs)

class Core64WriteBase(ExplicitReqHdr, Core64ReadWriteMixin):
    os1_fields = [('TC',                         c_u32,  1),
                  ('NS',                         c_u32,  1),
                  ('UN',                         c_u32,  1),
                  ('PU',                         c_u32,  1),
                  ('RC',                         c_u32,  1),
                  ('MS',                         c_u32,  2),
                  ('PadCNT',                     c_u32,  2)]
    os2_fields = [('Addrh',                      c_u32, 32), # Byte 12
                  ('Addrl',                      c_u32, 32)] # Byte 16
    os3_fields = [('R0',                         c_u32,  5), # Byte YY
                  ('PD',                         c_u32,  1),
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitReqHdr.hd_fields + Core64WriteBase.os1_fields
        hdr_len = 6 # Revisit: constant 6
        if NH:
            hdr_len += 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if RK:
            fields.extend(ExplicitHdr.rk_fields)
            hdr_len += 1
        fields.extend(Core64WriteBase.os2_fields)
        # Revisit: MS (Meta) field
        pay_len = (Packet.pay_len_and_pad_cnt(payLen)[0] if pktLen is None
                   else (pktLen - hdr_len))
        fields.append(('Payload', c_u32 * pay_len))
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(Core64WriteBase.os3_fields)
        pkt_type = type(className, (Core64WriteBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity,
                         'pay_len': pay_len})
        return (pkt_type, hdr_len + pay_len)

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = Core64WriteBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH, exp_pkt.RK,
                                    pktLen=exp_pkt.LEN,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    def __str__(self):
        r = super().__str__()
        r += (',,,,{},{}' if self.csv else ', PadCNT: {:3d}, Addr: {:016x}').format(self.PadCNT, self.Addr)
        r += (',,,{},{},{},{},{},{}' if self.csv else
              ', TC: {}, NS: {}, UN: {}, PU: {}, RC: {}, MS: {}').format(
            self.TC, self.NS, self.UN, self.PU, self.RC, self.MS)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:02x}'.format(self.R0)
        r += (',{},{},,,,,{}' if self.csv else ', PD: {0}, FPS: {1}, ECRC:{3}{2:06x}').format(self.PD, self.FPS, self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        if self.verbosity:
            byte_len = self.pay_len * 4 - self.PadCNT
            r += f'\n\tPayload[{byte_len}]:'
            for i in reversed(range(self.pay_len)):
                width = 8 if byte_len >= 4 else 2 * byte_len
                r += f' {self.Payload[i]:0{width}x}'
                byte_len -= width // 2
        return r

class Core64WritePkt(Core64WriteBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, RK:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = Core64WriteBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH, RK=RK,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, RK=RK, data=data,
                        verbosity=verbosity, **kwargs)

class Core64WritePartialBase(ExplicitReqHdr, Core64ReadWriteMixin):
    os1_fields = [('TC',                         c_u32,  1),
                  ('NS',                         c_u32,  1),
                  ('UN',                         c_u32,  1),
                  ('PU',                         c_u32,  1),
                  ('RC',                         c_u32,  1),
                  ('R0',                         c_u32,  4)]
    os2_fields = [('Addrh',                      c_u32, 32), # Byte 12
                  ('Addrl',                      c_u32, 32), # Byte 16
                  ('Maskl',                      c_u32, 32), # Byte 20
                  ('Maskh',                      c_u32, 32)] # Byte 24
    os3_fields = [('R1',                         c_u32,  5), # Byte 92
                  ('PD',                         c_u32,  1),
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0):
        fields = ExplicitReqHdr.hd_fields + Core64WritePartialBase.os1_fields
        hdr_len = 8 # Revisit: constant 8
        if NH:
            hdr_len += 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if RK:
            fields.extend(ExplicitHdr.rk_fields)
            hdr_len += 1
        fields.extend(Core64WritePartialBase.os2_fields)
        # Revisit: MS (Meta) field
        pay_len = (Packet.pay_len_and_pad_cnt(payLen)[0] if pktLen is None
                   else (pktLen - hdr_len))
        if pay_len != 16:
            raise ValueError('WritePartial payload must be 64 bytes')
        fields.append(('Payload', c_u32 * pay_len))
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(Core64WritePartialBase.os3_fields)
        pkt_type = type(className, (Core64WritePartialBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity,
                         'pay_len': pay_len})
        return (pkt_type, hdr_len + pay_len)

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = Core64WritePartialBase.pkt_type(className, 0,
                        exp_pkt.GC, exp_pkt.NH, exp_pkt.RK, pktLen=exp_pkt.LEN,
                        data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def Mask(self):
        return self.Maskh << 32 | self.Maskl

    @Mask.setter
    def Mask(self, val):
        self.Maskl = val & 0xffffffff
        self.Maskh = (val >> 32) & 0xffffffff

    def __str__(self):
        r = super().__str__()
        r += (',,,,,{},,{}' if self.csv else ', PadCNT: N/A, Addr: {:016x}, Mask: {:016x}').format(self.Addr, self.Mask)
        r += (',{},{},{},{},{},' if self.csv else
              ', TC: {}, NS: {}, UN: {}, PU: {}, RC: {}').format(
            self.TC, self.NS, self.UN, self.PU, self.RC)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:02x}, R1: {:02x}'.format(self.R0, self.R1)
        r += (',{},{},,,,,{}' if self.csv else ', PD: {0}, FPS: {1}, ECRC:{3}{2:06x}').format(self.PD, self.FPS, self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        if self.verbosity:
            byte_len = self.pay_len * 4 # no PadCNT
            r += f'\n\tPayload[{byte_len}]:'
            for i in reversed(range(self.pay_len)):
                width = 8 if byte_len >= 4 else 2 * byte_len
                r += f' {self.Payload[i]:0{width}x}'
                byte_len -= width // 2
        return r

class Core64WritePartialPkt(Core64WritePartialBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, RK:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = Core64WritePartialBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH, RK=RK,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, RK=RK, data=data,
                        verbosity=verbosity, **kwargs)

class Core64StandaloneAckBase(ExplicitHdr):
    os1_fields = [('RNR_QD',                     c_u32,  3),
                  ('RSl',                        c_u32,  3),
                  ('Reason',                     c_u32,  6)]
    os3_fields = [('RSh',                        c_u32,  8), # Byte 12
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0):
        fields = ExplicitHdr.hd_fields + Core64StandaloneAckBase.os1_fields
        hdr_len = 4 # Revisit: constant 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
            hdr_len += 4
        fields.extend(Core64StandaloneAckBase.os3_fields)
        pkt_type = type(className, (Core64StandaloneAckBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity})
        return (pkt_type, hdr_len) # no payload

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = Core64StandaloneAckBase.pkt_type(className, 0,
                                            exp_pkt.GC, exp_pkt.NH,
                                            data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def RS(self):
        return self.RSh << 3 | self.RSl

    @RS.setter
    def RS(self, val):
        self.RSl = val & 0x7
        self.RSh = (val >> 3) & 0xff

    def __str__(self):
        r = super().__str__()
        r += (',,,,,,,,,,,,,,,,,,,,{},{},{}' if self.csv else ', RNR_QD: {}, RS: {}, Reason: {}').format(
            self.RNR_QD, self.RS, self.Reason)
        r += (',{}' if self.csv else ', ECRC:{1}{0:06x}').format(self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        return r

class Core64StandaloneAckPkt(Core64StandaloneAckBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = Core64StandaloneAckBase.pkt_type(className, payLen,
                                GC=GC, NH=NH, data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, data=data,
                        verbosity=verbosity, **kwargs)

class ControlReadWriteMixin():
    '''Mix-in defining additional methods for Control Read/Write
    '''
    @property
    def Addr(self):
        return self.Addrh << 32 | self.Addrl

    @Addr.setter
    def Addr(self, val):
        self.Addrl = val & 0xffffffff
        self.Addrh = (val >> 32) & 0xfffff

    @property
    def MGRUUID(self):
        return self.uuid(self._uuid_fields[0])

    @MGRUUID.setter
    def MGRUUID(self, uu: uuid.UUID):
        uub = uu.bytes
        uuFld = self._uuid_fields[0]
        setattr(self, uuFld[0], int.from_bytes(uub[0:4], byteorder='little'))
        setattr(self, uuFld[1], int.from_bytes(uub[4:8], byteorder='little'))
        setattr(self, uuFld[2], int.from_bytes(uub[8:12], byteorder='little'))
        setattr(self, uuFld[3], int.from_bytes(uub[12:16], byteorder='little'))


class ControlReadBase(ExplicitHdr, ControlReadWriteMixin):
    os1_fields = [('R0',                         c_u32,  2),
                  ('RK',                         c_u32,  1),
                  ('DR',                         c_u32,  1),
                  ('RDSize',                     c_u32,  8)]
    os2_fields = [('DRIface',                    c_u32, 12), # Byte 12
                  ('Addrh',                      c_u32, 20),
                  ('Addrl',                      c_u32, 32), # Byte 16
                  ('MGRUUID0',                   c_u32, 32), # Byte 20
                  ('MGRUUID1',                   c_u32, 32), # Byte 24
                  ('MGRUUID2',                   c_u32, 32), # Byte 28
                  ('MGRUUID3',                   c_u32, 32)] # Byte 32
    os3_fields = [('R1',                         c_u32,  6), # Byte 36
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    _uuid_fields = [('MGRUUID0', 'MGRUUID1', 'MGRUUID2', 'MGRUUID3')]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0):
        fields = ExplicitHdr.hd_fields + ControlReadBase.os1_fields
        hdr_len = 10 # Revisit: constant 10
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if RK:
            fields.extend(ExplicitHdr.rk_fields)
            hdr_len += 1
        fields.extend(ControlReadBase.os2_fields)
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
            hdr_len += 4
        fields.extend(ControlReadBase.os3_fields)
        pkt_type = type(className, (ControlReadBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity})
        return (pkt_type, hdr_len) # no payload

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = ControlReadBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH, exp_pkt.RK,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    def __str__(self):
        r = super().__str__()
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {}'.format(self.R0)
        r += (',,,{},{}' if self.csv else ', RK: {}, DR: {}').format(self.RK, self.DR)
        if self.RK:
            r += (',{}' if self.csv else ', RKey: {:08x}').format(self.RKey)
        elif self.csv:
            r += ','
        if self.DR:
            r += (',{}' if self.csv else ', DRIface: {}').format(self.DRIface)
        elif self.csv:
            r += ','
        r += (',{},,{},{}' if self.csv else ', RDSize: {:3d}, Addr: {:013x}, MGRUUID: {}').format(
            self.RDSize, self.Addr, self.MGRUUID)
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {:02x}'.format(self.R1)
        r += (',,,,,,,,,{},,,,,{}' if self.csv else ', FPS: {0}, ECRC:{2}{1:06x}').format(self.FPS, self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        return r

class ControlReadPkt(ControlReadBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, RK:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = ControlReadBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH, RK=RK,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, RK=RK, data=data,
                        verbosity=verbosity, **kwargs)

class ControlReadResponseBase(Core64ReadResponseBase):
    pass

class ControlReadResponsePkt(Core64ReadResponsePkt):
    pass

class ControlWriteBase(ExplicitHdr, ControlReadWriteMixin):
    os1_fields = [('R0',                         c_u32,  2),
                  ('RK',                         c_u32,  1),
                  ('DR',                         c_u32,  1),
                  ('R1',                         c_u32,  8)]
    os2_fields = [('DRIface',                    c_u32, 12), # Byte 12
                  ('Addrh',                      c_u32, 20),
                  ('Addrl',                      c_u32, 32)] # Byte 16
    os2b_fields = [('MGRUUID0',                  c_u32, 32), # Byte NN
                  ('MGRUUID1',                   c_u32, 32),
                  ('MGRUUID2',                   c_u32, 32),
                  ('MGRUUID3',                   c_u32, 32)]
    os3_fields = [('PadCNT',                     c_u32,  2), # Byte YY
                  ('R2',                         c_u32,  4),
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    _uuid_fields = [('MGRUUID0', 'MGRUUID1', 'MGRUUID2', 'MGRUUID3')]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitHdr.hd_fields + ControlWriteBase.os1_fields
        hdr_len = 10 # Revisit: constant 10
        if NH:
            hdr_len += 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if RK:
            fields.extend(ExplicitHdr.rk_fields)
            hdr_len += 1
        fields.extend(ControlWriteBase.os2_fields)
        pay_len = (Packet.pay_len_and_pad_cnt(payLen)[0] if pktLen is None
                   else (pktLen - hdr_len))
        fields.append(('Payload', c_u32 * pay_len))
        fields.extend(ControlWriteBase.os2b_fields)
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(ControlWriteBase.os3_fields)
        pkt_type = type(className, (ControlWriteBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity,
                         'pay_len': pay_len})
        return (pkt_type, hdr_len + pay_len)

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = ControlWriteBase.pkt_type(className, 0,
                        exp_pkt.GC, exp_pkt.NH, exp_pkt.RK, pktLen=exp_pkt.LEN,
                        data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    def __str__(self):
        r = super().__str__()
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {}'.format(self.R0)
        r += (',,,{},{}' if self.csv else ', RK: {}, DR: {}').format(self.RK, self.DR)
        if self.RK:
            r += (',{}' if self.csv else ', RKey: {:08x}').format(self.RKey)
        elif self.csv:
            r += ','
        if self.DR:
            r += (',{}' if self.csv else ', DRIface: {}').format(self.DRIface)
        elif self.csv:
            r += ','
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {:02x}'.format(self.R1)
        r += (',,{},{},{}' if self.csv else ', PadCNT: {:3d}, Addr: {:013x}, MGRUUID: {}').format(
            self.PadCNT, self.Addr, self.MGRUUID)
        if self.verbosity > 1 and not self.csv:
            r += ', R2: {:02x}'.format(self.R2)
        r += (',,,,,,,,,{},,,,,{}' if self.csv else ', FPS: {0}, ECRC:{2}{1:06x}').format(self.FPS, self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        if self.verbosity:
            byte_len = self.pay_len * 4 - self.PadCNT
            r += f'\n\tPayload[{byte_len}]:'
            for i in reversed(range(self.pay_len)):
                width = 8 if byte_len >= 4 else 2 * byte_len
                r += f' {self.Payload[i]:0{width}x}'
                byte_len -= width // 2
        return r

class ControlWritePkt(ControlWriteBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, RK:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = ControlWriteBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH, RK=RK,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, RK=RK, data=data,
                        verbosity=verbosity, **kwargs)

class ControlWritePartialBase(ExplicitHdr, ControlReadWriteMixin):
    os1_fields = [('R0',                         c_u32,  2),
                  ('RK',                         c_u32,  1),
                  ('DR',                         c_u32,  1),
                  ('R1',                         c_u32,  8)]
    os2_fields = [('DRIface',                    c_u32, 12), # Byte 12
                  ('Addrh',                      c_u32, 20),
                  ('Addrl',                      c_u32, 32), # Byte 16
                  ('Maskl',                      c_u32, 32), # Byte 20
                  ('Maskh',                      c_u32, 32)] # Byte 24
    os2b_fields = [('MGRUUID0',                  c_u32, 32), # Byte 92
                  ('MGRUUID1',                   c_u32, 32),
                  ('MGRUUID2',                   c_u32, 32),
                  ('MGRUUID3',                   c_u32, 32)]
    os3_fields = [('R2',                         c_u32,  6), # Byte 108
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    _uuid_fields = [('MGRUUID0', 'MGRUUID1', 'MGRUUID2', 'MGRUUID3')]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitHdr.hd_fields + ControlWritePartialBase.os1_fields
        hdr_len = 12 # Revisit: constant 12
        if NH:
            hdr_len += 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if RK:
            fields.extend(ExplicitHdr.rk_fields)
            hdr_len += 1
        fields.extend(ControlWritePartialBase.os2_fields)
        pay_len = (Packet.pay_len_and_pad_cnt(payLen)[0] if pktLen is None
                   else (pktLen - hdr_len))
        fields.append(('Payload', c_u32 * pay_len))
        fields.extend(ControlWritePartialBase.os2b_fields)
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(ControlWritePartialBase.os3_fields)
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type = type(className, (ControlWritePartialBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity,
                         'pay_len': pay_len})
        return (pkt_type, hdr_len + pay_len)

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = ControlWritePartialBase.pkt_type(className, 0,
                        exp_pkt.GC, exp_pkt.NH, exp_pkt.RK, pktLen=exp_pkt.LEN,
                        data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def Mask(self):
        return self.Maskh << 32 | self.Maskl

    @Mask.setter
    def Mask(self, val):
        self.Maskl = val & 0xffffffff
        self.Maskh = (val >> 32) & 0xffffffff

    def __str__(self):
        r = super().__str__()
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {}'.format(self.R0)
        r += (',,,{},{}' if self.csv else ', RK: {}, DR: {}').format(self.RK, self.DR)
        if self.DR:
            r += (',{}' if self.csv else ', DRIface: {}').format(self.DRIface)
        elif self.csv:
            r += ','
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {:02x}'.format(self.R1)
        r += (',,{},{},{}' if self.csv else ', PadCNT: N/A, Addr: {:013x}, Mask: {:016x}, MGRUUID: {}').format(
            self.Addr, self.Mask, self.MGRUUID)
        if self.verbosity > 1 and not self.csv:
            r += ', R2: {:02x}'.format(self.R2)
        r += (',,,,,,,,,{},,,,,{}' if self.csv else ', FPS: {0}, ECRC:{2}{1:06x}').format(self.FPS, self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        if self.verbosity:
            byte_len = self.pay_len * 4 - self.PadCNT
            r += f'\n\tPayload[{byte_len}]:'
            for i in reversed(range(self.pay_len)):
                width = 8 if byte_len >= 4 else 2 * byte_len
                r += f' {self.Payload[i]:0{width}x}'
                byte_len -= width // 2
        return r

class ControlWritePartialPkt(ControlWritePartialBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, RK:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = ControlWritePartialBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH, RK=RK,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, RK=RK, data=data,
                        verbosity=verbosity, **kwargs)

class ControlUnsolicitedEventBase(ExplicitHdr):
    # Revisit: ExplicitHdr has Tag, while UEP has R0
    os1_fields = [('CV',                         c_u32,  1),
                  ('SV',                         c_u32,  1),
                  ('IV',                         c_u32,  1),
                  ('Event',                      c_u32,  8),
                  ('R1',                         c_u32,  1)]
    os2_fields = [('RCCID',                      c_u32, 12), # Byte 12
                  ('IfaceID',                    c_u32, 12),
                  ('RCSIDl',                     c_u32,  8),
                  ('RCSIDh',                     c_u32,  8), # Byte 16
                  ('R2',                         c_u32,  8),
                  ('EventID',                    c_u32, 16),
                  ('ES',                         c_u32, 32)] # Byte 20
    os3_fields = [('R3',                         c_u32,  8), # Byte 24
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitHdr.hd_fields + ControlUnsolicitedEventBase.os1_fields
        hdr_len = 7 # Revisit: constant 7
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        fields.extend(ControlUnsolicitedEventBase.os2_fields)
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
            hdr_len += 4
        fields.extend(ControlUnsolicitedEventBase.os3_fields)
        pkt_type = type(className, (ControlUnsolicitedEventBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity})
        return (pkt_type, hdr_len) # no payload

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = ControlUnsolicitedEventBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH, pktLen=exp_pkt.LEN,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        pkt.noTag = True
        return pkt

    @property
    def RCSID(self):
        return self.RCSIDh << 8 | self.RCSIDl

    @RCSID.setter
    def RCSID(self, val):
        self.RCSIDl = val & 0xff
        self.RCSIDh = (val >> 8) & 0xff

    def to_json(self):
        jds = super().to_json()
        jd = { 'Event': self.Event,
               'EventName': (eventName[self.Event] if self.Event
                             in eventName else 'Reserved'),
               'CV': self.CV,
               'SV': self.SV,
               'IV': self.IV,
               'IfaceID': self.IfaceID,
               'EventID': self.EventID,
               'ES': self.ES,
               'RCCID': self.RCCID,
               'RCSID': self.RCSID,
               }

        return jds | jd

    def __str__(self):
        r = super().__str__()
        try:
            evName = eventName[self.Event]
        except KeyError:
            evName = 'Reserved'
        # Revisit: fix csv columns
        r += (',,,,,,,,,{},,,,,{}' if self.csv else ', CV: {}, SV: {}, IV: {}, Event: {}[{:02x}]').format(self.CV, self.SV, self.IV, evName, self.Event)
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {}'.format(self.R1)
        if self.csv:
            r += (',,{},{},{}' if self.csv else ', RCCID: {:03x}, IfaceID: {}, RCSID: {:04x}').format(
                self.RCCID, self.IfaceID, self.RCSID)
        else:
            if self.CV and self.SV:
                r += ', RCGCID: {:04x}:{:03x}'.format(self.RCSID, self.RCCID)
            elif self.CV:
                r += ', RCCID: {:03x}'.format(self.RCCID)
            if self.IV:
                r += ', IfaceID: {}'.format(self.IfaceID)
        if self.verbosity > 1 and not self.csv:
            r += ', R2: {:02x}'.format(self.R2)
        r += (',,{},{},{}' if self.csv else ', EventID: {:04x}, ES: {:08x}').format(
            self.EventID, self.ES)
        if self.verbosity > 1 and not self.csv:
            r += ', R3: {:02x}'.format(self.R3)
        r += (',,,,,,,,,,,,,,{}' if self.csv else ', ECRC:{1}{0:06x}').format(self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        return r

class ControlUnsolicitedEventPkt(ControlUnsolicitedEventBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = ControlUnsolicitedEventBase.pkt_type(className, 0,
                                GC=GC, NH=NH, data=data, verbosity=verbosity)
        pkt_type.noTag = True
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, data=data,
                        verbosity=verbosity, **kwargs)

class ControlStandaloneAckBase(Core64StandaloneAckBase):
    pass

class ControlStandaloneAckPkt(Core64StandaloneAckPkt):
    pass

class WriteMsgMixin():
    '''Mix-in defining additional methods for multi-pkt messages
    '''
    isWriteMSG = True

    @property
    def payload_len(self):
        return self.pay_len * 4 - self.PadCNT

    def single(self):  # msg is single-pkt
        return self.MSGSZ == 1

    def msgsz_woff(self):
        msgsz = MaxMsgSize if self.MSGSZ == 0 else (self.MSGSZ * MaxPktPayload)
        woff = self.WOFF * MaxPktPayload
        return (msgsz, woff) # msgsz & woff in bytes

    def last(self, msgsz=None, woff=None):  # pkt is the last one in the msg
        if msgsz is None or woff is None:
            msgsz, woff = self.msgsz_woff()
        # msgsz & woff in bytes (not MaxPktPayload units)
        return (woff + MaxPktPayload) == msgsz

    def msg_len(self):
        msgsz, woff = self.msgsz_woff()
        last = self.last(msgsz, woff)
        # only the last (or only) pkt has actual msg len; others only have a
        # pessimistic max based on msgsz
        return (woff + self.payload_len) if last else msgsz


class CtxIdWriteMSGBase(ExplicitHdr, WriteMsgMixin):
    os1_fields = [('RT',                         c_u32,  1),
                  ('MSGSZ',                      c_u32, 11)]
    os2_fields = [('RSPCTXID',                   c_u32, 24), # Byte 12
                  ('REQCTXIDl',                  c_u32,  8),
                  ('REQCTXIDh',                  c_u32, 16), # Byte 16
                  ('WOFF',                       c_u32, 11),
                  ('CH',                         c_u32,  1),
                  ('NS',                         c_u32,  1),
                  ('ER',                         c_u32,  1),
                  ('PadCNT',                     c_u32,  2),
                  ('MSGID',                      c_u32, 32)] # Byte 20
    os2b_fields = [('RCVTag0',                   c_u32, 32), # Byte 24
                  ('RCVTag1',                    c_u32, 32),
                  ('RCVTag2',                    c_u32, 32)]
    # Revisit: EV & AV bits
    os3_fields = [('R0',                         c_u32,  5), # Byte YY
                  ('CA',                         c_u32,  1),
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RT:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitHdr.hd_fields + CtxIdWriteMSGBase.os1_fields
        hdr_len = 7 # Revisit: constant 7
        if NH:
            hdr_len += 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        fields.extend(CtxIdWriteMSGBase.os2_fields)
        if RT:
            fields.extend(CtxIdWriteMSGBase.os2b_fields)
            hdr_len += 3
        pay_len = (Packet.pay_len_and_pad_cnt(payLen)[0] if pktLen is None
                   else (pktLen - hdr_len))
        fields.append(('Payload', c_u32 * pay_len))
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(CtxIdWriteMSGBase.os3_fields)
        pktClass = globals()[className + 'Base']
        pkt_type = type(className, (pktClass,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity,
                         'pay_len': pay_len})
        return (pkt_type, hdr_len + pay_len)

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        # Revisit: hack - LP is same bit pos as RT
        pkt_type, hdr_len = CtxIdWriteMSGBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH, exp_pkt.LP,
                                    pktLen=exp_pkt.LEN,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def REQCTXID(self):
        return self.REQCTXIDh << 8 | self.REQCTXIDl

    @REQCTXID.setter
    def REQCTXID(self, val):
        self.REQCTXIDl = val & 0xff
        self.REQCTXIDh = (val >> 8) & 0xffff

    @property
    def RCVTag(self):
        return self.RCVTag2 << 64 | self.RCVTag1 << 32 | self.RCVTag0

    @RCVTag.setter
    def RCVTag(self, val):
        self.RCVTag0 = val & 0xffffffff
        self.RCVTag1 = (val >> 32) & 0xffffffff
        self.RCVTag2 = (val >> 64) & 0xffffffff

    def __str__(self):
        r = super().__str__()
        # Revisit: fix csv columns
        r += (',,,,{}' if self.csv else ', PadCNT: {:3d}').format(self.PadCNT)
        r += (',,,{},{},{},{},{},{}' if self.csv else
              ', RT: {}, MSGSZ: {:03x}, RSPCTXID: {:06x}, REQCTXID: {:06x}, WOFF: {:03x}, CH: {}, NS: {}, ER: {}, MSGID: {:08x}').format(
                  self.RT, self.MSGSZ, self.RSPCTXID, self.REQCTXID, self.WOFF, self.CH, self.NS, self.ER, self.MSGID)
        if self.RT:
            r += (',{}' if self.csv else ', RCVTag: {:024x}').format(self.RCVTag)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:02x}'.format(self.R0)
        r += (',{},{},,,,,{}' if self.csv else ', CA: {0}, FPS: {1}, ECRC:{3}{2:06x}').format(self.CA, self.FPS, self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        if self.verbosity:
            byte_len = self.pay_len * 4 # no PadCNT
            r += f'\n\tPayload[{byte_len}]:'
            for i in reversed(range(self.pay_len)):
                width = 8 if byte_len >= 4 else 2 * byte_len
                r += f' {self.Payload[i]:0{width}x}'
                byte_len -= width // 2
        return r

class CtxIdWriteMSGPkt(CtxIdWriteMSGBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, RT:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = CtxIdWriteMSGBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH, RT=RT,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, RT=RT, data=data,
                        verbosity=verbosity, **kwargs)

class CtxIdUnrelWriteMSGBase(CtxIdWriteMSGBase):
    def reliable(self):
        return False

class CtxIdUnrelWriteMSGPkt(CtxIdWriteMSGPkt):
    pass


class ControlWriteMSGBase(ExplicitHdr, WriteMsgMixin):
    os1_fields = [('IV',                         c_u32,  1),
                  ('MSGSZ',                      c_u32, 11)]
    os2_fields = [('RSPCTXID',                   c_u32, 24), # Byte 12
                  ('REQCTXIDl',                  c_u32,  8),
                  ('REQCTXIDh',                  c_u32, 16), # Byte 16
                  ('WOFF',                       c_u32, 11),
                  ('CH',                         c_u32,  1),
                  ('DR',                         c_u32,  1),
                  ('SDR',                        c_u32,  1),
                  ('PadCNT',                     c_u32,  2),
                  ('MSGID',                      c_u32, 32), # Byte 20
                  ('DRIface',                    c_u32, 12), # Byte 24
                  ('InstanceID',                 c_u32, 20)]
    os3_fields = [('R0',                         c_u32,  6), # Byte YY
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitHdr.hd_fields + ControlWriteMSGBase.os1_fields
        hdr_len = 8 # Revisit: constant 8
        if NH:
            hdr_len += 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        fields.extend(ControlWriteMSGBase.os2_fields)
        pay_len = (Packet.pay_len_and_pad_cnt(payLen)[0] if pktLen is None
                   else (pktLen - hdr_len))
        fields.append(('Payload', c_u32 * pay_len))
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(ControlWriteMSGBase.os3_fields)
        pktClass = globals()[className + 'Base']
        pkt_type = type(className, (pktClass,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity,
                         'pay_len': pay_len})
        return (pkt_type, hdr_len + pay_len)

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = ControlWriteMSGBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH,
                                    pktLen=exp_pkt.LEN,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def REQCTXID(self):
        return self.REQCTXIDh << 8 | self.REQCTXIDl

    @REQCTXID.setter
    def REQCTXID(self, val):
        self.REQCTXIDl = val & 0xff
        self.REQCTXIDh = (val >> 8) & 0xffff

    def __str__(self):
        r = super().__str__()
        # Revisit: fix csv columns
        r += (',,,,{}' if self.csv else ', PadCNT: {:3d}').format(self.PadCNT)
        r += (',,,{},{},{},{},{},{},{},{},{},{},{}' if self.csv else
              ', IV: {}, MSGSZ: {:03x}, RSPCTXID: {:06x}, REQCTXID: {:06x}, WOFF: {:03x}, CH: {}, DR: {}, SDR: {}, MSGID: {:08x}, DRIface: {}, InstanceID: {}').format(
                  self.IV, self.MSGSZ, self.RSPCTXID, self.REQCTXID, self.WOFF, self.CH, self.DR, self.SDR, self.MSGID, self.DRIface, self.InstanceID)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:02x}'.format(self.R0)
        r += (',,{},,,,,{}' if self.csv else ', FPS: {0}, ECRC:{2}{1:06x}').format(self.FPS, self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        if self.verbosity:
            byte_len = self.pay_len * 4 - self.PadCNT
            r += f'\n\tPayload[{byte_len}]:'
            for i in reversed(range(self.pay_len)):
                width = 8 if byte_len >= 4 else 2 * byte_len
                r += f' {self.Payload[i]:0{width}x}'
                byte_len -= width // 2
        return r

class ControlWriteMSGPkt(ControlWriteMSGBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = ControlWriteMSGBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, data=data,
                        verbosity=verbosity, **kwargs)

class ControlUnrelWriteMSGBase(ControlWriteMSGBase):
    def reliable(self):
        return False

class ControlUnrelWriteMSGPkt(ControlWriteMSGPkt):
    pass

class DRUnrelWriteMSGBase(ControlUnrelWriteMSGBase):
    pass

class DRUnrelWriteMSGPkt(ControlUnrelWriteMSGPkt):
    pass

class MulticastHdr(ExplicitHdr):
    hd_fields = [('MGIDl',                      c_u32,  5), # Byte 0
                 ('LENl',                       c_u32,  3),
                 ('MGIDm',                      c_u32,  4),
                 ('LENh',                       c_u32,  4),
                 ('MGIDh',                      c_u32,  3),
                 ('VC',                         c_u32,  5),
                 ('OpCodel',                    c_u32,  2),
                 ('PCRC',                       c_u32,  6),
                 ('OpCodeh',                    c_u32,  3), # Byte 4
                 ('OCL',                        c_u32,  5),
                 ('Tag',                        c_u32, 12),
                 ('SCID',                       c_u32, 12),
                 ('AKey',                       c_u32,  6), # Byte 8
                 ('Deadline',                   c_u32, 10),
                 ('ECN',                        c_u32,  1),
                 ('GC',                         c_u32,  1),
                 ('NH',                         c_u32,  1),
                 ('PM',                         c_u32,  1)]
    # OS1 is in each individual packet format
    ms_fields = [('GMCP',                       c_u32, 16),
                 ('SSID',                       c_u32, 16)]

    def multicast(self):
        return True

    @property
    def MGID(self):
        return self.MGIDh << 9 | self.MGIDm << 5 | self.MGIDl

    @MGID.setter
    def MGID(self, val: int) -> None:
        if val < 0 or val > 4095:
            raise(ValueError)
        self.MGIDh = (val >> 9) & 0x7
        self.MGIDm = (val >> 5) & 0xf
        self.MGIDl = val & 0x1f

    @property
    def GMGID(self):
        return self.MGID if not self.GC else (self.GMCP << 12) | self.MGID

    @property
    def uniqueness(self):
        if self.isRequest:
            return (self.SGCID << 40) | (self.GMGID << 12) | self.Tag
        else: # isResponse - swap SGCID/GMGID so it matches request
            return (self.GMGID << 40) | (self.SGCID << 12) | self.Tag

    def to_json(self):
        jd = { 'name': type(self).__name__,
               'OCL': self.OCL,
               'OpCode': self.OpCode,
               'LEN': self.LEN,
               'VC': self.VC,
               'PCRC': self.PCRC,
               'MGID': self.MGID,
               'SCID': self.SCID,
               'ECRC': self.ECRC,
               'AKey': self.AKey,
               'Deadline': self.Deadline,
               'ECN': self.ECN,
               'GC': self.GC,
               'NH': self.NH,
               'PM': self.PM,
               # Revisit: finish this
              }
        noTag = getattr(self, 'noTag', False)
        if not noTag:
            jd['Tag'] = self.Tag
        return jd


    def __str__(self):
        noTag = getattr(self, 'noTag', False)
        r = ('{}' if self.csv else '{:>23s}').format(type(self).__name__)
        if self.csv or type(self).__name__[0:8] != 'Explicit':
            r += (',{},{}' if self.csv else '[{:02x}:{:02x}]').format(self.OCL, self.OpCode)
        else:
            r += ' OpClass: {}({:02x}), OpCode: {}({:02x})'.format(
                self.oclName, self.OCL, self.opcName, self.OpCode)
        r += (',{}' if self.csv else ', Length: {:2d}').format(self.LEN)
        if self.GC:
            # Revisit: CSV format
            try: # Revisit: workaround for Unknown packets
                r += ', SGCID: {:04x}:{:03x}, GMGID: {:04x}:{:03x}'.format(
                    self.SSID, self.SCID, self.GMCP, self.MGID)
            except AttributeError:
                r += ', SGCID: ????:{:03x}, GMGID: ????:{:03x}'.format(
                    self.SCID, self.DCID)
        else:
            r += (',{},{}' if self.csv else ', SCID: {:03x}, MGID: {:03x}').format(self.SCID, self.MGID)
        r += (',{}' if self.csv else ', R0:  {:03x}' if noTag else ', Tag: {:03x}').format(
            self.Tag)
        r += (',{},{}' if self.csv else
              ', VC: {0}, PCRC:{2}{1:02x}').format(
            self.VC, self.PCRC, self.pcrc_sep)
        r += self.expected_pcrc_str
        r += (',{},{},{},{},{},{}' if self.csv else
              ', AKey: {:02x}, Deadline: {:4d}, ECN: {}, GC: {}, NH: {}, PM: {}').format(
            self.AKey, self.Deadline, self.ECN, self.GC, self.NH, self.PM)
        return r


class MulticastUnrelWriteMSGBase(MulticastHdr, WriteMsgMixin):
    os1_fields = [('RT',                         c_u32,  1),
                  ('MSGSZ',                      c_u32, 11)]
    os2_fields = [('R0',                         c_u32, 16), # Byte 12
                  ('WOFF',                       c_u32, 11),
                  ('CH',                         c_u32,  1),
                  ('NS',                         c_u32,  1),
                  ('R1',                         c_u32,  1),
                  ('PadCNT',                     c_u32,  2),
                  ('MSGID',                      c_u32, 32)] # Byte 16
    os2b_fields = [('RCVTag0',                   c_u32, 32), # Byte 20
                  ('RCVTag1',                    c_u32, 32),
                  ('RCVTag2',                    c_u32, 32)]
    os3_fields = [('R2',                         c_u32,  8), # Byte YY
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RT:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = MulticastHdr.hd_fields + MulticastUnrelWriteMSGBase.os1_fields
        hdr_len = 6 # Revisit: constant 6
        if NH:
            hdr_len += 4
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        fields.extend(MulticastUnrelWriteMSGBase.os2_fields)
        if RT:
            fields.extend(MulticastUnrelWriteMSGBase.os2b_fields)
            hdr_len += 3
        pay_len = (Packet.pay_len_and_pad_cnt(payLen)[0] if pktLen is None
                   else (pktLen - hdr_len))
        fields.append(('Payload', c_u32 * pay_len))
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(MulticastUnrelWriteMSGBase.os3_fields)
        pkt_type = type(className, (MulticastUnrelWriteMSGBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity,
                         'pay_len': pay_len})
        return (pkt_type, hdr_len + pay_len)

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        # Revisit: hack - LP is same bit pos as RT
        pkt_type, hdr_len = MulticastUnrelWriteMSGBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH, exp_pkt.LP,
                                    pktLen=exp_pkt.LEN,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def RCVTag(self):
        return self.RCVTag2 << 64 | self.RCVTag1 << 32 | self.RCVTag0

    @RCVTag.setter
    def RCVTag(self, val):
        self.RCVTag0 = val & 0xffffffff
        self.RCVTag1 = (val >> 32) & 0xffffffff
        self.RCVTag2 = (val >> 64) & 0xffffffff

    def reliable(self):
        return False

    def __str__(self):
        r = super().__str__()
        # Revisit: fix csv columns
        r += (',,,,{}' if self.csv else ', PadCNT: {:3d}').format(self.PadCNT)
        r += (',,,{},{},{},{},{},{}' if self.csv else
              ', RT: {}, MSGSZ: {:03x}, WOFF: {:03x}, CH: {}, NS: {}, MSGID: {:08x}').format(
                  self.RT, self.MSGSZ, self.WOFF, self.CH, self.NS, self.MSGID)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:04x}, R1: {}'.format(self.R0, self.R1)
        if self.RT:
            r += (',{}' if self.csv else ', RCVTag: {:024x}').format(self.RCVTag)
        if self.verbosity > 1 and not self.csv:
            r += ', R2: {:02x}'.format(self.R2)
        r += (',{},{},,,,,{}' if self.csv else ', ECRC:{1}{0:06x}').format(self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        if self.verbosity:
            byte_len = self.pay_len * 4 - self.PadCNT
            r += f'\n\tPayload[{byte_len}]:'
            for i in reversed(range(self.pay_len)):
                width = 8 if byte_len >= 4 else 2 * byte_len
                r += f' {self.Payload[i]:0{width}x}'
                byte_len -= width // 2
        return r

class MulticastUnrelWriteMSGPkt(MulticastUnrelWriteMSGBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, RT:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = MulticastUnrelWriteMSGBase.pkt_type(className, payLen,
                                    GC=GC, NH=NH, RT=RT,
                                    data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, RT=RT, data=data,
                        verbosity=verbosity, **kwargs)

class Adv2PTREQBase(ExplicitHdr):
    os1_fields = [('NP',                         c_u32,  1),
                  ('SV',                         c_u32,  1),
                  ('R0',                         c_u32, 10)]
    os2_fields = [('GTCCID',                     c_u32, 12), # Byte 12
                  ('R1',                         c_u32,  4),
                  ('GTCSID',                     c_u32, 16)]
    os3_fields = [('R2',                         c_u32,  8), # Byte 16
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitHdr.hd_fields + Adv2PTREQBase.os1_fields
        hdr_len = 5 # Revisit: constant 5
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        fields.extend(Adv2PTREQBase.os2_fields)
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
            hdr_len += 4
        fields.extend(Adv2PTREQBase.os3_fields)
        pkt_type = type(className, (Adv2PTREQBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity})
        return (pkt_type, hdr_len) # no payload

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = Adv2PTREQBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH, pktLen=exp_pkt.LEN,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    def to_json(self):
        jds = super().to_json()
        jd = { 'NP': self.NP,
               'SV': self.SV,
               'GTCCID': self.GTCCID,
               'GTCSID': self.GTCSID,
               }

        return jds | jd

    def __str__(self):
        r = super().__str__()
        # Revisit: fix csv columns
        r += (',,,,,,,,,{},,,,,{}' if self.csv else ', NP: {}, SV: {}').format(self.NP, self.SV)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:03x}'.format(self.R0)
        if self.csv:
            r += (',,{},,{}' if self.csv else ', GTCCID: {:03x}, GTCSID: {:04x}').format(
                self.GTCCID, self.GTCSID)
        else:
            if self.SV:
                r += ', GTCGCID: {:04x}:{:03x}'.format(self.GTCSID, self.GTCCID)
            else:
                r += ', GTCCID: {:03x}'.format(self.GTCCID)
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {:01x}'.format(self.R1)
        if self.verbosity > 1 and not self.csv:
            r += ', R2: {:02x}'.format(self.R2)
        r += (',,,,,,,,,,,,,,{}' if self.csv else ', ECRC:{1}{0:06x}').format(self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        return r

class Adv2PTREQPkt(Adv2PTREQBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = Adv2PTREQBase.pkt_type(className, 0,
                                GC=GC, NH=NH, data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, data=data,
                        verbosity=verbosity, **kwargs)

class Adv2PTRSPBase(ExplicitHdr):
    os1_fields = [('TP',                         c_u32,  1),
                  ('SV',                         c_u32,  1),
                  ('GU',                         c_u32,  1),
                  ('R0',                         c_u32,  9)]
    os2_fields = [('GTCCID',                     c_u32, 12), # Byte 12
                  ('R1',                         c_u32,  4),
                  ('GTCSID',                     c_u32, 16),
                  ('MasterTimel',                c_u32, 32), # Byte 16
                  ('MasterTimeh',                c_u32, 32), # Byte 20
                  ('PropDelay',                  c_u32, 32)] # Byte 24
    os3_fields = [('R2',                         c_u32,  8), # Byte 28
                  ('ECRC',                       c_u32, 24)]

    @staticmethod
    def pkt_type(className: str, payLen: int, GC:bool = False, NH:bool = False,
                 RK:bool = False, data = None, verbosity = 0, pktLen:int = None):
        fields = ExplicitHdr.hd_fields + Adv2PTRSPBase.os1_fields
        hdr_len = 8 # Revisit: constant 8
        if GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        fields.extend(Adv2PTRSPBase.os2_fields)
        if NH:
            fields.extend(ExplicitHdr.nh_fields)
            hdr_len += 4
        fields.extend(Adv2PTRSPBase.os3_fields)
        pkt_type = type(className, (Adv2PTRSPBase,),
                        {'_fields_': fields,
                         'data': data,
                         'verbosity': verbosity})
        return (pkt_type, hdr_len) # no payload

    def dataToPktInit(exp_pkt, data, verbosity):
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type, hdr_len = Adv2PTRSPBase.pkt_type(className, 0,
                                    exp_pkt.GC, exp_pkt.NH, pktLen=exp_pkt.LEN,
                                    data=data, verbosity=verbosity)
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def MasterTime(self):
        return self.MasterTimeh << 32 | self.MasterTimel

    @MasterTime.setter
    def MasterTime(self, val):
        self.MasterTimel = val & 0xffffffff
        self.MasterTimeh = (val >> 32) & 0xffffffff

    def to_json(self):
        jds = super().to_json()
        jd = { 'TP': self.TP,
               'SV': self.SV,
               'GU': self.GU,
               'GTCCID': self.GTCCID,
               'GTCSID': self.GTCSID,
               'MasterTime': self.MasterTime,
               'PropDelay': self.PropDelay,
               }

        return jds | jd

    def __str__(self):
        r = super().__str__()
        # Revisit: fix csv columns
        r += (',,,,,,,,,{},,,,,{},{}' if self.csv else ', TP: {}, SV: {}, GU: {}').format(self.TP, self.SV, self.GU)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:03x}'.format(self.R0)
        if self.csv:
            r += (',,{},,{}' if self.csv else ', GTCCID: {:03x}, GTCSID: {:04x}').format(
                self.GTCCID, self.GTCSID)
        else:
            if self.SV:
                r += ', GTCGCID: {:04x}:{:03x}'.format(self.GTCSID, self.GTCCID)
            else:
                r += ', GTCCID: {:03x}'.format(self.GTCCID)
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {:01x}'.format(self.R1)
        r += (',,{},,{}' if self.csv else ', MasterTime: {:016x}, PropDelay: {:08x}').format(
            self.MasterTime, self.PropDelay)
        if self.verbosity > 1 and not self.csv:
            r += ', R2: {:02x}'.format(self.R2)
        r += (',,,,,,,,,,,,,,{}' if self.csv else ', ECRC:{1}{0:06x}').format(self.ECRC, self.ecrc_sep)
        r += self.expected_ecrc_str
        return r

class Adv2PTRSPPkt(Adv2PTRSPBase):
    def __new__(cls, ocl, opcode, payLen, verbosity=0, GC:bool = False,
                NH:bool = False, data = None, **kwargs):
        className = Packet.className(ocl, opcode)
        pkt_type, pktLen = Adv2PTRSPBase.pkt_type(className, 0,
                                GC=GC, NH=NH, data=data, verbosity=verbosity)
        return pkt_type(ocl, opcode, pktLen, GC=GC, NH=NH, data=data,
                        verbosity=verbosity, **kwargs)
