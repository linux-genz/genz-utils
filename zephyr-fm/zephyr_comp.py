#!/usr/bin/env python3

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

import ctypes
from genz.genz_common import GCID, CState, IState, RKey, PHYOpStatus, ErrSeverity, CReset, HostMgrUUID, genzUUID
import os
import re
import time
from pdb import set_trace
from uuid import UUID, uuid4
from math import ceil, log2
from pathlib import Path
import zephyr_conf
from zephyr_conf import log, INVALID_GCID
from zephyr_iface import Interface

ALL_RKD = 0 # all requesters are granted this RKD
FM_RKD = 1  # only the FM is granted this RKD
FM_RKEY = RKey(rkd=FM_RKD, os=0) # for FM-only control structs
NO_ACCESS_RKEY = RKey(rkd=FM_RKD, os=1) # no-access: rsp RO+RW; read-only: rsp RW
DEFAULT_RKEY = RKey(rkd=ALL_RKD, os=0)

def ceil_log2(x):
    try:
        return ceil(log2(x))
    except ValueError: # x == 0
        return 0

comp_num_re = re.compile(r'.*/([^0-9]+)([0-9]+)')

def component_num(comp_path):
    match = comp_num_re.match(str(comp_path))
    return int(match.group(2))

def get_gcid(comp_path):
    gcid = comp_path / 'gcid'
    with gcid.open(mode='r') as f:
        return GCID(str=f.read().rstrip())

def get_cuuid(comp_path):
    cuuid = comp_path / 'c_uuid'
    with cuuid.open(mode='r') as f:
        return UUID(f.read().rstrip())

def get_fru_uuid(comp_path):
    fru_uuid = comp_path / 'fru_uuid'
    with fru_uuid.open(mode='r') as f:
        return UUID(f.read().rstrip())

def get_mgr_uuid(comp_path):
    mgr_uuid = comp_path / 'mgr_uuid'
    with mgr_uuid.open(mode='r') as f:
        return UUID(f.read().rstrip())

def get_serial(comp_path):
    serial = comp_path / 'serial'
    with serial.open(mode='r') as f:
        return f.read().rstrip()

def get_cclass(comp_path):
    cclass = comp_path / 'cclass'
    with cclass.open(mode='r') as f:
        return f.read().rstrip()


