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
import shutil
from pdb import set_trace
from .genz_common import *

cols, lines = shutil.get_terminal_size()

# Based on Gen-Z revision 1.1 final

# Revisit: this should be auto-generated from the v1.1.xml file

cclass_name = [ 'reserved',    'memory_p2p64', 'memory',      'int_switch',
                'exp_switch',  'fab_switch',   'processor',   'processor',
                'accelerator', 'accelerator',  'accelerator', 'accelerator',
                'io',          'io',           'io',          'io',
                'block',       'block',        'tr',          'multi_class',
                'bridge',      'bridge',       'compliance',  'lph' ]

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

    _fields_    = [('field', CStatusFields), ('val', c_u64)]
    _c_state = ['C-Down', 'C-CFG', 'C-Up', 'C-LP', 'C-DLP']
    _therm   = ['Nominal', 'Caution', 'Exceeded', 'Shutdown']
    _special = {'CState': _c_state, 'ThermStatus': _therm}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
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

    _fields_    = [('field', CControlFields), ('val', c_u64)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
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
                    ('Rv',                  c_u64,  1),
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
                    ('Rv',                  c_u64,  2),
                    ('NIRTSup',             c_u64,  1),
                    ('Rv',                  c_u64,  1),
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

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
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
                    ('Rv',                         c_u64,  1),
                    ('NextHdrPrecTimeEnb',         c_u64,  1),
                    ('InbandMgmtDisable',          c_u64,  1),
                    ('OOBMgmtDisable',             c_u64,  1),
                    ('AutoCStateEnb',              c_u64,  1),
                    ('VdefPwrMgmtEnb',             c_u64,  1),
                    ('MaxPwrCtl',                  c_u64,  3),
                    ('EmergPwrReductEnb',          c_u64,  1),
                    ('NotifyPeerCStateEnb',        c_u64,  1),
                    ('Rv',                         c_u64,  1),
                    ('CStatePwrCtlEnb',            c_u64,  1),
                    ('LowestAutoCState',           c_u64,  3),
                    ('InitiateAllStatsSnap',       c_u64,  1),
                    ('InitiateAllIfaceStatsSnap',  c_u64,  1),
                    ('Rv',                         c_u64,  2),
                    ('MCTPEnb',                    c_u64,  1),
                    ('MetaRWHdrEnb',               c_u64,  1),
                    ('HostMgrMGRUUIDEnb',          c_u64,  2),
                    ('MGRUUIDEnb',                 c_u64,  1),
                    ('LoopbackEnb',                c_u64,  1),
                    ('Rv',                         c_u64, 26),
                    ('SWMgmt0',                    c_u64,  1),
                    ('SWMgmt1',                    c_u64,  1),
                    ('SWMgmt2',                    c_u64,  1),
                    ('SWMgmt3',                    c_u64,  1),
                    ('SWMgmt4',                    c_u64,  1),
                    ('SWMgmt5',                    c_u64,  1),
                    ('SWMgmt6',                    c_u64,  1),
                    ('SWMgmt7',                    c_u64,  1),
        ]

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

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class CAP2Control(SpecialField, Union):
    class CAP2ControlFields(Structure):
        _fields_ = [('Rv',                         c_u64,  1),
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
                    ('Rv',                         c_u64,  2),
                    ('DIPIBlockSize',              c_u64,  3),
                    ('BUFREQT10DIFPIEnb',          c_u64,  1),
                    ('Rv',                         c_u64,  3),
                    ('RSPLPDType5Enb',             c_u64,  1),
                    ('REQLPDType5Enb',             c_u64,  1),
                    ('EnqueueEmbeddedRdEnb',       c_u64,  1),
                    ('Rv',                         c_u64, 39),
        ]

    _fields_     = [('field', CAP2ControlFields), ('val', c_u64)]
    _di_pi_sz    = ['512B', '4KiB']
    _special = {'DIPIBlockSize': _di_pi_sz
    }

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
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

    _fields_    = [('field', IStatusFields), ('val', c_u32)]
    _i_state    = ['I-Down', 'I-CFG', 'I-Up', 'I-LP']
    _ctl_stat   = ['InProgress', 'ACKReceived', 'UnsupLinkCTL',
                   'UnableToCompleteLinkCTLReq', 'UnsupLLR', 'UnauthLinkCTL',
                   'UnsupPHYStateReq', 'UnableToCompleteLUpLLP']
    _special = {'IState': _i_state, 'LinkCTLComplStatus': _ctl_stat}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

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

    _fields_    = [('field', IControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
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
                    ('Rv',                       c_u32,  1),
                    ('P2P64Sup',                 c_u32,  1),
                    ('P2PVdefSup',               c_u32,  1),
                    ('Rv',                       c_u32,  1),
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
                    ('Rv',                       c_u32,  1),
                    ('AggIfaceSup',              c_u32,  1),
                    ('AggIfaceRole',             c_u32,  1),
                    ('PeerNonceValidationSup',   c_u32,  1),
                    ('P2PStandaloneAckRequired', c_u32,  1),
                    ('IfaceGroupSup',            c_u32,  1),
                    ('IfaceGroupSingleOpClass',  c_u32,  1),
                    ('P2PBackupSup',             c_u32,  1),
        ]

    _fields_    = [('field', ICAP1Fields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class ICAP1Control(SpecialField, Union):
    class ICAP1ControlFields(Structure):
        _fields_ = [('Rv',                               c_u32,  1),
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
                    ('Rv',                               c_u32,  1),
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

    _fields_    = [('field', ICAP1ControlFields), ('val', c_u32)]

    _opclass    = ['NotConfig', 'Explicit', 'P2P64', 'P2PVdef',
                   'Rv', 'Rv', 'Rv', 'Incompatible']
    _agg_iface  = ['Independent', 'NAI', 'SAI', 'Rv']
    _special = {'OpClassSelect': _opclass, 'AggIfaceCtl': _agg_iface}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class ICAP2(SpecialField, Union):
    class ICAP2Fields(Structure):
        _fields_ = [('TEHistSize',               c_u32,  3),
                    ('Rv',                       c_u32, 29),
        ]

    _fields_    = [('field', ICAP2Fields), ('val', c_u32)]

    _te_hist_sz = ['256', '512', '1024']
    _special = {'TEHistSize': _te_hist_sz}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class ICAP2Control(SpecialField, Union):
    class ICAP2ControlFields(Structure):
        _fields_ = [('SWMgmtI0',                         c_u32,  1),
                    ('SWMgmtI1',                         c_u32,  1),
                    ('Rv',                               c_u32, 30),
        ]

    _fields_    = [('field', ICAP2ControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

# for IErrorStatus/IErrorDetect/IErrorFaultInjection/IErrorTrigger
class IError(SpecialField, Union):
    class IErrorFields(Structure):
        _fields_ = [('ExcessivePHYRetraining',           c_u16,  1),
                    ('NonTransientLinkErr',              c_u16,  1),
                    ('IfaceContainment',                 c_u16,  1),
                    ('IfaceAKEYViolation',               c_u16,  1),
                    ('IfaceFCFwdProgressViolation',      c_u16,  1),
                    ('UnexpectedPHYFailure',             c_u16,  1),
                    ('P2PSECE',                          c_u16,  1),
                    ('IfaceAE',                          c_u16,  1),
                    ('SwitchPktRelayFailure',            c_u16,  1),
                    ('Rv',                               c_u16,  7),
        ]

    _fields_    = [('field', IErrorFields), ('val', c_u16)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class PeerState(SpecialField, Union):
    class PeerStateFields(Structure):
        _fields_ = [('PeerCState',                       c_u32,  3),
                    ('PeerMgrType',                      c_u32,  1),
                    ('PeerCIDValid',                     c_u32,  1),
                    ('PeerSIDValid',                     c_u32,  1),
                    ('PeerIfaceIDValid',                 c_u32,  1),
                    ('Rv',                               c_u32,  1),
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

    _fields_    = [('field', PeerStateFields), ('val', c_u32)]

    _c_state    = ['C-Down', 'C-CFG', 'C-Up', 'C-LP', 'C-DLP']
    _mgr_type   = ['Primary', 'Fabric']
    _opclass    = ['NotConfig', 'Explicit', 'P2P64', 'P2PVdef']
    _fc_sup     = ['Implicit', 'Explicit', 'Implicit+Explicit']
    _special = {'PeerCState': _c_state, 'PeerMgrType': _mgr_type,
                'PeerIfaceFCSup': _fc_sup,
                'PeerUniformOpClassSelected': _opclass}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class LinkCTLControl(SpecialField, Union):
    class LinkCTLControlFields(Structure):
        _fields_ = [('Rv',                               c_u32,  2),
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

    _fields_    = [('field', LinkCTLControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
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

    _fields_    = [('field', PHYStatusFields), ('val', c_u64)]
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

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class PHYType(SpecialField, Union):
    class PHYTypeFields(Structure):
        _fields_ = [('PHYType',             c_u8,   8)]

    _fields_    = [('field', PHYTypeFields), ('val', c_u8)]
    _phy_type = ['25GFabric', '25GLocal', 'PCIe']
    _special = {'PHYType': _phy_type}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class PACAP1(SpecialField, Union):
    class PACAP1Fields(Structure):
        _fields_ = [('PAIdxSz',             c_u32,  2),
                    ('PAEntrySz',           c_u32,  2),
                    ('Rv',                  c_u32,  2),
                    ('WildcardAKeySup',     c_u32,  1),
                    ('WildcardPASup',       c_u32,  1),
                    ('Rv',                  c_u32,  1),
                    ('WildcardACREQSup',    c_u32,  1),
                    ('WildcardACRSPSup',    c_u32,  1),
                    ('Rv',                  c_u32, 21),
        ]

    _fields_    = [('field', PACAP1Fields), ('val', c_u32)]
    _pa_idx_sz = ['0bits', '8bits', '16bits']
    _pa_ent_sz = ['16bits']
    _special = {'PAIdxSz': _pa_idx_sz, 'PAEntrySz': _pa_ent_sz}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class PACAP1Control(SpecialField, Union):
    class PACAP1ControlFields(Structure):
        _fields_ = [('AKeyEnb',                          c_u32,  1),
                    ('Rv',                               c_u32, 31),
        ]

    _fields_    = [('field', PACAP1ControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class CPageSz(SpecialField, Union):
    class CPageSzFields(Structure):
        _fields_ = [('CPageSz',             c_u8,   4)]

    _fields_    = [('field', CPageSzFields), ('val', c_u8)]
    _cpage_sz = ['4KiB', '64KiB', '1MiB', '32MiB']
    _special = {'CPageSz': _cpage_sz}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class CAccessCAP1(SpecialField, Union):
    class CAccessCAP1Fields(Structure):
        _fields_ = [('LACSup',                 c_u8,  1),
                    ('P2PACSup',               c_u8,  1),
                    ('Rv',                     c_u8,  2),
        ]


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


    _fields_    = [('field', CAccessCTLFields), ('val', c_u8)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class PGZMMUCAP1(SpecialField, Union):
    class PGZMMUCAP1Fields(Structure):
        _fields_ = [('ZMMUType',                 c_u32,  1),
                    ('LPDRspNoBypassSup',        c_u32,  1),
                    ('LPDRspBypassSup',          c_u32,  1),
                    ('LPDRspBypassCtlSup',       c_u32,  1),
                    ('Rv',                       c_u32, 28),
        ]


    _fields_    = [('field', PGZMMUCAP1Fields), ('val', c_u32)]
    _type    = ['ReqZMMU', 'RspZMMU']
    _special = {'ZMMUType': _type}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class PTZMMUCAP1(SpecialField, Union):
    class PTZMMUCAP1Fields(Structure):
        _fields_ = [('ZMMUType',                 c_u32,  1),
                    ('LPDRspNoBypassSup',        c_u32,  1),
                    ('LPDRspBypassSup',          c_u32,  1),
                    ('LPDRspBypassCtlSup',       c_u32,  1),
                    ('Rv',                       c_u32, 28),
        ]


    _fields_    = [('field', PTZMMUCAP1Fields), ('val', c_u32)]
    _type    = ['ReqZMMU', 'RspZMMU']
    _special = {'ZMMUType': _type}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class PTEATTRl(SpecialField, Union):
    class ReqPTEATTRlFields(Structure):
        _fields_ = [('GdSz',                     c_u64,  5),
                    ('Rv',                       c_u64,  5),
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
                    ('Rv',                       c_u64,  5),
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

    def __init__(self, value, parent, verbosity=0):
        # Revisit: PG vs PT
        cap1 = PGZMMUCAP1(parent.PGZMMUCAP1, parent)
        self.zmmuType = cap1.field.ZMMUType
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

    @property
    def field(self):
        return self.rsp if self.zmmuType == 1 else self.req

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

    _fields_    = [('field', SwitchCAP1Fields), ('val', c_u32)]
    _scale   = ['ps', 'ns']
    _special = {'ULATScale': _scale, 'MLATScale': _scale}

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class SwitchCAP1Control(SpecialField, Union):
    class SwitchCAP1ControlFields(Structure):
        _fields_ = [('MCPRTEnb',                          c_u32,  1),
                    ('MSMCPRTEnb',                        c_u32,  1),
                    ('DefaultMCPktRelayEnb',              c_u32,  1),
                    ('DefaultCollPktRelayEnb',            c_u32,  1),
                    ('Rv',                                c_u32, 28),
        ]

    _fields_    = [('field', SwitchCAP1ControlFields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class SwitchOpCTL(SpecialField, Union):
    class SwitchOpCTLFields(Structure):
        _fields_ = [('PktRelayEnb',                       c_u16,  1),
                    ('Rv',                                c_u16, 15),
        ]

    _fields_    = [('field', SwitchOpCTLFields), ('val', c_u16)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class VCAT4(SpecialField, Union):
    class VCAT4Fields(Structure):
        _fields_ = [('VCM',             c_u32,   32)]

    _fields_    = [('field', VCAT4Fields), ('val', c_u32)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
        self.val = value

class VCAT8(SpecialField, Union):
    class VCAT8Fields(Structure):
        _fields_ = [('VCM',             c_u64,   32),
                    ('TH',              c_u64,    7),
                    ('Rv',              c_u64,   25),
        ]

    _fields_    = [('field', VCAT8Fields), ('val', c_u64)]

    def __init__(self, value, parent, verbosity=0):
        super().__init__(value, parent, verbosity=verbosity)
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
              'Read'                                : 0x1b,
              'CtlCTXIDNIRRelease'                  : 0x1c,
              'CtlNIRRelease'                       : 0x1d,
              'UnreliableCtlWriteMSG'               : 0x1e,
              'CtlWriteMSG'                         : 0x1f,
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
              'UnreliableEncapRequest'              : 0x04,
              'Write'                               : 0x05,
              'ReliableEncapRequest'                : 0x06,
              'UnreliableWrite'                     : 0x08,
              'VendorDefined1'                      : 0x1a,
              'VendorDefined2'                      : 0x1b,
              'VendorDefined3'                      : 0x1c,
              'VendorDefined4'                      : 0x1d,
              'UnreliableWriteMSG'                  : 0x1e,
              'WriteMSG'                            : 0x1f,
              }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class SODOpcodes(Opcodes):
    _map = {  'SODACK'                              : 0x00,
              'SODReadResponse'                     : 0x01,
              'SODEncapResponse'                    : 0x02,
              'SODWrite'                            : 0x04,
              'SODSync'                             : 0x05,
              'SODWritePersistent'                  : 0x06,
              'SODInterrupt'                        : 0x08,
              'SODEnqueue'                          : 0x09,
              'SODDequeue'                          : 0x0a,
              'SODNIRR'                             : 0x0b,
              'SODRead'                             : 0x1b,
              'SODEncapRequest'                     : 0x1c,
              }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class CTXIDOpcodes(Opcodes):
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
              'UnreliableWriteMSG'                  : 0x1e,
              'WriteMSG'                            : 0x1f,
              }

    _inverted_map = {v : k for k, v in _map.items()}
    _list = sorted(_map.items(), key=lambda x: x[1])

class DROpcodes(Opcodes):
    _map = {  'StandaloneAck'                       : 0x00,
              'ReadResponse'                        : 0x01,
              'Write'                               : 0x04,
              'Read'                                : 0x1b,
              'UnreliableCtlWriteMSG'               : 0x1e,
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

    _struct = { 'core'                        : 'CoreStructure',
                'opcode_set'                  : 'OpCodeSetStructure',
                'interface'                   : 'InterfaceStructure',
                # interfaceX has the optional fields
                'interfaceX'                  : 'InterfaceXStructure',
                'interface_phy'               : 'InterfacePHYStructure',
                'interface_statistics'        : 'InterfaceStatisticsStructure',
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
                'service_uuid'                : 'ServiceUUIDStructure',
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
                'opcode_set_table'            : 'OpCodeSetTable',
                'opcode_set_uuid'             : 'OpCodeSetUUIDTable',
                'req_vcat'                    : 'RequesterVCATTable',
                'rsp_vcat'                    : 'ResponderVCATTable',
                'rit'                         : 'RITTable',
                'ssdt'                        : 'SSDTTable',
                'msdt'                        : 'MSDTTable',
                'lprt'                        : 'LPRTTable',
                'mprt'                        : 'MPRTTable',
                'vcat'                        : 'VCATTable',
                'c_access_r_key'              : 'CAccessRKeyTable',
                'c_access_l_p2p'              : 'CAccessLP2PTable',
                'pg_base'                     : 'PGTable',  # Revisit - delete
                'restricted_pg_base'          : 'PGTable',  # Revisit - delete
                'pg_table'                    : 'PGTable',
                'restricted_pg_table'         : 'PGTable',
                'pte_table'                   : 'PTETable',
                'restricted_pte_table'        : 'PTETable',
                'pa'                          : 'PATable',
                'ssap'                        : 'SSAPTable',
                'mcap'                        : 'MCAPTable',
                'msap'                        : 'MSAPTable',
                'msmcap'                      : 'MSMCAPTable',
    }

    def nameToId(self, name):
        return self._map[name]

    def idToName(self, id):
        return self._inverted_map[id]

    def fileToStruct(self, file, data, verbosity=0, fd=None, path=None,
                     parent=None, core=None):
        struct = globals()[self._struct[file]].from_buffer(data)
        struct.data = data
        struct.verbosity = verbosity
        struct.fd = fd
        struct.path = path
        struct.parent = parent
        struct.core = core
        struct.fileToStructInit()
        return struct

#Revisit: jmh - this is almost totally version independent
class ControlStructure(ControlStructureMap):
    def __init__(self):
        super().__init__()
        bitOffset = 0
        for field in self._fields_:
            width = field[2]
            byteOffset, highBit, lowBit, hexWidth = self.bitField(width, bitOffset)
            field.byteOffset = byteOffset

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
            width = field[2]
            if skipNext:
                bitOffset += width
                skipNext = False
                continue
            byteOffset, highBit, lowBit, hexWidth = self.bitField(width, bitOffset)
            if byteOffset >= self.Size * 16:
                break
            uu = self.isUuid(name)
            if uu is not None:
                r += '    {0:{nw}}@0x{1:0>3x} = {2}\n'.format(
                    name[:-1], byteOffset, uu, nw=max_len)
                skipNext = True
            else:
                r += '    {0:{nw}}@0x{1:0>3x}{{{2:2}:{3:2}}} = 0x{4:0>{hw}x}\n'.format(
                    name, byteOffset, highBit, lowBit,
                    getattr(self, name),
                    nw=max_len, hw=hexWidth)
                if self.verbosity < 3:
                    continue
                special = self.isSpecial(name)
                if special is not None:
                    specialStr = textwrap.fill(
                        str(special), expand_tabs=False, width=cols,
                        initial_indent='      ', subsequent_indent='      ')
                    if specialStr != '':
                        r += '{}\n'.format(specialStr)
            bitOffset += width
        #for subStruct in self.subStructs:
        #    r += str(subStruct)
        return r

    def __repr__(self):
        r = type(self).__name__ + '('
        l = len(self._fields_)
        for i, field in enumerate(self._fields_, start=1):
            fmt = '{}=0x{:x}, ' if i < l else '{}=0x{:x})'
            r += fmt.format(field[0], getattr(self, field[0]))
        return r

    def fileToStructInit(self):
        pass

class ControlTable(ControlStructure):
    def fileToStructInit(self):
        self.stat = self.path.stat()

    @property
    def Size(self):
        return self.stat.st_size

class ControlTableArray(ControlTable):
    def __getitem__(self, key):
        return self.array[key]

    def __len__(self):
        return len(self.array)

    def __str__(self):
        # Revisit: handle 2-dimensional arrays, like VCAT
        r = type(self).__name__
        if self.verbosity < 2:
            return r
        r += ':\n'
        if self.verbosity < 4:
            return r
        elif self.verbosity == 4:
            name = type(self.array[0]).__name__
            for i in range(len(self)):
                r += '    {}[{}]={}\n'.format(name, i, repr(self.array[i]))
        else:
            # Revisit: the str() output should be indented another 2 spaces
            name = type(self.array[0]).__name__
            for i in range(len(self)):
                r += '    {}[{}]={}\n'.format(name, i, str(self.array[i]))

        return r

    def __repr__(self):
        return repr(self.array)

#Revisit: jmh - this is version independent
class ControlHeader(ControlStructure):
    _fields_ = [('Type',          c_u64, 12),
                ('Vers',          c_u64,  4),
                ('Size',          c_u64, 16),
                ]

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
                      'CAP2Control': CAP2Control }

class ComponentDestinationTableStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),  # Basic OpCode Set Fields
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
                ('RouteControlPTR',            c_u64, 32),
                ('SSDTPTR',                    c_u64, 32),
                ('MSDTPTR',                    c_u64, 32),
                ('REQVCATPTR',                 c_u64, 32),
                ('RITPTR',                     c_u64, 32),
                ('RSPVCATPTR',                 c_u64, 32),
                ('R2',                         c_u64, 32),
                ('R3',                         c_u64, 64)]

    _ptr_fields = ['RouteControlPtr', 'SSDTPTR', 'MSDTPTR', 'REQVCATPTR',
                   'RITPTR', 'RSPVCATPTR']

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

class OpCodeSetTable(ControlTable):
    _fields_ = [('SetID',                          c_u64,  3),
                ('R0',                             c_u64, 13),
                ('Control1',                       c_u64, 16),
                ('NextOpcodeSetPtr',               c_u64, 32),
                ('R1',                             c_u64, 64),
                ('SupportedCore64OpCodeSet',       c_u64, 64),
                ('EnabledCore64OpCodeSet',         c_u64, 64),
                ('SupportedControlOpCodeSet',      c_u64, 64),
                ('EnabledControlOpCodeSet',        c_u64, 64),
                ('SupportedP2P64OpCodeSet',        c_u64, 64),
                ('EnabledP2P64OpCodeSet',          c_u64, 64),
                ('SupportedAtomic1OpCodeSet',      c_u64, 64),
                ('EnabledAtomic1OpCodeSet',        c_u64, 64),
                ('SupportedLDM1OpCodeSet',         c_u64, 64),
                ('EnabledLDM1OpCodeSet',           c_u64, 64),
                ('SupportedAdvanced1OpCodeSet',    c_u64, 64),
                ('EnabledAdvanced1OpCodeSet',      c_u64, 64),
                # Revisit: Advanced2 (0x5) is missing in Core spec
                ('SupportedOpClass0x6OpCodeSet',   c_u64, 64),
                ('EnabledOpClass0x6OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x7OpCodeSet',   c_u64, 64),
                ('EnabledOpClass0x7OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x8OpCodeSet',   c_u64, 64),
                ('EnabledOpClass0x8OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x9OpCodeSet',   c_u64, 64),
                ('EnabledOpClass0x9OpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xaOpCodeSet',   c_u64, 64),
                ('EnabledOpClass0xaOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xbOpCodeSet',   c_u64, 64),
                ('EnabledOpClass0xbOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xcOpCodeSet',   c_u64, 64),
                ('EnabledOpClass0xcOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xdOpCodeSet',   c_u64, 64),
                ('EnabledOpClass0xdOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xeOpCodeSet',   c_u64, 64),
                ('EnabledOpClass0xeOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0xfOpCodeSet',   c_u64, 64),
                ('EnabledOpClass0xfOpCodeSet',     c_u64, 64),
                ('SupportedOpClass0x10OpCodeSet',  c_u64, 64),
                ('EnabledOpClass0x10OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x11OpCodeSet',  c_u64, 64),
                ('EnabledOpClass0x11OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x12OpCodeSet',  c_u64, 64),
                ('EnabledOpClass0x12OpCodeSet',    c_u64, 64),
                ('SupportedOpClass0x13OpCodeSet',  c_u64, 64),
                ('EnabledOpClass0x13OpCodeSet',    c_u64, 64),
                ('SupportedDROpCodeSet',           c_u64, 64),
                ('EnabledDROpCodeSet',             c_u64, 64),
                ('SupportedCtxIdOpCodeSet',        c_u64, 64),
                ('EnabledCtxIdOpCodeSet',          c_u64, 64),
                ('SupportedMulticastOpCodeSet',    c_u64, 64),
                ('EnabledMulticastOpCodeSet',      c_u64, 64),
                ('SupportedSODOpCodeSet',          c_u64, 64),
                ('EnabledSODOpCodeSet',            c_u64, 64),
                ('SupportedMultiOpReqSubOpSet',    c_u64, 64),
                ('EnabledMultiOpReqSubOpSet',      c_u64, 64),
                ('SupportedReadMultiOpSet',        c_u64, 32),
                ('EnabledReadMultiOpSet',          c_u64, 32),
                ('R2',                             c_u64, 64),
                ]

    _ptr_fields = ['NextOpcodeSetPtr']

    _special_dict = { 'SupportedCore64OpCodeSet'      : Core64Opcodes,
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
                      'SupportedDROpCodeSet'          : DROpcodes,
                      'EnabledDROpCodeSet'            : DROpcodes,
                      'SupportedCtxIdOpCodeSet'       : CTXIDOpcodes,
                      'EnabledCtxIdOpCodeSet'         : CTXIDOpcodes,
                      'SupportedMulticastOpCodeSet'   : MulticastOpcodes,
                      'EnabledMulticastOpCodeSet'     : MulticastOpcodes,
                      'SupportedSODOpCodeSet'         : SODOpcodes,
                      'EnabledSODOpCodeSet'           : SODOpcodes,
                      # Revisit: jmh - finish this
    }

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

class InterfaceStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12), #0x0
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
                ('IErrorFaultInjection',       c_u64, 16),
                ('IErrorTrigger',              c_u64, 16),
                ('ISignalTarget',              c_u64, 48), #0x28
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

    #_ptr_fields = ['NextIPTR', 'IPHYPTR', 'VDPTR', 'ISTATSPTR', 'IARBPTR', 'MechanicalPTR']
    _special_dict = { 'IStatus': IStatus, 'IControl': IControl,
                      'ICAP1': ICAP1, 'ICAP1Control': ICAP1Control,
                      'ICAP2': ICAP2, 'ICAP2Control': ICAP2Control,
                      'IErrorStatus': IError, 'IErrorDetect': IError,
                      'IErrorFaultInjection': IError, 'IErrorTrigger': IError,
                      'PeerState': PeerState, 'LinkCTLControl': LinkCTLControl}

class InterfaceXStructure(ControlStructure):
    '''InterafceXStructure is the same as InterfaceStructure, but with
    the optional fields included'''
    # Revisit: figure out how to dynamically create this class
    _fields_ = [('Type',                       c_u64, 12), #0x0
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
                ('IErrorFaultInjection',       c_u64, 16),
                ('IErrorTrigger',              c_u64, 16),
                ('ISignalTarget',              c_u64, 48), #0x28
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
                # optional fields
                ('VCATPTR',                    c_u64, 32), #0x90
                ('LPRTPTR',                    c_u64, 32),
                ('MPRTPTR',                    c_u64, 32), #0x98
                ('R7',                         c_u64, 32),
                ('IngressAKeyMask',            c_u64, 64), #0xA0
                ('EgressAKeyMask',             c_u64, 64), #0xA8
                ]

    _special_dict = { 'IStatus': IStatus, 'IControl': IControl,
                      'ICAP1': ICAP1, 'ICAP1Control': ICAP1Control,
                      'ICAP2': ICAP2, 'ICAP2Control': ICAP2Control,
                      'IErrorStatus': IError, 'IErrorDetect': IError,
                      'IErrorFaultInjection': IError, 'IErrorTrigger': IError,
                      'PeerState': PeerState, 'LinkCTLControl': LinkCTLControl}

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

class InterfaceStatisticsStructure(ControlStructure):
    _fields_ = [('Type',                       c_u64, 12),  # Basic Statistics Fields
                ('Vers',                       c_u64,  4),
                ('Size',                       c_u64, 16),
                ('Status',                     c_u64,  4),
                ('SCTL',                       c_u64,  4),
                ('R0',                         c_u64,  8),
                ('VendorDefinedPtr',           c_u64, 16),
                ('CRCTransientErrors',         c_u64, 16),
                ('MiscE2ETE',                  c_u64, 12),
                ('E2ENTE',                     c_u64, 12),
                ('LinkTransientError',         c_u64, 16),
                ('LinkNTEError',               c_u64,  8),
                ('TxStompedECRC',              c_u64, 16),
                ('RxStompedECRC',              c_u64, 16),
                ('EgressAKEYV',                c_u64, 16),
                ('IngressAKEYV',               c_u64, 16),
                ('VC0ExFC',                    c_u64, 16),
                ('VC1ExFC',                    c_u64, 16),
                ('VC2ExFC',                    c_u64, 16),
                ('VC3ExFC',                    c_u64, 16),
                ('VC4ExFC',                    c_u64, 16),
                ('VC5ExFC',                    c_u64, 16),
                ('VC6ExFC',                    c_u64, 16),
                ('VC7ExFC',                    c_u64, 16),
                ('FPTExpirations',             c_u64, 16),
                ('R1',                         c_u64, 32),
                ('InterfaceSPIR',              c_u64, 16),
                ('VC0SPIR',                    c_u64, 16),
                ('VC1SPIR',                    c_u64, 16),
                ('VC2SPIR',                    c_u64, 16),
                ('VC3SPIR',                    c_u64, 16),
                ('VC4SPIR',                    c_u64, 16),
                ('VC5SPIR',                    c_u64, 16),
                ('VC6SPIR',                    c_u64, 16),
                ('VC7SPIR',                    c_u64, 16),
                # Revisit: jmh - finish this
                ]

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

    _special_dict = {'PACAP1': PACAP1, 'PACAP1Ctl': PACAP1Control}

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
                ('MV0',                        c_u64,  1),
                ('MGMTVC0',                    c_u64,  5),
                ('MGMTIfaceID0',               c_u64, 12),
                ('MV1',                        c_u64,  1),
                ('MGMTVC1',                    c_u64,  5),
                ('MGMTIfaceID1',               c_u64, 12),
                ('MV2',                        c_u64,  1),
                ('MGMTVC2',                    c_u64,  5),
                ('MGMTIfaceID2',               c_u64, 12),
                ('R5',                         c_u64, 10),
                ('MV3',                        c_u64,  1),
                ('MGMTVC3',                    c_u64,  5),
                ('MGMTIfaceID3',               c_u64, 12),
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

class VendorDefinedStructure(ControlStructure):
    _fields_ = [('Type',                       c_u32, 12), #0x0
                ('Vers',                       c_u32,  4),
                ('Size',                       c_u32, 16)]
    # Revisit: print rest of structure in hex?

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

class UnknownStructure(ControlStructure):
    _fields_ = [('Type',                       c_u32, 12),
                ('Vers',                       c_u32,  4),
                ('Size',                       c_u32, 16)]
    # Revisit: print rest of structure in hex?

class PATable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: subfields
        fields = [('PeerAttr',  c_u16, 16)
        ]
        PA = type('PA', (ControlStructure,), {'_fields_': fields,
                                              'verbosity': self.verbosity,
                                              'Size': 2}) # Revisit
        items = self.Size // sizeof(PA)
        self.array = (PA * items).from_buffer(self.data)
        self.element = PA

class RequesterVCATTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: need parent/core so we can dynamically build VCAT based on
        # HCS, max_hvs, etc.
        fields = [('VCM',       c_u32, 32)
        ]
        VCAT = type('VCAT', (ControlStructure,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 4}) # Revisit
        items = self.Size // sizeof(VCAT)
        self.array = (VCAT * items).from_buffer(self.data)
        self.element = VCAT

class ResponderVCATTable(ControlTableArray):
    # Revisit: identical to RequesterVCATTable
    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: need parent/core so we can dynamically build VCAT based on
        # HCS, max_hvs, etc.
        fields = [('VCM',       c_u32, 32)
        ]
        VCAT = type('VCAT', (ControlStructure,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 4}) # Revisit
        items = self.Size // sizeof(VCAT)
        self.array = (VCAT * items).from_buffer(self.data)
        self.element = VCAT

class VCATTable(ControlTableArray):
    # Revisit: identical to RequesterVCATTable/ResponderVCATTable
    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: need parent/core so we can dynamically build VCAT based on
        # HCS, max_hvs, etc.
        fields = [('VCM',       c_u32, 32)
        ]
        VCAT = type('VCAT', (ControlStructure,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 4}) # Revisit
        items = self.Size // sizeof(VCAT)
        self.array = (VCAT * items).from_buffer(self.data)
        self.element = VCAT

class RITTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: need parent/core so we can dynamically build RIT based on
        # MaxInterface, RITPadSize, etc.
        fields = [('EIM',       c_u32, 32)
        ]
        RIT = type('RIT', (ControlStructure,), {'_fields_': fields,
                                                'verbosity': self.verbosity,
                                                'Size': 4}) # Revisit
        items = self.Size // sizeof(RIT)
        self.array = (RIT * items).from_buffer(self.data)
        self.element = RIT

# for SSDT, MSDT, LPRT, and MPRT
class SSDTMSDTLPRTMPRTTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: need parent so we can dynamically build SSDT based on
        # SSDTSize, SSDTMSDTRowSize, etc.
        fields = [('MHC',       c_u32,  6),
                  ('R0',        c_u32,  2),
                  ('V',         c_u32,  1),
                  ('HC',        c_u32,  6),
                  ('VCA',       c_u32,  5),
                  ('EI',        c_u32, 12),
        ]
        SSDT = type(self._name, (ControlStructure,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 4}) # Revisit
        items = self.Size // sizeof(SSDT)
        self.array = (SSDT * items).from_buffer(self.data)
        self.element = SSDT

class SSDTTable(SSDTMSDTLPRTMPRTTable):
    def fileToStructInit(self):
        self._name = 'SSDT'
        super().fileToStructInit()

class MSDTTable(SSDTMSDTLPRTMPRTTable):
    def fileToStructInit(self):
        self._name = 'MSDT'
        super().fileToStructInit()

class LPRTTable(SSDTMSDTLPRTMPRTTable):
    def fileToStructInit(self):
        self._name = 'LPRT'
        super().fileToStructInit()

class MPRTTable(SSDTMSDTLPRTMPRTTable):
    def fileToStructInit(self):
        self._name = 'MPRT'
        super().fileToStructInit()

# for SSAP, MCAP, MSAP, and MSMCAP
class SSAPMCAPMSAPMSMCAPTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # use parent to dynamically build SSAP entry based on PAIdxSz & PadSz
        cap1 = PACAP1(self.parent.PACAP1, self.parent)
        pa_idx_sz = cap1.field.PAIdxSz * 8  # bytes to bits
        pad_sz = self.parent.PadSz
        fields = []
        if pa_idx_sz > 0:
            fields.append(('PAIdx',       c_u32,  pa_idx_sz))
        fields.append(('AKey',            c_u32,  6))
        fields.append(('ACREQ',           c_u32,  2))
        fields.append(('ACRSP',           c_u32,  2))
        if pad_sz > 0:
            fields.append(('Pad',         c_u32,  pad_sz))
        SSAP = type(self._name, (ControlStructure,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 4})
        items = self.Size // sizeof(SSAP)
        self.array = (SSAP * items).from_buffer(self.data)
        self.element = SSAP

class SSAPTable(SSAPMCAPMSAPMSMCAPTable):
    def fileToStructInit(self):
        self._name = 'SSAP'
        super().fileToStructInit()

class MCAPTable(SSAPMCAPMSAPMSMCAPTable):
    def fileToStructInit(self):
        self._name = 'MCAP'
        super().fileToStructInit()

class MSAPTable(SSAPMCAPMSAPMSMCAPTable):
    def fileToStructInit(self):
        self._name = 'MSAP'
        super().fileToStructInit()

class MSMCAPTable(SSAPMCAPMSAPMSMCAPTable):
    def fileToStructInit(self):
        self._name = 'MSMCAP'
        super().fileToStructInit()

class CAccessRKeyTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        fields = [('RORKey',      c_u64, 32),
                  ('RWRKey',      c_u64, 32),
        ]
        RKey = type('RKey', (ControlStructure,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 8})
        items = self.Size // sizeof(RKey)
        self.array = (RKey * items).from_buffer(self.data)
        self.element = RKey

class CAccessLP2PTable(ControlTableArray):
    def fileToStructInit(self):
        super().fileToStructInit()
        # Revisit: decode subfield values
        fields = [('LAC',         c_u8,  3),
                  ('P2PAC',       c_u8,  3),
                  ('Rv',          c_u8,  2),
        ]
        LP2P = type('LP2P', (ControlStructure,), {'_fields_': fields,
                                                  'verbosity': self.verbosity,
                                                  'Size': 1})
        items = self.Size // sizeof(LP2P)
        self.array = (LP2P * items).from_buffer(self.data)
        self.element = LP2P

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
        PG = type('PG', (ControlStructure,), {'_fields_': fields,
                                              'verbosity': self.verbosity,
                                              'Size': 16})
        items = self.Size // sizeof(PG)
        self.array = (PG * items).from_buffer(self.data)
        self.element = PG

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
        return fields

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
            fields.extend(self.splitField(('RORKey',  c_u64, 32), bits))
            bits += 32
            fields.extend(self.splitField(('RWRKey',  c_u64, 32), bits))
            bits += 32
        a_sz = attr.field.ASz
        if a_sz > 0: # max 64 bits
            fields.extend(self.splitField(('ADDR',    c_u64, a_sz), bits))
            bits += a_sz
        w_sz = attr.field.WSz
        if w_sz > 0: # max 64 bits
            fields.extend(self.splitField(('WinSz',   c_u64, w_sz), bits))
            bits += w_sz
        fields.extend(self.padFields(bits, pte_sz))
        return fields

    def fileToStructInit(self):
        super().fileToStructInit()
        # use parent to dynamically build PTE based on PTESz, PTEATTRl, etc.
        pte_sz = self.parent.PTESz  # in bits, guaranteed to be 32-bit multiple
        pte_bytes = pte_sz // 8
        cap1 = PGZMMUCAP1(self.parent.PGZMMUCAP1, self.parent)
        attr = PTEATTRl(self.parent.PTEATTRl, self.parent)
        if attr.zmmuType == 0:
            fields = self.reqPteFields(pte_sz, cap1, attr)
            pfx = 'Req'
        else:
            fields = self.rspPteFields(pte_sz, cap1, attr)
            pfx = 'Rsp'
        PTE = type('{}PTE'.format(pfx), (ControlStructure,),
                   {'_fields_': fields,
                    'verbosity': self.verbosity,
                    'Size': pte_bytes})
        items = self.Size // sizeof(PTE)
        self.array = (PTE * items).from_buffer(self.data)
        self.element = PTE

class Packet(LittleEndianStructure):
    _ocl = OpClasses()

    def __init__(self):
        super().__init__()
        bitOffset = 0
        for field in self._fields_:
            width = field[2]
            byteOffset, highBit, lowBit, hexWidth = self.bitField(width, bitOffset)
            field.byteOffset = byteOffset

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

class ExplicitHdr(Packet):
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

    @property
    def LEN(self):
        return self.LENh << 3 | self.LENl

    @property
    def OpCode(self):
        return self.OpCodeh << 2 | self.OpCodel

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
    def uniqueness(self):
        if self.isRequest:
            return (self.SGCID << 40) | (self.DGCID << 12) | self.Tag
        else: # isResponse - swap SGCID/DGCID so it matches request
            return (self.DGCID << 40) | (self.SGCID << 12) | self.Tag

    @property
    def opcName(self):
        #return self._ocl.opClass(self.OCL).name(self.OpCode)
        try:
            name = self._ocl.opClass(self.OCL).name(self.OpCode)
        except KeyError:
            name = 'Unknown'
        return name

    def __str__(self):
        r = ('{}' if self.csv else '{:>22s}').format(type(self).__name__)
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
        r += (',{},{},{},{},{},{},{},{},{}' if self.csv else
              ', Tag: {:03x}, VC: {}, PCRC: {:02x}, AKey: {:02x}, Deadline: {:4d}, ECN: {}, GC: {}, NH: {}, PM: {}').format(
            self.Tag, self.VC, self.PCRC, self.AKey, self.Deadline,
            self.ECN, self.GC, self.NH, self.PM)
        return r

class ExplicitReqHdr(ExplicitHdr):
    rq_fields = [('LP',                         c_u32,  1),
                 ('TA',                         c_u32,  1),
                 ('RK',                         c_u32,  1)]
    hd_fields = ExplicitHdr.hd_fields + rq_fields

    def __str__(self):
        r = super().__str__()
        r += (',{},{},{}' if self.csv else ', LP: {}, TA: {}, RK: {}').format(self.LP, self.TA, self.RK)
        return r

class ExplicitPkt(ExplicitHdr):
    _fields_ = ExplicitHdr.hd_fields

class ExplicitReqPkt(ExplicitReqHdr):
    _fields_ = ExplicitHdr.hd_fields + ExplicitReqHdr.rq_fields

class Core64ReadPkt(ExplicitReqHdr):
    os1_fields = [('RDSize',                     c_u32,  9)]
    os2_fields = [('Addrh',                      c_u32, 32), # Byte 12
                  ('Addrl',                      c_u32, 32)] # Byte 16
    os3_fields = [('R0',                         c_u32,  5), # Byte 20
                  ('PD',                         c_u32,  1),
                  ('FPS',                        c_u32,  2),
                  ('ECRC',                       c_u32, 24)]

    def dataToPktInit(exp_pkt, data, verbosity):
        fields = ExplicitReqHdr.hd_fields + Core64ReadPkt.os1_fields
        if exp_pkt.GC:
            fields.extend(ExplicitHdr.ms_fields)
        if exp_pkt.RK:
            fields.extend(ExplicitHdr.rk_fields)
        fields.extend(Core64ReadPkt.os2_fields)
        if exp_pkt.NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(Core64ReadPkt.os3_fields)
        pkt_type = type('Core64Read', (Core64ReadPkt,),
                        {'_fields_': fields,
                         'data': exp_pkt.data,
                         'verbosity': exp_pkt.verbosity})
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def Addr(self):
        return self.Addrh << 32 | self.Addrl

    def __str__(self):
        r = super().__str__()
        r += (',,,{},,{}' if self.csv else ', RDSize: {:3d}, Addr: {:016x}').format(self.RDSize, self.Addr)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:02x}'.format(self.R0)
        r += (',,,,,,,,{},{},,,,,{}' if self.csv else ', PD: {}, FPS: {}, ECRC: {:06x}').format(self.PD, self.FPS, self.ECRC)
        return r

class Core64ReadResponsePkt(ExplicitHdr):
    os1_fields = [('LP',                         c_u32,  1),
                  ('R0',                         c_u32,  3),
                  ('PadCNT',                     c_u32,  2),
                  ('MS',                         c_u32,  2),
                  ('RRSPReason',                 c_u32,  4)]
    os3_fields = [('R1',                         c_u32,  8),
                  ('ECRC',                       c_u32, 24)]

    def dataToPktInit(exp_pkt, data, verbosity):
        fields = ExplicitHdr.hd_fields + Core64ReadResponsePkt.os1_fields
        if exp_pkt.GC:
            fields.extend(ExplicitHdr.ms_fields)
        # Revisit: LP (LPD) field
        # Revisit: MS (Meta) field
        pay_len = exp_pkt.LEN - 4  # Revisit: constant 4
        fields.append(('Payload', c_u32 * pay_len))
        if exp_pkt.NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(Core64ReadResponsePkt.os3_fields)
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type = type(className, (Core64ReadResponsePkt,),
                        {'_fields_': fields,
                         'data': exp_pkt.data,
                         'verbosity': exp_pkt.verbosity,
                         'pay_len': pay_len})
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    def __str__(self):
        r = super().__str__()
        r += (',{}' if self.csv else ', LP: {}').format(self.LP)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {}'.format(self.R0)
        r += (',,,,,,{},,,,,,,,{},,,{}' if self.csv else ', PadCNT: {:3d}, MS: {}, RRSPReason: {}').format(
            self.PadCNT, self.MS, self.RRSPReason)
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {:02x}'.format(self.R1)
        r += (',,,,{}' if self.csv else ', ECRC: {:06x}').format(self.ECRC)
        if self.verbosity:
            r += ('\n\tPayload[{}]:'.format(self.pay_len * 4 - self.PadCNT))
            for i in reversed(range(self.pay_len)):
                r += ' {:08x}'.format(self.Payload[i])
        return r

class Core64WritePkt(ExplicitReqHdr):
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

    def dataToPktInit(exp_pkt, data, verbosity):
        fields = ExplicitReqHdr.hd_fields + Core64WritePkt.os1_fields
        hdr_len = 6 # Revisit: constant 6
        if exp_pkt.NH:
            hdr_len += 4
        if exp_pkt.GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if exp_pkt.RK:
            fields.extend(ExplicitHdr.rk_fields)
            hdr_len += 1
        fields.extend(Core64WritePkt.os2_fields)
        # Revisit: MS (Meta) field
        pay_len = exp_pkt.LEN - hdr_len
        fields.append(('Payload', c_u32 * pay_len))
        if exp_pkt.NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(Core64WritePkt.os3_fields)
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type = type(className, (Core64WritePkt,),
                        {'_fields_': fields,
                         'data': exp_pkt.data,
                         'verbosity': exp_pkt.verbosity,
                         'pay_len': pay_len})
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def Addr(self):
        return self.Addrh << 32 | self.Addrl

    def __str__(self):
        r = super().__str__()
        r += (',,,,{},{}' if self.csv else ', PadCNT: {:3d}, Addr: {:016x}').format(self.PadCNT, self.Addr)
        r += (',,{},{},{},{},{},{}' if self.csv else
              ', TC: {}, NS: {}, UN: {}, PU: {}, RC: {}, MS: {}').format(
            self.TC, self.NS, self.UN, self.PU, self.RC, self.MS)
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {:02x}'.format(self.R0)
        r += (',{},{},,,,,{}' if self.csv else ', PD: {}, FPS: {}, ECRC: {:06x}').format(self.PD, self.FPS, self.ECRC)
        if self.verbosity:
            r += ('\n\tPayload[{}]:'.format(self.pay_len * 4 - self.PadCNT))
            for i in reversed(range(self.pay_len)):
                r += ' {:08x}'.format(self.Payload[i])
        return r

class Core64StandaloneAckPkt(ExplicitHdr):
    os1_fields = [('RNR_QD',                     c_u32,  3),
                  ('RSl',                        c_u32,  3),
                  ('Reason',                     c_u32,  6)]
    os3_fields = [('RSh',                        c_u32,  8), # Byte 12
                  ('ECRC',                       c_u32, 24)]

    def dataToPktInit(exp_pkt, data, verbosity):
        fields = ExplicitHdr.hd_fields + Core64StandaloneAckPkt.os1_fields
        if exp_pkt.GC:
            fields.extend(ExplicitHdr.ms_fields)
        if exp_pkt.NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(Core64StandaloneAckPkt.os3_fields)
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type = type(className, (Core64StandaloneAckPkt,),
                        {'_fields_': fields,
                         'data': exp_pkt.data,
                         'verbosity': exp_pkt.verbosity})
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def RS(self):
        return self.RSh << 3 | self.RSl

    def __str__(self):
        r = super().__str__()
        r += (',,,,,,,,,,,,,,,,,,,{},{},{}' if self.csv else ', RNR_QD: {}, RS: {}, Reason: {}').format(
            self.RNR_QD, self.RS, self.Reason)
        r += (',{}' if self.csv else ', ECRC: {:06x}').format(self.ECRC)
        return r

class ControlReadPkt(ExplicitHdr):
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

    def dataToPktInit(exp_pkt, data, verbosity):
        fields = ExplicitHdr.hd_fields + ControlReadPkt.os1_fields
        if exp_pkt.GC:
            fields.extend(ExplicitHdr.ms_fields)
        if exp_pkt.RK:
            fields.extend(ExplicitHdr.rk_fields)
        fields.extend(ControlReadPkt.os2_fields)
        if exp_pkt.NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(ControlReadPkt.os3_fields)
        pkt_type = type('ControlRead', (ControlReadPkt,),
                        {'_fields_': fields,
                         'data': exp_pkt.data,
                         'verbosity': exp_pkt.verbosity})
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def Addr(self):
        return self.Addrh << 32 | self.Addrl

    @property
    def MGRUUID(self):
        return self.uuid(self._uuid_fields[0])

    def __str__(self):
        r = super().__str__()
        if self.verbosity > 1 and not self.csv:
            r += ', R0: {}'.format(self.R0)
        r += (',,,{},{}' if self.csv else ', RK: {}, DR: {}').format(self.RK, self.DR)
        if self.DR:
            r += (',{}' if self.csv else ', DRIface: {}').format(self.DRIface)
        elif self.csv:
            r += ','
        r += (',{},,{},{}' if self.csv else ', RDSize: {:3d}, Addr: {:013x}, MGRUUID: {}').format(
            self.RDSize, self.Addr, self.MGRUUID)
        if self.verbosity > 1 and not self.csv:
            r += ', R1: {:02x}'.format(self.R1)
        r += (',,,,,,,,{},,,,,{}' if self.csv else ', FPS: {}, ECRC: {:06x}').format(self.FPS, self.ECRC)
        return r

class ControlReadResponsePkt(Core64ReadResponsePkt):
    pass

class ControlWritePkt(ExplicitHdr):
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

    def dataToPktInit(exp_pkt, data, verbosity):
        fields = ExplicitHdr.hd_fields + ControlWritePkt.os1_fields
        hdr_len = 10 # Revisit: constant 10
        if exp_pkt.NH:
            hdr_len += 4
        if exp_pkt.GC:
            fields.extend(ExplicitHdr.ms_fields)
            hdr_len += 1
        if exp_pkt.RK:
            fields.extend(ExplicitHdr.rk_fields)
            hdr_len += 1
        fields.extend(ControlWritePkt.os2_fields)
        pay_len = exp_pkt.LEN - hdr_len
        fields.append(('Payload', c_u32 * pay_len))
        fields.extend(ControlWritePkt.os2b_fields)
        if exp_pkt.NH:
            fields.extend(ExplicitHdr.nh_fields)
        fields.extend(ControlWritePkt.os3_fields)
        className = exp_pkt.oclName + exp_pkt.opcName
        pkt_type = type(className, (ControlWritePkt,),
                        {'_fields_': fields,
                         'data': exp_pkt.data,
                         'verbosity': exp_pkt.verbosity,
                         'pay_len': pay_len})
        pkt = pkt_type.from_buffer(exp_pkt.data)
        return pkt

    @property
    def Addr(self):
        return self.Addrh << 32 | self.Addrl

    @property
    def MGRUUID(self):
        return self.uuid(self._uuid_fields[0])

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
        r += (',,{},{},{}' if self.csv else ', PadCNT: {:3d}, Addr: {:013x}, MGRUUID: {}').format(
            self.PadCNT, self.Addr, self.MGRUUID)
        if self.verbosity > 1 and not self.csv:
            r += ', R2: {:02x}'.format(self.R2)
        r += (',,,,,,,,{},,,,,{}' if self.csv else ', FPS: {}, ECRC: {:06x}').format(self.FPS, self.ECRC)
        if self.verbosity:
            r += ('\n\tPayload[{}]:'.format(self.pay_len * 4 - self.PadCNT))
            for i in reversed(range(self.pay_len)):
                r += ' {:08x}'.format(self.Payload[i])
        return r

class ControlStandaloneAckPkt(Core64StandaloneAckPkt):
    pass