class Component():
    timer_unit_list = [ 1e-9, 10*1e-9, 100*1e-9, 1e-6, 10*1e-6, 100*1e-6,
                        1e-3, 10*1e-3, 100*1e-3, 1.0 ]
    ctl_timer_unit_list = [ 1e-6, 10*1e-6, 100*1e-6, 1e-3 ]

    def __new__(cls, cclass, *args, **kwargs):
        subclass_map = {cclass: subclass for subclass in cls.__subclasses__()
                        for cclass in subclass.cclasses}
        subclass = subclass_map.get(cclass, cls)
        instance = super(Component, subclass).__new__(subclass)
        return instance

    def __init__(self, cclass, fab, map, path, mgr_uuid, verbosity=0, gcid=None,
                 local_br=False, dr=None, tmp_gcid=None, br_gcid=None,
                 netlink=None, uuid=None, nonce=None):
        self.cclass = cclass
        self.fab = fab
        self.map = map
        self.path = path
        self.mgr_uuid = mgr_uuid
        self.verbosity = verbosity
        self.local_br = local_br
        self.tmp_gcid = tmp_gcid
        self.gcid = (gcid if gcid is not None else
                     tmp_gcid if tmp_gcid is not None else INVALID_GCID)
        self.br_gcid = br_gcid
        self.dr = dr
        self.nl = netlink
        self.interfaces = []
        self.uuid = uuid4() if uuid is None else uuid
        self.nonce = fab.generate_nonce() if nonce is None else nonce
        self.cuuid = None
        self.serial = None
        self.cuuid_serial = None
        self._num_vcs = None
        self._req_vcat_sz = None
        self._rsp_vcat_sz = None
        self._ssdt_sz = None
        self.comp_dest = None
        self.ssdt = None
        self.ssdt_dir = None # needed by rt.invert() early on
        self.rit = None
        self.route_info = None
        self.req_vcat = None
        self.rsp_vcat = None
        self.rsp_page_grid_ps = 0
        fab.components[self.uuid] = self
        fab.add_node(self, instance_uuid=self.uuid, cclass=self.cclass,
                     mgr_uuid=self.mgr_uuid)

    def __hash__(self):
        return hash(self.uuid)

    def __eq__(self, other):
        return self.uuid == other.uuid

    def to_json(self):
        return self.cuuid_serial

    def set_dr(self, dr):
        self.dr = dr
        self.path = dr.path

    # for LLMUTO, NLMUTO, NIRT, FPST, REQNIRTO, REQABNIRTO
    def timeout_val(self, time):
        try:
            return int(time / Component.timer_unit_list[self.timer_unit])
        except IndexError:
            log.warning('invalid timer_unit value {}'.format(self.timer_unit))
            return 0

    # for ControlTO, ControlDRTO
    def ctl_timeout_val(self, time):
        # all ctl_timer_unit values are valid
        return int(time / Component.ctl_timer_unit_list[self.ctl_timer_unit])

    def check_all_ones(self, sz, off, data):
        ones = (1 << (sz * 8)) - 1
        val = int.from_bytes(data[off:off+sz], 'little')
        if val == ones:
            raise ValueError # Revisit: raise better exception?

    # Revisit: the sz & off params are workarounds for ctypes bugs
    def control_read(self, struct, field, sz=None, off=0, check=False):
        off += field.offset
        if sz is None:
            sz = ctypes.sizeof(field)  # Revisit: this doesn't work
        struct.data[off:off+sz] = os.pread(struct.fd, sz, off)
        if check: # check that we didn't read bad all-ones data
            self.check_all_ones(sz, off, struct.data)

    # Revisit: the sz & off params are workarounds for ctypes bugs
    def control_write(self, struct, field, sz=None, off=0, check=False):
        off += field.offset
        if sz is None:
            sz = ctypes.sizeof(field)  # Revisit: this doesn't work
        if check: # check that we're not writing bad all-ones data
            self.check_all_ones(sz, off, struct.data)
        os.pwrite(struct.fd, struct.data[off:off+sz], off)

    def add_fab_comp(self, setup=False):
        log.debug('add_fab_comp for {}'.format(self))
        cmd_name = self.nl.cfg.get('ADD_FAB_COMP')
        data = {'gcid':     self.gcid.val,
                'br_gcid':  self.br_gcid.val,
                'tmp_gcid': self.tmp_gcid.val if self.tmp_gcid else INVALID_GCID.val,
                'dr_gcid':  self.dr.gcid.val if self.dr else INVALID_GCID.val,
                'dr_iface': self.dr.egress_iface.num if self.dr else 0,
                'mgr_uuid': self.mgr_uuid,
        }
        msg = self.nl.build_msg(cmd=cmd_name, data=data)
        ret = self.nl.sendmsg(msg)
        self.fab.update_path('/sys/devices/genz1')  # Revisit: MultiBridge hardcoded path
        if setup:
            self.setup_paths('control')
        else:
            self.update_path()
        return ret

    def remove_fab_comp(self):
        log.debug('remove_fab_comp for {}'.format(self))
        cmd_name = self.nl.cfg.get('REMOVE_FAB_COMP')
        data = {'gcid':     self.gcid.val,
                'br_gcid':  self.br_gcid.val,
                'tmp_gcid': self.tmp_gcid.val if self.tmp_gcid else INVALID_GCID.val,
                'dr_gcid':  self.dr.gcid.val if self.dr else INVALID_GCID.val,
                'dr_iface': self.dr.egress_iface.num if self.dr else 0,
                'mgr_uuid': self.mgr_uuid,
        }
        msg = self.nl.build_msg(cmd=cmd_name, data=data)
        ret = self.nl.sendmsg(msg)
        self.remove_paths()
        return ret

    def add_fab_dr_comp(self):
        log.debug('add_fab_dr_comp for {}'.format(self))
        cmd_name = self.nl.cfg.get('ADD_FAB_DR_COMP')
        data = {'gcid':     self.gcid.val,
                'br_gcid':  self.br_gcid.val,
                'tmp_gcid': INVALID_GCID.val,
                'dr_gcid':  self.dr.gcid.val,
                'dr_iface': self.dr.egress_iface.num,
                'mgr_uuid': self.mgr_uuid,
        }
        msg = self.nl.build_msg(cmd=cmd_name, data=data)
        ret = self.nl.sendmsg(msg)
        return ret

    def remove_fab_dr_comp(self):
        log.debug('remove_fab_dr_comp for {}'.format(self))
        cmd_name = self.nl.cfg.get('REMOVE_FAB_DR_COMP')
        data = {'gcid':     self.gcid.val,
                'br_gcid':  self.br_gcid.val,
                'tmp_gcid': INVALID_GCID.val,
                'dr_gcid':  self.dr.gcid.val,
                'dr_iface': self.dr.egress_iface.num,
                'mgr_uuid': self.mgr_uuid,
        }
        msg = self.nl.build_msg(cmd=cmd_name, data=data)
        ret = self.nl.sendmsg(msg)
        self.remove_paths()
        return ret

    # Returns the current component GCID
    def get_gcid(self, prefix='control'):
        gcid = None
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                         verbosity=self.verbosity)
            if core.CV:
                gcid = GCID(val=core.CID0)  # Revisit: Subnets
        return gcid

    def find_rsp_page_grid_path(self, prefix):
        genz = zephyr_conf.genz
        for pg_dir in (self.path / prefix / 'component_page_grid').glob(
                'component_page_grid*@*'):
            pg_file = pg_dir / 'component_page_grid'
            with pg_file.open(mode='rb+') as f:
                data = bytearray(f.read())
                pg = self.map.fileToStruct('component_page_grid', data,
                                           fd=f.fileno(),
                                           verbosity=self.verbosity)
                cap1 = genz.PGZMMUCAP1(pg.PGZMMUCAP1, pg)
                if cap1.field.ZMMUType == genz.ZMMUType.RspZMMU:
                    return pg_dir
            # end with
        # end for
        return None

    def setup_paths(self, prefix):
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        self.opcode_set_dir = list((self.path / prefix).glob('opcode_set@*'))[0]
        try:
            self.opcode_set_table_dir = list(self.opcode_set_dir.glob(
                'opcode_set_table/opcode_set_table0@*'))[0]
        except IndexError:
            self.opcode_set_table_dir = None
        try:
            self.ssdt_dir = list(self.comp_dest_dir.glob('ssdt@*'))[0]
        except IndexError:
            self.ssdt_dir = None
        try:
            self.req_vcat_dir = list(self.comp_dest_dir.glob('req_vcat@*'))[0]
        except IndexError:
            self.req_vcat_dir = None
        try:
            self.rsp_vcat_dir = list(self.comp_dest_dir.glob('rsp_vcat@*'))[0]
        except IndexError:
            self.rsp_vcat_dir = None
        try:
            self.rit_dir = list(self.comp_dest_dir.glob('rit@*'))[0]
        except IndexError:
            self.rit_dir = None
        try:
            self.switch_dir = list((self.path / prefix).glob(
                'component_switch@*'))[0]
        except IndexError:
            self.switch_dir = None
        try:
            self.ces_dir = list((self.path / prefix).glob(
                'component_error_and_signal_event@*'))[0]
        except IndexError:
            self.ces_dir = None
        self.rsp_pg_dir = self.find_rsp_page_grid_path(prefix)
        if self.rsp_pg_dir is not None:
            self.rsp_pg_table_dir = list(self.rsp_pg_dir.glob(
                'pg_table@*'))[0]
            self.rsp_pte_table_dir = list(self.rsp_pg_dir.glob(
                'pte_table@*'))[0]

    def remove_paths(self):
        self.comp_dest_dir = None
        self.opcode_set_dir = None
        self.opcode_set_table_dir = None
        self.ssdt_dir = None
        self.req_vcat_dir = None
        self.rsp_vcat_dir = None
        self.rit_dir = None
        self.switch_dir = None
        self.ces_dir = None
        self.rsp_pg_dir = None
        self.rsp_pg_table_dir = None
        self.rsp_pte_table_dir = None

    def check_usable(self, prefix='control'):
        self.update_cstate(prefix=prefix)
        return (self.cstate == CState.CUp or self.cstate == CState.CLP or
                self.cstate == CState.CDLP)

    # Returns True if component is usable - is C-Up/C-LP/C-DLP, not C-Down
    def comp_init(self, pfm, prefix='control', ingress_iface=None, route=None):
        args = zephyr_conf.args
        genz = zephyr_conf.genz
        log.debug('comp_init for {}'.format(self))
        if args.keyboard > 1:
            set_trace()
        self.usable = False  # Revisit: move to __init__()
        if self.local_br:
            self.br_gcid = self.gcid
        self.setup_paths(prefix)
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                         verbosity=self.verbosity)
            log.debug('{}: {}'.format(self.gcid, core))
            self.core = core
            # verify good data, at structure start
            if core.all_ones_type_vers_size():
                log.warning(f'{self}: core structure returned all-ones data')
                self.usable = False
                return False
            # verify good data near structure end (check ZUUID)
            if core.ZUUID != genzUUID:
                log.warning(f'{self}: invalid core structure ZUUID {core.ZUUID}')
                self.usable = False
                return False
            # save cstate and use below to control writes (e.g., CID0)
            cstatus = genz.CStatus(core.CStatus, core)
            self.cstate = CState(cstatus.field.CState)
            # save some other key values
            cap1 = genz.CAP1(core.CAP1, core)
            self.timer_unit = cap1.field.TimerUnit
            self.ctl_timer_unit = cap1.field.CtlTimerUnit
            self.cclass = core.BaseCClass
            self.max_data = core.MaxData
            self.max_iface = core.MaxInterface
            self.cuuid = core.CUUID
            # create and read (but do not HW init) the switch struct
            self.switch_read(prefix=prefix)
            # create and read (but do not HW init) all interfaces
            for ifnum in range(0, core.MaxInterface):
                if ifnum >= len(self.interfaces):
                    if ((ingress_iface is not None) and
                        (ingress_iface.num == ifnum)):
                        iface = ingress_iface
                    else:
                        iface = Interface(self, ifnum)
                    self.interfaces.append(iface)
                # end if ifnum
                try:
                    self.interfaces[ifnum].iface_read(prefix=prefix)
                except ValueError:
                    log.warning(f'{self.interfaces[ifnum]}: iface_read returned all-ones data')
                except IndexError:
                    pass
            # end for
            if pfm and self.cstate is CState.CCFG:
                # set CV/CID0/SID0 - first Gen-Z control write if !local_br
                # Revisit: support subnets and multiple CIDs
                core.CID0 = self.gcid.cid
                core.CV = 1
                self.control_write(core, genz.CoreStructure.CV, sz=8)
            # Revisit: MGR-UUID capture does not work on previous mamba
            if 0:
                # For non-local-bridge components in C-CFG, MGR-UUID will have
                # been captured on CV/CID0/SID0 write, so skip this
                # set MGR-UUID
                core.MGRUUIDl = int.from_bytes(self.mgr_uuid.bytes[0:8],
                                           byteorder='little')
                core.MGRUUIDh = int.from_bytes(self.mgr_uuid.bytes[8:16],
                                           byteorder='little')
                self.control_write(core, genz.CoreStructure.MGRUUIDl, sz=16)
            # setup SSDT and RIT entries for route back to FM
            if pfm and ingress_iface is not None:
                self.ssdt_size(prefix=prefix)
                # use route elem to correctly set SSDT HC & MHC
                elem = route[0][0]
                elem.set_ssdt(pfm, update_rt_num=True)
                self.rit_write(ingress_iface, 1 << ingress_iface.num)
            if pfm:
                # initialize RSP-VCAT
                # Revisit: multiple Action columns
                for vc in range(0, self.rsp_vcat_size(prefix=prefix)[0]):
                    # Revisit: vc policies
                    self.rsp_vcat_write(vc, 0x1)
                # set LLReqDeadline, NLLReqDeadline
                # Revisit: only for requesters
                # set DeadlineTick
                # Revisit: compute values depending on topology, as described
                # in Core spec section 15.2, Deadline Semantics
                # Revisit: if no Component Peer Attr struct, LL/NLL must be same
                core.LLReqDeadline = 586
                core.NLLReqDeadline = 976
                if self.cstate is not CState.CUp:
                    # DeadlineTick can only be modified in non-C-Up
                    # Revisit: current HW only directly supports power-of-2 values
                    core.DeadlineTick = 1024  # 1.024us
                self.control_write(core, genz.CoreStructure.LLReqDeadline, sz=4)
                # set DRReqDeadline
                # Revisit: compute values depending on topology
                core.DRReqDeadline = 1023
                self.control_write(core, genz.CoreStructure.SID0, sz=4)
                # set LLRspDeadline, NLLRspDeadline, RspDeadline
                # Revisit: compute values depending on topology, as described
                # in Core spec section 15.2, Deadline Semantics
                # Revisit: only for responders
                # Revisit: if no Component Peer Attr struct, LL/NLL must be same
                core.LLRspDeadline = 587
                core.NLLRspDeadline = 977
                core.RspDeadline = 782 # responder packet execution time
                self.control_write(core, genz.CoreStructure.LLRspDeadline, sz=4)
                # almost done with DR - read back the first thing we wrote
                # (CV/CID0), and if it's still set correctly assume that CCTO
                # did not expire; also check that it's not all-ones
                try:
                    self.control_read(core, genz.CoreStructure.CV,
                                      sz=8, check=True)
                except ValueError:
                    log.warning(f'{self}: CV/CID0 returned all-ones data')
                    self.usable = False
                    return False
                # Revisit: retry if CCTO expired?
                if core.CV == 0 and core.CID0 == 0:
                    log.warning(f'{self}: CV/CID0 is 0 - CCTO expired')
                    self.usable = False
                    return False
                # we have set up just enough for "normal" responses to work -
                # tell the kernel about the new/changed component and stop DR
                try:
                    if self.cstate is CState.CCFG:
                        self.add_fab_comp()
                        self.tmp_gcid = None
                        self.dr = None
                        prefix = 'control'
                except Exception as e:
                    log.error('add_fab_comp failed with exception {}'.format(e))
                    self.usable = False
                    return self.usable
            # end if pfm
        # end with
        cuuid = get_cuuid(self.path)
        serial = get_serial(self.path)
        self.cuuid = cuuid
        self.serial = int(serial, base=0)
        self.cuuid_serial = str(cuuid) + ':' + serial
        self.fru_uuid = get_fru_uuid(self.path)
        self.fab.add_comp(self)
        if not pfm:
            return self.check_usable()
        # re-open core file at (potential) new location set by add_fab_comp()
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            core.set_fd(f)
            if self.cstate is CState.CCFG:
                log.debug('{}: done with DR - using direct access'.format(self))
            if self.cstate is not CState.CCFG or self.local_br:
                # For non-local-bridge components in C-CFG, MGR-UUID will have
                # been captured on CV/CID0/SID0 write, so skip this
                # set MGR-UUID
                core.MGRUUIDl = int.from_bytes(self.mgr_uuid.bytes[0:8],
                                           byteorder='little')
                core.MGRUUIDh = int.from_bytes(self.mgr_uuid.bytes[8:16],
                                           byteorder='little')
                self.control_write(core, genz.CoreStructure.MGRUUIDl, sz=16)
            # read back MGRUUID, to confirm we own component by verifying
            # not all-ones
            try:
                self.control_read(core, genz.CoreStructure.MGRUUIDl,
                                  sz=16, check=True)
            except ValueError:
                log.warning(f'{self}: all-ones MGRUUID - component not owned')
                self.usable = False
                return False
            # set PFMSID/PFMCID (must be before PrimaryFabMgrRole = 1)
            # Revisit: subnets
            core.PFMCID = pfm.gcid.cid
            self.control_write(core, genz.CoreStructure.PMCID, sz=8)
            # set HostMgrMGRUUIDEnb, MGRUUIDEnb
            cap1ctl = genz.CAP1Control(core.CAP1Control, core)
            uuEnb = HostMgrUUID.Core if self.local_br else HostMgrUUID.Zero
            cap1ctl.HostMgrMGRUUIDEnb = uuEnb
            cap1ctl.MGRUUIDEnb = 1
            # set ManagerType, PrimaryFabMgrRole
            # clear PrimaryMgrRole, SecondaryFabMgrRole, PwrMgrEnb
            cap1ctl.field.ManagerType = 1
            cap1ctl.field.PrimaryMgrRole = 0
            cap1ctl.PrimaryFabMgrRole = 1 if self.local_br else 0
            cap1ctl.field.SecondaryFabMgrRole = 0
            cap1ctl.field.PwrMgrEnb = 0
            # Revisit: set OOBMgmtDisable
            # set sticky SWMgmtBits[3:0] to FabricManaged=0x1
            cap1ctl.field.SWMgmt0 = 1
            cap1ctl.field.SWMgmt1 = 0
            cap1ctl.field.SWMgmt2 = 0
            cap1ctl.field.SWMgmt3 = 0
            cap1ctl.field.SWMgmt4 = 0
            cap1ctl.field.SWMgmt5 = 0
            cap1ctl.field.SWMgmt6 = 0
            cap1ctl.field.SWMgmt7 = 0
            core.CAP1Control = cap1ctl.val
            self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
            # set PFMCIDValid; clear other CID/SID valid bits
            cap2ctl = genz.CAP2Control(core.CAP2Control, core)
            cap2ctl.field.PMCIDValid = 0
            cap2ctl.field.PFMCIDValid = 1
            cap2ctl.field.SFMCIDValid = 0
            cap2ctl.field.PFMSIDValid = 0
            cap2ctl.field.SFMSIDValid = 0
            core.CAP2Control = cap2ctl.val
            self.control_write(core, genz.CoreStructure.CAP2Control, sz=8)
            # set CompNonce
            core.CompNonce = self.nonce
            self.control_write(core, genz.CoreStructure.CompNonce, sz=8)
            # check that at least 1 interface can be brought Up
            for ifnum in range(0, core.MaxInterface):
                try:
                    iup = self.interfaces[ifnum].iface_init(prefix=prefix)
                    if iup:
                        self.usable = True
                except IndexError:
                    del self.interfaces[-1] # Revisit: why?
            # set LLMUTO  # Revisit: how to compute reasonable values?
            # Revisit: this should be <=20us, but orthus is timing control ops
            # with the wrong timer
            wrong_timer = False
            if wrong_timer:
                #core.LLMUTO = self.timeout_val(3e-3)  # 3ms [2ms:bad, 3ms:good]
                core.LLMUTO = self.timeout_val(65.53e-3)  # 65.53ms
            else:
                core.LLMUTO = self.timeout_val(20e-6)  # 20us
            self.control_write(core, genz.CoreStructure.LLMUTO, sz=2)
            # set UERT
            # Revisit: set NIRT, ATSTO, UNREQ
            core.UERT = 200                            # 200ms # Revisit
            self.control_write(core, genz.CoreStructure.UERT, sz=8)
            # Revisit: set UNRSP, FPST, PCO FPST, NLMUTO
            # Revisit: set REQNIRTO, REQABNIRTO
            # set ControlTO, ControlDRTO
            # Revisit: how to compute reasonable values?
            core.ControlTO = self.ctl_timeout_val(args.control_to)
            core.ControlDRTO = self.ctl_timeout_val(args.control_drto)
            self.control_write(core, genz.CoreStructure.ControlTO, sz=4)
            # set MaxRequests
            # Revisit: Why would FM choose < MaxREQSuppReqs? Only for P2P?
            # Revisit: only for requesters
            core.MaxRequests = core.MaxREQSuppReqs
            self.control_write(core, genz.CoreStructure.MaxRequests, sz=8)
            # Revisit: set MaxPwrCtl (to NPWR?)
            # Revisit: try/except ValueError
            rows, cols = self.ssdt_size(prefix=prefix)
            # initialize SSDT route info
            from zephyr_route import RouteInfo
            self.route_info = [[RouteInfo() for j in range(cols)]
                               for i in range(rows)]
            # invalidate SSDT (except PFM CID written earlier)
            # Revisit: should we be doing this when reclaiming a C-Up comp?
            for cid in range(0, rows):
                if cid != pfm.gcid.cid or ingress_iface is None:
                    for rt in range(0, cols):
                        self.ssdt_write(cid, 0x780|cid, rt=rt, valid=0) # Revisit: ei debug
            # initialize REQ-VCAT
            # Revisit: multiple Action columns
            for vc in range(0, self.req_vcat_size(prefix=prefix)[0]):
                # Revisit: vc policies
                self.req_vcat_write(vc, 0x2)
            # initialize RIT for each usable interface
            for iface in self.interfaces:
                if iface.usable:
                    self.rit_write(iface, 1 << iface.num)
            # initialize OpCode Set structure
            self.opcode_set_init()
            # initialize Responder Page Grid structure
            # Revisit: should we be doing this when reclaiming a C-Up comp?
            self.rsp_page_grid_init(core, valid=1)
            # if component is usable, set ComponentEnb - transition to C-Up
            if self.usable:
                # Revisit: before setting ComponentEnb, once again check that
                # CCTO never expired
                cctl = genz.CControl(core.CControl, core)
                cctl.field.ComponentEnb = 1
                core.CControl = cctl.val
                self.control_write(core, genz.CoreStructure.CControl, sz=8)
                log.info('{} transitioning to C-Up'.format(self.gcid))
                # update our peer's peer-info (about us, now that we're C-Up)
                if (ingress_iface is not None and
                    ingress_iface.peer_iface is not None):
                    ingress_iface.peer_iface.update_peer_info()
                if args.sleep > 0.0:
                    log.debug('sleeping {} seconds for slow switch C-Up transition'.format(args.sleep))
                    time.sleep(args.sleep)
            else:
                log.info('{} has no usable interfaces'.format(self.path))
        # end with
        if self.has_switch:
            self.switch_init(core)
        self.comp_err_signal_init(core)
        self.fab.update_comp(self)
        return self.usable

    def opcode_set_init(self):
        # Revisit: support multiple OpCode Set tables
        # Revisit: handle Vendor-Defined OpClasses
        genz = zephyr_conf.genz
        opcode_set_file = self.opcode_set_dir / 'opcode_set'
        with opcode_set_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            opcode_set = self.map.fileToStruct('opcode_set', data, fd=f.fileno(),
                                               verbosity=self.verbosity)
            log.debug('{}: {}'.format(self.gcid, opcode_set))
            cap1 = genz.OpCodeSetCAP1(opcode_set.CAP1, opcode_set)
            cap1ctl = genz.OpCodeSetCAP1Control(opcode_set.CAP1Control,
                                                opcode_set)
            # Revisit: set cap1ctl.EnbCacheLineSz
            if cap1.field.UniformOpClassSup:
                # set Uniform Explicit OpClasses
                cap1ctl.field.IfaceUniformOpClass = 0x1 # Revisit: enum
                opcode_set.CAP1Control = cap1ctl.val
                self.control_write(opcode_set,
                            genz.OpCodeSetStructure.CAP1Control, sz=4, off=4)
        # end with
        opcode_set_table_file = self.opcode_set_table_dir / 'opcode_set_table'
        with opcode_set_table_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            opcode_set_table = self.map.fileToStruct('opcode_set_table',
                                                     data, fd=f.fileno(),
                                                     path=opcode_set_table_file,
                                                     verbosity=self.verbosity)
            log.debug('{}: {}'.format(self.gcid, opcode_set_table))
            # Enable all Supported OpCodes for Core64/Control/DR OpClasses
            opcode_set_table.EnabledCore64OpCodeSet = (
                opcode_set_table.SupportedCore64OpCodeSet)
            opcode_set_table.EnabledControlOpCodeSet = (
                opcode_set_table.SupportedControlOpCodeSet)
            opcode_set_table.EnabledDROpCodeSet = (
                opcode_set_table.SupportedDROpCodeSet)
            # Revisit: add support for other OpClasses
            # Revisit: orthus tries to use >16-byte writes and fails
            #self.control_write(opcode_set_table, genz.OpCodeSetTable.SetID,
            #                   sz=opcode_set_table.Size, off=0)
            self.control_write(opcode_set_table,
                               genz.OpCodeSetTable.EnabledCore64OpCodeSet,
                               sz=8, off=0)
            self.control_write(opcode_set_table,
                               genz.OpCodeSetTable.EnabledControlOpCodeSet,
                               sz=8, off=0)
            self.control_write(opcode_set_table,
                               genz.OpCodeSetTable.EnabledDROpCodeSet,
                               sz=8, off=0)
        # end with

    def cerror_init(self, ces):
        genz = zephyr_conf.genz
        # Set CErrorSigTgt
        cerr_tgt = genz.CErrorSigTgt([ces.CErrorSigTgtl,
                                      ces.CErrorSigTgtm,
                                      ces.CErrorSigTgth], ces)
        sig_tgt = genz.SigTgt.TgtIntr1 if self.local_br else genz.SigTgt.TgtUEP
        cerr_tgt.field.CompContain = sig_tgt
        cerr_tgt.field.NonFatalCompErr = sig_tgt
        cerr_tgt.field.FatalCompErr = sig_tgt
        cerr_tgt.field.E2EUnicastUR = sig_tgt
        cerr_tgt.field.E2EUnicastMP = sig_tgt
        cerr_tgt.field.E2EUnicastEXENonFatal = sig_tgt
        cerr_tgt.field.E2EUnicastEXEFatal = sig_tgt
        cerr_tgt.field.E2EUnicastUP = sig_tgt
        cerr_tgt.field.AEInvAccPerm = sig_tgt
        cerr_tgt.field.E2EUnicastEXEAbort = sig_tgt
        cerr_tgt.field.MaxReqPktRetrans = sig_tgt # Revisit: Only Requesters
        cerr_tgt.field.InsufficientSpace = sig_tgt
        cerr_tgt.field.UnsupServiceAddr = sig_tgt
        cerr_tgt.field.InsufficientRspRes = sig_tgt
        ces.CErrorSigTgtl = cerr_tgt.val[0]
        ces.CErrorSigTgtm = cerr_tgt.val[1]
        ces.CErrorSigTgth = cerr_tgt.val[2]
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.CErrorSigTgtl, sz=24)
        # Set CErrorDetect - last, after other CError fields setup
        cerr_det = genz.CErrorDetect(ces.CErrorDetect, ces)
        cerr_det.field.CompContain = 1
        cerr_det.field.NonFatalCompErr = 1
        cerr_det.field.FatalCompErr = 1
        cerr_det.field.E2EUnicastUR = 1
        cerr_det.field.E2EUnicastMP = 1
        cerr_det.field.E2EUnicastEXENonFatal = 1
        cerr_det.field.E2EUnicastEXEFatal = 1
        cerr_det.field.E2EUnicastUP = 1
        cerr_det.field.AEInvAccPerm = 1
        cerr_det.field.E2EUnicastEXEAbort = 1
        cerr_det.field.MaxReqPktRetrans = 1 # Revisit: Only Requesters
        cerr_det.field.InsufficientSpace = 1
        cerr_det.field.UnsupServiceAddr = 1
        cerr_det.field.InsufficientRspRes = 1
        # Revisit: other errors
        ces.CErrorDetect = cerr_det.val
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.CErrorDetect, sz=8)

    def cevent_init(self, ces):
        genz = zephyr_conf.genz
        # Set CEventSigTgt
        cevt_tgt = genz.CEventSigTgt([ces.CEventSigTgtl,
                                      ces.CEventSigTgtm,
                                      ces.CEventSigTgth], ces)
        sig_tgt = genz.SigTgt.TgtIntr1 if self.local_br else genz.SigTgt.TgtUEP
        cevt_tgt.field.UnableToCommAuthDest = sig_tgt
        cevt_tgt.field.ExcessiveRNRNAK = sig_tgt
        cevt_tgt.field.CompThermShutdown = sig_tgt
        ces.CEventSigTgtl = cevt_tgt.val[0]
        ces.CEventSigTgtm = cevt_tgt.val[1]
        ces.CEventSigTgth = cevt_tgt.val[2]
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.CEventSigTgtl, sz=24)
        # Set CEventDetect - last, after other CEvent fields setup
        cevt_det = genz.CEventDetect(ces.CEventDetect, ces)
        cevt_det.field.UnableToCommAuthDest = 1
        cevt_det.field.ExcessiveRNRNAK = 1
        cevt_det.field.CompThermShutdown = 1
        # Revisit: other events
        ces.CEventDetect = cevt_det.val
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.CEventDetect, sz=8)

    def ievent_init(self, ces):
        genz = zephyr_conf.genz
        # Set IEventSigTgt
        ievt_tgt = genz.IEventSigTgt([ces.IEventSigTgtl,
                                      ces.IEventSigTgtm,
                                      ces.IEventSigTgth], ces)
        sig_tgt = genz.SigTgt.TgtIntr1 if self.local_br else genz.SigTgt.TgtUEP
        ievt_tgt.field.FullIfaceReset = sig_tgt
        ievt_tgt.field.WarmIfaceReset = sig_tgt
        ievt_tgt.field.NewPeerComp = sig_tgt
        ievt_tgt.field.ExceededTransientErrThresh = sig_tgt
        ievt_tgt.field.IfacePerfDegradation = sig_tgt
        ces.IEventSigTgtl = ievt_tgt.val[0]
        ces.IEventSigTgtm = ievt_tgt.val[1]
        ces.IEventSigTgth = ievt_tgt.val[2]
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.IEventSigTgtl, sz=24)
        # Set IEventDetect - last, after other IEvent fields setup
        ievt_det = genz.IEventDetect(ces.IEventDetect, ces)
        ievt_det.field.FullIfaceReset = 1
        ievt_det.field.WarmIfaceReset = 1
        ievt_det.field.NewPeerComp = 1
        ievt_det.field.ExceededTransientErrThresh = 1
        ievt_det.field.IfacePerfDegradation = 1
        ces.IEventDetect = ievt_det.val
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.IEventDetect, sz=8)

    def comp_err_signal_init(self, core):
        if self.ces_dir is None:
            return
        genz = zephyr_conf.genz
        ces_file = self.ces_dir / 'component_error_and_signal_event'
        with ces_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            ces = self.map.fileToStruct('component_error_and_signal_event',
                                        data, fd=f.fileno(),
                                        verbosity=self.verbosity)
            log.debug('{}: {}'.format(self.gcid, ces))
            # Set EControl UEP Target fields
            ectl = genz.EControl(ces.EControl, ces)
            ectl.field.ErrUEPTgt = genz.UEPTgt.TgtPFMSFM
            ectl.field.EventUEPTgt = genz.UEPTgt.TgtPFMSFM
            ectl.field.MechUEPTgt = genz.UEPTgt.TgtPFMSFM
            ectl.field.MediaUEPTgt = genz.UEPTgt.TgtPFMSFM
            # Set Fault Injection Enable
            ectl.field.ErrFaultInjEnb = 1 # Revisit: Always?
            ces.EControl = ectl.val
            self.control_write(ces,
                        genz.ComponentErrorSignalStructure.EControl,
                        sz=2, off=4)
            # Set EControl2 UEP Target fields
            # Revisit: Since Core.PwrMgrEnb already specifies Disabled/CID/GCID
            # why does PwrUEPTgt also have CID/GCID?
            ectl2 = genz.EControl2(ces.EControl2, ces)
            ectl2.field.PwrUEPTgt = genz.UEPTgt.TgtPFMSFM
            ces.EControl2 = ectl2.val
            self.control_write(ces,
                        genz.ComponentErrorSignalStructure.EControl2, sz=4)
            # Get/Set C-Event/I-Event capabilities
            cap1 = genz.ErrSigCAP1(ces.ErrSigCAP1, ces)
            cap1ctl = genz.ErrSigCAP1Control(ces.ErrSigCAP1Control, ces)
            if cap1.field.CEventInjSup:
                cap1ctl.field.CEventInjEnb = 1
            if cap1.field.IEventInjSup:
                cap1ctl.field.IEventInjEnb = 1
            ces.ErrSigCAP1Control = cap1ctl.val
            # Revisit: switch doesn't like sz=2, off=6, because at
            # least on orthus that turns into a 4-byte ControlWrite to
            # a 2-byte-aligned addr
            #self.control_write(ces,
            #            genz.ComponentErrorSignalStructure.ErrSigCAP1Control,
            #            sz=2, off=6)
            self.control_write(ces,
                        genz.ComponentErrorSignalStructure.ErrSigCAP1,
                        sz=4, off=4)
            # Set CErrorSigTgt/CErrorDetect
            self.cerror_init(ces)
            # If supported, set CEventSigTgt/CEventDetect
            if cap1.field.CEventDetectSup:
                self.cevent_init(ces)
            # If supported, set IEventSigTgt/IEventDetect
            if cap1.field.IEventDetectSup:
                self.ievent_init(ces)
            # IError setup is done by iface_init()
            if not self.local_br:
                # Set MV/MgmtVC/Iface
                pfm_rts = self.fab.get_routes(self, self.fab.pfm)
                ces.MgmtVC0 = 0 # Revisit: VC should come from route
                ces.MgmtIface0 = pfm_rts[0][0].egress_iface.num
                ces.MV0 = 1
                for i in range(0, len(pfm_rts)):
                    if pfm_rts[i][0].egress_iface.num != ces.MgmtIface0:
                        # an HA route using a different egress_iface
                        ces.MgmtVC1 = 0 # Revisit: VC should come from route
                        ces.MgmtIface1 = pfm_rts[i][0].egress_iface.num
                        ces.MV1 = 1
                        break
                    # end if
                # end for
                self.control_write(ces,
                            genz.ComponentErrorSignalStructure.MV0, sz=8)
                # Set PFM UEP Mask
                ces.PFMUEPMask = 0x01 # use MgmtVC/Iface0
                self.control_write(ces,
                            genz.ComponentErrorSignalStructure.PMUEPMask, sz=8)
            # end if local_br
        # end with

    def switch_init(self, core):
        genz = zephyr_conf.genz
        switch_file = self.switch_dir / 'component_switch'
        with switch_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            switch = self.map.fileToStruct('component_switch', data, fd=f.fileno(),
                                           verbosity=self.verbosity)
            log.debug('{}: {}'.format(self.gcid, switch))
            # Revisit: write MV/MGMT VC/MGMT Iface ID
            # Revisit: write MCPRTEnb, MSMCPRTEnb, Default MC Pkt Relay
            # Enable Packet Relay
            sw_op_ctl = genz.SwitchOpCTL(switch.SwitchOpCTL, core)
            sw_op_ctl.field.PktRelayEnb = 1
            switch.SwitchOpCTL = sw_op_ctl.val
            self.control_write(
                switch, genz.ComponentSwitchStructure.SwitchCAP1Control, sz=8)
        # end with

    def rsp_page_grid_init(self, core, valid=0):
        if self.rsp_pg_dir is None:
            return
        if self.max_data == 0:
            log.warning('{}: component has Rsp Page Grid but MaxData==0'.format(
                self.gcid))
            return
        # Revisit: return if rsp_pg should be host managed
        rsp_pg_file = self.rsp_pg_dir / 'component_page_grid'
        with rsp_pg_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            pg = self.map.fileToStruct('component_page_grid', data,
                                       fd=f.fileno(),
                                       verbosity=self.verbosity)
            log.debug('{}: {}'.format(self.gcid, pg))
            # Revisit: verify the PG-PTE-UUID
        # end with
        # Cover all of data space using 2 page grids each with half the
        # available PTEs, one for direct-mapped pages and one for interleave
        pte_cnt = pg.PTETableSz // 2
        ps = max(ceil_log2(self.max_data / pte_cnt), 12)
        self.rsp_page_grid_ps = ps
        # Revisit: verify pg.PGTableSz >= 2
        rsp_pg_table_file = self.rsp_pg_table_dir / 'pg_table'
        with rsp_pg_table_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            pg_table = self.map.fileToStruct('pg_table', data,
                                             path=rsp_pg_table_file,
                                             fd=f.fileno(), parent=pg,
                                             verbosity=self.verbosity)
            log.debug('{}: {}'.format(self.gcid, pg_table))
            pg_table[0].PGBaseAddr = 0
            pg_table[0].PageSz = ps
            pg_table[0].RES = 0
            pg_table[0].PageCount = pte_cnt
            pg_table[0].BasePTEIdx = 0
            pg_table[1].PGBaseAddr = 1 << (63 - 12)
            pg_table[1].PageSz = ps
            pg_table[1].RES = 0
            pg_table[1].PageCount = pte_cnt
            pg_table[1].BasePTEIdx = pte_cnt
            for i in range(2, pg.PGTableSz):
                pg_table[i].PageCount = 0
            for i in range(0, pg.PGTableSz):
                self.control_write(pg_table, pg_table.element.R0,
                                   off=16*i, sz=16)
        # end with
        rsp_pte_table_file = self.rsp_pte_table_dir / 'pte_table'
        with rsp_pte_table_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            pte_table = self.map.fileToStruct('pte_table', data,
                                              path=rsp_pte_table_file,
                                              fd=f.fileno(), parent=pg,
                                              verbosity=self.verbosity)
            log.debug('{}: {}'.format(self.gcid, pte_table))
            for i in range(0, pte_cnt):
                pte_table[i].V = valid
                pte_table[i].RORKey = NO_ACCESS_RKEY.val
                pte_table[i].RWRKey = NO_ACCESS_RKEY.val
                # Revisit: non-zero-based addressing
                pte_table[i].ADDR = i * (1 << ps)
                # Revisit: add PA/CCE/CE/WPE/PSE/LPE/IE/PFE/RKMGR/PASID/RK_MGR
            for i in range(pte_cnt, pg.PTETableSz):
                pte_table[i].V = 0
            for i in range(0, pg.PTETableSz):
                self.control_write(pte_table, pte_table.element.V,
                                   off=pte_table.element.Size*i,
                                   sz=pte_table.element.Size)
        # end with

    def comp_dest_read(self, prefix='control', haveCore=True):
        if self.comp_dest is not None:
            return self.comp_dest
        comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        comp_dest_file = comp_dest_dir / 'component_destination_table'
        with comp_dest_file.open(mode='rb') as f:
            data = bytearray(f.read())
            comp_dest = self.map.fileToStruct(
                'component_destination_table',
                data, fd=f.fileno(), verbosity=self.verbosity)
        # end with
        if haveCore:
            self.comp_dest = comp_dest
            self.core.comp_dest = comp_dest # Revisit: two copies
            self.core.comp_dest.HCS = self.route_control_read(prefix=prefix)
        return comp_dest

    # returns route_control.HCS
    def route_control_read(self, prefix='control'):
        genz = zephyr_conf.genz
        try:  # Revisit: route control is required, but missing in current HW
            rc_dir = list(self.switch_dir.glob('route_control@*'))[0]
        except IndexError:
            rc_dir = None
        if rc_dir is not None:
            rc_path = rc_dir / 'route_control'
            with rc_path.open(mode='rb') as f:
                data = bytearray(f.read())
                rc = self.map.fileToStruct('route_control', data,
                                parent=self.core.sw, core=self.core,
                                fd=f.fileno(), verbosity=self.verbosity)
                self.core.route_control = rc
                cap1 = genz.RCCAP1(rc.RCCAP1, rc)
                hcs = cap1.field.HCS
            # end with
        else:  # Route Control is missing - assume HCS=0
            self.core.route_control = None
            hcs = 0

        return hcs

    def switch_read(self, prefix='control'):
        if self.core.sw is not None or self.switch_dir is None:
            return self.core.sw
        switch_file = self.switch_dir / 'component_switch'
        with switch_file.open(mode='rb') as f:
            data = bytearray(f.read())
            self.core.sw = self.map.fileToStruct('component_switch',
                                data, fd=f.fileno(), verbosity=self.verbosity)
        # end with
        self.core.sw.HCS = self.route_control_read(prefix=prefix)
        return self.core.sw

    def num_vcs(self, prefix='control'):
        if self._num_vcs is not None:
            return self._num_vcs
        max_hvs = max(self.interfaces, key=lambda i: i.hvs).hvs
        self._num_vcs = max_hvs + 1
        log.debug('{}: num_vcs={}'.format(self.gcid, self._num_vcs))
        return self._num_vcs

    def rit_write(self, iface, eim):
        if self.rit_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        rit_file = self.rit_dir / 'rit'
        with rit_file.open(mode='rb+', buffering=0) as f:
            if self.rit is None:
                data = bytearray(f.read())
                self.rit = self.map.fileToStruct('rit', data, path=rit_file,
                                     fd=f.fileno(), verbosity=self.verbosity)
            else:
                self.rit.set_fd(f)
            # Revisit: more than 32 interfaces
            self.rit[iface.num].EIM = eim
            self.control_write(self.rit, self.rit.element.EIM,
                               off=4*iface.num, sz=4)
        # end with

    def req_vcat_size(self, prefix='control'):
        if self._req_vcat_sz is not None:
            return self._req_vcat_sz
        comp_dest = self.comp_dest_read(prefix=prefix)
        rows = 16  # Revisit: enum
        cols = comp_dest.REQVCATSZ
        self._req_vcat_sz = (rows, cols)
        log.debug('{}: req_vcat_sz={}'.format(self.gcid, self._req_vcat_sz))
        return self._req_vcat_sz

    def req_vcat_write(self, vc, vcm, action=0, th=None):
        if self.req_vcat_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        req_vcat_file = self.req_vcat_dir / 'req_vcat'
        with req_vcat_file.open(mode='rb+', buffering=0) as f:
            if self.req_vcat is None:
                data = bytearray(f.read())
                self.req_vcat = self.map.fileToStruct('req_vcat', data,
                                    path=req_vcat_file, parent=self.comp_dest,
                                    fd=f.fileno(), verbosity=self.verbosity)
            else:
                self.req_vcat.set_fd(f)
            sz = ctypes.sizeof(self.req_vcat.element)
            self.req_vcat[vc][action].VCM = vcm
            if th is not None and sz == 8:
                self.req_vcat[vc][action].TH = th
            self.control_write(self.req_vcat, self.req_vcat.element.VCM,
                               off=self.req_vcat.cs_offset(vc, action), sz=sz)
        # end with

    def rsp_vcat_size(self, prefix='control'):
        if self._rsp_vcat_sz is not None:
            return self._rsp_vcat_sz
        comp_dest = self.comp_dest_read(prefix=prefix)
        rows = self.num_vcs(prefix=prefix)
        cols = comp_dest.RSPVCATSZ
        self._rsp_vcat_sz = (rows, cols)
        log.debug('{}: rsp_vcat_sz={}'.format(self.gcid, self._rsp_vcat_sz))
        return self._rsp_vcat_sz

    def rsp_vcat_write(self, vc, vcm, action=0, th=None):
        if self.rsp_vcat_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        rsp_vcat_file = self.rsp_vcat_dir / 'rsp_vcat'
        with rsp_vcat_file.open(mode='rb+', buffering=0) as f:
            if self.rsp_vcat is None:
                data = bytearray(f.read())
                self.rsp_vcat = self.map.fileToStruct('rsp_vcat', data,
                                    path=rsp_vcat_file, parent=self.comp_dest,
                                    fd=f.fileno(), verbosity=self.verbosity)
            else:
                self.rsp_vcat.set_fd(f)
            sz = ctypes.sizeof(self.rsp_vcat.element)
            self.rsp_vcat[vc][action].VCM = vcm
            self.control_write(self.rsp_vcat, self.rsp_vcat.element.VCM,
                               off=self.rsp_vcat.cs_offset(vc, action), sz=sz)
        # end with

    def ssdt_size(self, prefix='control', haveCore=True):
        if self._ssdt_sz is not None:
            return self._ssdt_sz
        comp_dest = self.comp_dest_read(prefix=prefix, haveCore=haveCore)
        rows = comp_dest.SSDTSize
        cols = comp_dest.MaxRoutes
        self._ssdt_sz = (rows, cols)
        log.debug('{}: ssdt_sz={}'.format(self.gcid, self._ssdt_sz))
        return self._ssdt_sz

    def compute_mhc(self, cid, rt, hc, valid):
        if self.ssdt is None:
            return (hc, rt != 0, False)
        # Revisit: what about changes to other fields, like VCA & EI?
        curV = self.ssdt[cid][rt].V
        if valid:
            # Revisit: enum
            cur_min = min(self.ssdt[cid], key=lambda x: x.HC if x.V else 63)
            cur_min = cur_min.HC if cur_min.V else 63
            new_min = min(cur_min, hc)
        else:
            cur_min = self.ssdt[cid][0].MHC
            new_min = min((self.ssdt[cid][i] for i in range(len(self.ssdt[cid]))
                          if i != rt), key=lambda x: x.HC if x.V else 63)
            new_min = new_min.HC if new_min.V else 63
        wr0 = new_min != cur_min and rt != 0
        wrN = not valid or new_min < cur_min or valid != curV
        return (new_min, wr0, wrN)

    def ssdt_read(self):
        if self.ssdt is not None or self.ssdt_dir is None:
            return self.ssdt
        # Revisit: avoid open/close (via "with") on every read?
        ssdt_file = self.ssdt_dir / 'ssdt'
        with ssdt_file.open(mode='rb+', buffering=0) as f:
            data = bytearray(f.read())
            self.ssdt = self.map.fileToStruct('ssdt', data, path=ssdt_file,
                                    core=self.core, parent=self.comp_dest,
                                    fd=f.fileno(), verbosity=self.verbosity)
        return self.ssdt

    def ssdt_write(self, cid, ei, rt=0, valid=1, mhc=None, hc=None, vca=None,
                   mhcOnly=False):
        if self.ssdt_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        ssdt_file = self.ssdt_dir / 'ssdt'
        with ssdt_file.open(mode='rb+', buffering=0) as f:
            if self.ssdt is None:
                data = bytearray(f.read())
                self.ssdt = self.map.fileToStruct('ssdt', data, path=ssdt_file,
                                    core=self.core, parent=self.comp_dest,
                                    fd=f.fileno(), verbosity=self.verbosity)
            else:
                self.ssdt.set_fd(f)
            sz = ctypes.sizeof(self.ssdt.element)
            self.ssdt[cid][rt].MHC = mhc if (mhc is not None and rt == 0) else 0
            if not mhcOnly:
                self.ssdt[cid][rt].EI = ei
                self.ssdt[cid][rt].V = valid
                self.ssdt[cid][rt].HC = hc if hc is not None else 0
                self.ssdt[cid][rt].VCA = vca if vca is not None else 0
            self.control_write(self.ssdt, self.ssdt.element.MHC,
                               off=self.ssdt.cs_offset(cid, rt), sz=sz)
        # end with

    def update_rit_dir(self, prefix='control'):
        if self.rit_dir is None:
            return
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        self.rit_dir = list(self.comp_dest_dir.glob('rit@*'))[0]
        log.debug('new rit_dir = {}'.format(self.rit_dir))

    def update_req_vcat_dir(self, prefix='control'):
        if self.req_vcat_dir is None:
            return
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        self.req_vcat_dir = list(self.comp_dest_dir.glob('req_vcat@*'))[0]
        log.debug('new req_vcat_dir = {}'.format(self.req_vcat_dir))

    def update_rsp_vcat_dir(self, prefix='control'):
        if self.rsp_vcat_dir is None:
            return
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        self.rsp_vcat_dir = list(self.comp_dest_dir.glob('rsp_vcat@*'))[0]
        log.debug('new rsp_vcat_dir = {}'.format(self.rsp_vcat_dir))

    def update_ssdt_dir(self, prefix='control'):
        if self.ssdt_dir is None:
            return
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        self.ssdt_dir = list(self.comp_dest_dir.glob('ssdt@*'))[0]
        log.debug('new ssdt_dir = {}'.format(self.ssdt_dir))

    def update_opcode_set_dir(self, prefix='control'):
        if self.opcode_set_dir is None:
            return
        self.opcode_set_dir = list((self.path / prefix).glob(
            'opcode_set@*'))[0]
        log.debug('new opcode_set_dir = {}'.format(self.opcode_set_dir))
        if self.opcode_set_table_dir is None:
            return
        self.opcode_set_table_dir = list(self.opcode_set_dir.glob(
                'opcode_set_table/opcode_set_table0@*'))[0]
        log.debug('new opcode_set_table_dir = {}'.format(self.opcode_set_table_dir))

    def update_switch_dir(self, prefix='control'):
        if self.switch_dir is None:
            return
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        self.switch_dir = list((self.path / prefix).glob(
            'component_switch@*'))[0]
        log.debug('new switch_dir = {}'.format(self.switch_dir))

    def update_ces_dir(self, prefix='control'):
        if self.ces_dir is None:
            return
        self.ces_dir = list((self.path / prefix).glob(
            'component_error_and_signal_event@*'))[0]
        log.debug('new ces_dir = {}'.format(self.ces_dir))

    def update_rsp_page_grid_dir(self, prefix='control'):
        if self.rsp_pg_dir is None:
            return
        self.rsp_pg_dir = self.find_rsp_page_grid_path(prefix)
        self.rsp_pg_table_dir = list(self.rsp_pg_dir.glob('pg_table@*'))[0]
        self.rsp_pte_table_dir = list(self.rsp_pg_dir.glob('pte_table@*'))[0]
        log.debug('new rsp_pg_dir = {}'.format(self.rsp_pg_dir))

    def update_path(self):
        log.debug('current path: {}'.format(self.path))
        self.path = self.fab.make_path(self.gcid)
        log.debug('new path: {}'.format(self.path))
        self.update_ssdt_dir()
        self.update_rit_dir()
        self.update_req_vcat_dir()
        self.update_rsp_vcat_dir()
        self.update_switch_dir()
        self.update_ces_dir()
        self.update_opcode_set_dir()
        self.update_rsp_page_grid_dir()
        for iface in self.interfaces:
            iface.update_path(prefix='control')

    @property
    def rit_only(self):
        return self.ssdt_dir is None

    @property
    def has_switch(self):
        return self.switch_dir is not None

    def config_interface(self, iface, pfm, ingress_iface, prev_comp):
        args = zephyr_conf.args
        iface.update_peer_info()
        # get peer CState
        peer_cstate = iface.peer_cstate
        if prev_comp:
            prev_comp.cstate = peer_cstate
        msg = '{}: exploring interface{}, peer cstate={!s}, '.format(
            self.gcid, iface.num, peer_cstate)
        if iface.peer_inband_disabled:
            msg += 'peer inband management disabled - ignoring peer'
            log.info(msg)
            return
        elif iface.boundary_interface:
            msg += 'boundary interface - ignoring peer'
            log.info(msg)
            return
        if iface.peer_mgr_type == 0:  # Revisit: enum
            # Revisit: mamba/switch/orthus reporting wrong value
            #msg += 'peer manager type is not Fabric - ignoring peer'
            msg += 'peer manager type is not Fabric - claiming anyway, '
            #log.info(msg)
            #return
        # We need to distinguish 3 main cstate cases here:
        # 1. cstate is C-CFG - component is ready for us to configure
        #    using directed relay.
        # 2. cstate is C-Up:
        #    a. Component has no valid GCID (should not happen) - ignore it
        #       Revisit: try peer-c-reset link CTL
        #    b. Component has GCID match in our topology
        #       Do nonce exchange with peer - 2 sub-cases:
        #       i. Nonce matches
        #          Topology has a cycle; this is another path to a component
        #          we've already configured. Add new link to topology and
        #          recompute routes; do nothing else.
        #       ii. Nonce mismatch
        #           Not the component we thought it was
        #           Revisit: try to contact foreign FM
        #    c. GCID is unknown to us:
        #       Revisit: try to contact foreign FM
        # 3. cstate is C-LP/C-DLP:
        #    Revisit: handle these power states
        # Note: C-Down is handled in explore_interfaces() - we never get here.
        if peer_cstate is CState.CUp:
            reset_required = False
            peer_c_reset_only = False
            # get PeerGCID
            peer_gcid = iface.peer_gcid
            msg += 'peer gcid={}'.format(peer_gcid)
            if peer_gcid is None:
                msg += 'peer is C-Up but GCID not valid - ignoring peer'
                log.warning(msg)
                return
            if peer_gcid in self.fab.comp_gcids: # another path?
                comp = self.fab.comp_gcids[peer_gcid]
                peer_iface = comp.interfaces[iface.peer_iface_num]
                iface.set_peer_iface(peer_iface)
                nonce_valid = iface.do_nonce_exchange()
                if not nonce_valid:
                    iface.set_peer_iface(None)
                    msg += ' nonce mismatch'
                    log.warning(msg)
                    # Revisit: contact foreign FM
                    return
                self.fab.add_link(iface, peer_iface)
                msg += ' additional path to {}'.format(comp)
                log.info(msg)
                # new path might enable additional or shorter routes
                self.fab.recompute_routes(iface, peer_iface)
            elif args.reclaim:
                msg += ', reclaiming C-Up component'
                path = self.fab.make_path(peer_gcid)
                comp = Component(iface.peer_cclass, self.fab, self.map, path,
                                 self.mgr_uuid, br_gcid=self.br_gcid,
                                 netlink=self.nl, verbosity=self.verbosity)
                peer_iface = Interface(comp, iface.peer_iface_num, iface,
                                       usable=True)
                iface.set_peer_iface(peer_iface)
                gcid = self.fab.assign_gcid(comp, proposed_gcid=peer_gcid)
                if gcid is None:
                    msg += ', gcid conflict, reset required'
                    log.warning(msg)
                    reset_required = True
                    peer_c_reset_only = True
                else:
                    msg += ', retaining gcid={}'.format(gcid)
                    log.info(msg)
                if path.exists():
                    comp.remove_fab_comp()
                if not reset_required:
                    self.fab.add_link(iface, peer_iface)
                    route = self.fab.setup_bidirectional_routing(
                        pfm, comp, write_to_ssdt=False)
                    try:
                        comp.add_fab_comp(setup=True)
                    except Exception as e:
                        log.error('add_fab_comp failed with exception {}'.format(e))
                        reset_required = True
                        peer_c_reset_only = True
                if not reset_required:
                    usable = comp.comp_init(pfm, ingress_iface=peer_iface,
                                            route=route[1])
                    reset_required = not usable
                    if usable and comp.has_switch:  # if switch, recurse
                        comp.explore_interfaces(pfm, ingress_iface=peer_iface)
                if reset_required:
                    peer_cstate = comp.warm_reset(iface,
                                            peer_c_reset_only=peer_c_reset_only)
                    if peer_cstate is not CState.CCFG:
                        log.warning('unable to reset - ignoring component on {}'.format(
                            iface))
                        return
            elif args.accept_cids: # Revisit: mostly duplicate of reclaim
                # Revisit: add prev_comp handling
                path = self.fab.make_path(peer_gcid)
                comp = Component(iface.peer_cclass, self.fab, self.map, path,
                                 self.mgr_uuid, br_gcid=self.br_gcid,
                                 netlink=self.nl, verbosity=self.verbosity)
                peer_iface = Interface(comp, iface.peer_iface_num, iface)
                iface.set_peer_iface(peer_iface)
                gcid = self.fab.assign_gcid(comp, proposed_gcid=peer_gcid)
                if gcid is None:
                    msg += ' gcid conflict, ignoring component'
                    log.warning(msg)
                    return
                msg += ' retaining gcid={}'.format(gcid)
                log.info(msg)
                self.fab.add_link(iface, peer_iface)
                route = self.fab.setup_bidirectional_routing(
                    pfm, comp, write_to_ssdt=False)
                try:
                    comp.add_fab_comp(setup=True)
                except Exception as e:
                    log.error('add_fab_comp failed with exception {}'.format(e))
                    return
                usable = comp.comp_init(pfm, ingress_iface=peer_iface, route=route[1])
                if usable and comp.has_switch:  # if switch, recurse
                    comp.explore_interfaces(pfm, ingress_iface=peer_iface)
                elif not usable:
                    log.warning(f'{comp} is not usable')
                    return
            else:
                msg += ' ignoring unknown component'
                log.warning(msg)
                return
            # end if peer_gcid
        # end if CUp
        if peer_cstate is CState.CCFG: # Note: not 'elif'
            from zephyr_route import DirectedRelay
            dr = DirectedRelay(self, ingress_iface, iface)
            if prev_comp is None:
                comp = Component(iface.peer_cclass, self.fab, self.map, dr.path,
                                 self.mgr_uuid, dr=dr, br_gcid=self.br_gcid,
                                 netlink=self.nl, verbosity=self.verbosity)
                peer_iface = Interface(comp, iface.peer_iface_num, iface)
                iface.set_peer_iface(peer_iface)
                gcid = self.fab.assign_gcid(comp)
                msg += 'assigned gcid={}'.format(gcid)
                self.fab.add_link(iface, peer_iface)
            else: # have a prev_comp
                comp = prev_comp
                comp.set_dr(dr)
                peer_iface = iface.peer_iface
                gcid = comp.gcid
                msg += 'reusing previously-assigned gcid={}'.format(gcid)
            # deal with "leftover" comp path from previous zephyr run
            path = self.fab.make_path(gcid)
            if path.exists():
                leftover = Component(iface.peer_cclass, self.fab, self.map,
                                     path, self.mgr_uuid,
                                     gcid=gcid, br_gcid=self.br_gcid,
                                     netlink=self.nl, verbosity=self.verbosity)
                leftover.remove_fab_comp()
                self.fab.remove_node(leftover)
                del self.fab.components[leftover.uuid]
            log.info(msg)
            route = self.fab.setup_bidirectional_routing(
                pfm, comp, write_to_ssdt=False) # comp_init() will write SSDT
            try:
                comp.add_fab_dr_comp()
            except Exception as e:
                log.error('add_fab_dr_comp failed with exception {}'.format(e))
                return
            usable = comp.comp_init(pfm, prefix='dr', ingress_iface=peer_iface,
                                    route=route[1])
            if usable and comp.has_switch:  # if switch, recurse
                comp.explore_interfaces(pfm, ingress_iface=peer_iface)
            elif not usable:
                log.warning(f'{comp} is not usable')
        # end if peer_cstate

    def explore_interfaces(self, pfm, ingress_iface=None, explore_ifaces=None,
                           prev_comp=None):
        if explore_ifaces is None:
            # examine all interfaces (except ingress) & init those components
            explore_ifaces = self.interfaces
        for iface in explore_ifaces:
            if iface == ingress_iface:
                log.debug('{}: skipping ingress interface{}'.format(
                    self.gcid, iface.num))
            elif iface.usable:
                self.config_interface(iface, pfm, ingress_iface, prev_comp)
            else:
                log.info('{}: interface{} is not usable'.format(
                    self.gcid, iface.num))

    def update_cstate(self, prefix='control'):
        genz = zephyr_conf.genz
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            # Revisit: optimize this to avoid reading entire Core struct
            data = bytearray(f.read())
            core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                         verbosity=self.verbosity)
            cstatus = genz.CStatus(core.CStatus, core)
            self.cstate = CState(cstatus.field.CState)

    def unreachable_comp(self, to, iface, route):
        log.warning('{}: unreachable comp {} due to {} failure'.format(
            self, to, iface))
        # tear down route from "self" to "to"'
        self.fab.teardown_routing(self, to, [route])

    def warm_reset(self, iface, prefix='control', peer_c_reset_only=False):
        if not peer_c_reset_only:
            log.debug('attempting component warm reset of {}'.format(self))
            core_file = self.path / prefix / 'core@0x0/core'
            with core_file.open(mode='rb+') as f:
                data = bytearray(f.read())
                core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                             verbosity=self.verbosity)
                # Revisit: check read data (ZUUID?) is not all ones
                cctl = genz.CControl(core.CControl, core)
                cctl.field.ComponentReset = CReset.WarmReset
                core.CControl = cctl.val
                self.control_write(core, genz.CoreStructure.CControl, sz=8)
            # end with
        # end if
        iface.update_peer_info()
        # if still not C-CFG, use peer_c_reset()
        if iface.peer_cstate is not CState.CCFG:
            log.debug('attempting peer_c_reset of {} via {}'.format(
                self, iface))
            iface.peer_c_reset()
            iface.update_peer_info()
        return iface.peer_cstate

    def enable_sfm(self, sfm, prefix='control'):
        '''Enable @sfm as Secondary Fabric Manager of this component and
        setup bidirectional routing.
        '''
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            genz = zephyr_conf.genz
            core = self.core
            core.set_fd(f)
            # set SFMSID/SFMCID
            # Revisit: subnets
            core.SFMCID = sfm.gcid.cid
            self.control_write(core, genz.CoreStructure.SFMCID, sz=4, off=4)
            # set SFMCIDValid
            cap2ctl = genz.CAP2Control(core.CAP2Control, core)
            cap2ctl.field.SFMCIDValid = 1
            core.CAP2Control = cap2ctl.val
            self.control_write(core, genz.CoreStructure.CAP2Control, sz=8)
            # set SecondaryFabMgrRole, HostMgrMGRUUIDEnb (only on SFM component)
            if self is sfm:
                cap1ctl = genz.CAP1Control(core.CAP1Control, core)
                cap1ctl.SecondaryFabMgrRole = 1
                cap1ctl.HostMgrMGRUUIDEnb = HostMgrUUID.Core
                core.CAP1Control = cap1ctl.val
                self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
        # end with
        routes = self.fab.setup_bidirectional_routing(sfm, self)
        return routes # Revisit

    def lookup_iface(self, iface_str: str) -> Interface:
        gcid_str, iface_num_str = iface_str.split('.')
        gcid = GCID(str=gcid_str)
        # Revisit: compare gcid to self.gcid
        iface_num = int(iface_num_str)
        return self.interfaces[iface_num]

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.gcid)

class Memory(Component):
    cclasses = (0x1, 0x2)

class Switch(Component):
    cclasses = (0x3, 0x4, 0x5)

class Accelerator(Component):
    cclasses = (0x8, 0x9, 0xA, 0xB)

class IO(Component):
    cclasses = (0xC, 0xD, 0xE, 0xF)

class MultiClass(Component):
    # Revisit: verify that the required Service UUID structure exists
    cclasses = (0x13,)

class Bridge(Component):
    cclasses = (0x14, 0x15)

    def unreachable_comp(self, to, iface, route):
        super().unreachable_comp(to, iface, route)
        # Revisit: finish this - notify llamas instance about
        # unreachable resources

class LocalBridge(Bridge):
    def __init__(self, *args, brnum, **kwargs):
        self.brnum = brnum
        super().__init__(*args, **kwargs)

    def update_path(self):
        log.debug('current path: {}'.format(self.path))
        sys_devices = Path('/sys/devices')
        fabrics = sys_devices.glob('genz*')
        for fab_path in fabrics:
            br_paths = fab_path.glob('bridge*')
            for br_path in br_paths:
                br_num = component_num(br_path)
                if self.brnum == br_num:
                    self.path = br_path
                    self.update_ssdt_dir()
                    self.update_rit_dir()
                    self.update_req_vcat_dir()
                    self.update_rsp_vcat_dir()
                    self.update_switch_dir()
                    self.update_ces_dir()
                    self.update_opcode_set_dir()
                    self.update_rsp_page_grid_dir()
                    log.debug('new path: {}'.format(self.path))
                    for iface in self.interfaces:
                        iface.update_path()
                    self.fru_uuid = get_fru_uuid(self.path)
                    return
                # end if
            # end for br_path
        # end for fab_path

    def unreachable_comp(self, to, iface, route):
        super().unreachable_comp(to, iface, route)
        # remove "to" from /sys fabric
        if to.dr is not None:
            to.remove_fab_dr_comp()
        else:
            to.remove_fab_comp()
