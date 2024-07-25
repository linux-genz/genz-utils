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
from genz.genz_common import GCID, CState, IState, AKey, RKey, PHYOpStatus, ErrSeverity, CReset, HostMgrUUID, genzUUID, RefCount, MAX_HC, AllOnesData, DEFAULT_AKEY
import os
import re
import time
from pdb import set_trace
from uuid import UUID, uuid4
from math import ceil, floor, log2
from pathlib import Path
from typing import List
import zephyr_conf
from zephyr_conf import log, INVALID_GCID
from zephyr_iface import Interface
from blueprints.resource.blueprint import send_resource

# Revisit: these should move to zephyr_rkey.py
ALL_RKD = 0 # all requesters are granted this RKD
FM_RKD = 0xfff  # only the FMs (PFM/SFM) are granted this RKD
FM_RKEY = RKey(rkd=FM_RKD, os=0xfab) # for FM-only control structs
NO_ACCESS_RKEY = RKey(rkd=FM_RKD, os=0xfa15e) # no-access: rsp RO+RW; read-only: rsp RW
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

def pt_ns_to_ptd_time(ns: int, granularity: int, gran_unit: bool):
    genz = zephyr_conf.genz
    if gran_unit == genz.PTGranUnit.GranUnitNS:
        mt = int(ns / granularity)
    else: # GranUnitPS
        mt = int(ns * 1000 / granularity)
    return mt


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
        self._ssap_sz = None
        self.comp_dest = None
        self.component_pa = None
        self.pt = None
        self.ssdt = None
        self.ssap = None
        self.pa = None
        self.ssdt_dir = None # needed by rt.invert() early on
        self.ces_dir = None  # needed if comp_init() fails and usable is False
        self.rkd_dir = None # needed by rkd_write()
        self.rit = None
        self.route_info = None
        self.req_vcat = None
        self.rsp_vcat = None
        self.rsp_page_grid_ps = 0
        self.service_uuid_table = None
        self.paths_setup = False
        self.partition = None
        self.pt_req_iface = None
        self.pt_rsp_ifaces = []
        self.usable = False # will be set True if comp_init() succeeds
        self.cstate = CState.CDown # will be updated by comp_init()
        fab.components[self.uuid] = self
        fab.add_node(self, instance_uuid=self.uuid, cclass=self.cclass,
                     mgr_uuid=self.mgr_uuid)

    def __hash__(self):
        return hash(self.uuid)

    def __eq__(self, other):
        if isinstance(other, Component):
            return self.uuid == other.uuid
        return NotImplemented

    def to_json(self, verbosity=0):
        if verbosity == 0:
            return self.cuuid_serial
        js = { 'cclass': self.cclass,
               'cstate': str(self.cstate),
               'fru_uuid': self.fru_uuid,
               'gcids': [ str(self.gcid) ],
               'id': self.cuuid_serial,
               'instance_uuid': self.uuid,
               'max_data': self.max_data,
               'max_iface': self.max_iface,
               'mgr_uuid': self.mgr_uuid,
               'mod_timestamp': self.fab.get_mod_timestamp(self)[1],
               'nonce': self.fab.encrypt_nonce(self.nonce),
               'rsp_page_grid_ps': self.rsp_page_grid_ps
               }
        name = self.fab.get_comp_name(self)
        if name is not None:
            js['name'] = name
        return js

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
            raise AllOnesData(f'{self}: all-ones data')

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

    def remove_fab_comp(self, force=False, useDR=True, useTMP=True, rm_paths=True):
        if not (force or self.paths_setup):
            return None
        log.debug(f'remove_fab_comp for {self}, paths_setup={self.paths_setup}, force={force}')
        cmd_name = self.nl.cfg.get('REMOVE_FAB_COMP')
        data = {'gcid':     self.gcid.val,
                'br_gcid':  self.br_gcid.val,
                'tmp_gcid': self.tmp_gcid.val if (self.tmp_gcid and useTMP) else INVALID_GCID.val,
                'dr_gcid':  self.dr.gcid.val if (self.dr and useDR) else INVALID_GCID.val,
                'dr_iface': self.dr.egress_iface.num if (self.dr and useDR) else 0,
                'mgr_uuid': self.mgr_uuid,
        }
        msg = self.nl.build_msg(cmd=cmd_name, data=data)
        ret = self.nl.sendmsg(msg)
        if rm_paths:
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
        if not self.paths_setup:
            return None
        log.debug(f'remove_fab_dr_comp for {self}, paths_setup={self.paths_setup}')
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
            # Revisit: optimize this to avoid reading entire Core struct
            data = bytearray(f.read())
            core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                         verbosity=self.verbosity)
            if core.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: core structure all-ones data')
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
                cap1 = genz.PGZMMUCAP1(pg.PGZMMUCAP1, pg, check=True)
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
            self.component_pa_dir = list((self.path / prefix).glob(
                'component_pa@*'))[0]
        except IndexError:
            self.component_pa_dir = None
        try:
            self.ssdt_dir = list(self.comp_dest_dir.glob('ssdt@*'))[0]
        except IndexError:
            self.ssdt_dir = None
        try:
            self.ssap_dir = list(self.component_pa_dir.glob('ssap@*'))[0]
        except (IndexError, AttributeError):
            self.ssap_dir = None
        try:
            self.peer_attr_dir = list(self.component_pa_dir.glob('pa@*'))[0]
        except (IndexError, AttributeError):
            self.peer_attr_dir = None
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
        try:
            self.rkd_dir = list(self.comp_dest_dir.glob('component_rkd@*'))[0]
        except IndexError:
            self.rkd_dir = None
        self.rsp_pg_dir = self.find_rsp_page_grid_path(prefix)
        if self.rsp_pg_dir is not None:
            self.rsp_pg_table_dir = list(self.rsp_pg_dir.glob(
                'pg_table@*'))[0]
            self.rsp_pte_table_dir = list(self.rsp_pg_dir.glob(
                'pte_table@*'))[0]
        try: # Revisit: only 1 caccess_dir supported
            self.caccess_dir = list((self.path / prefix / 'component_c_access').glob(
                'component_c_access0@*'))[0]
        except IndexError:
            self.caccess_dir = None
        if self.caccess_dir is not None:
            try:
                self.caccess_rkey_dir = list(self.caccess_dir.glob(
                    'c_access_r_key@*'))[0]
            except IndexError:
                self.caccess_rkey_dir = None
        try:
            self.service_uuid_dir = list((self.path / prefix).glob(
                'service_uuid@*'))[0]
        except (IndexError, AttributeError):
            self.service_uuid_dir = None
        if self.service_uuid_dir is not None:
            self.service_uuid_table_dir = list(self.service_uuid_dir.glob(
                's_uuid@*'))[0]
        try: # Revisit: only 1 precision_time_dir supported
            self.precision_time_dir = list((self.path / prefix / 'component_precision_time').glob(
                'component_precision_time0@*'))[0]
        except IndexError:
            self.precision_time_dir = None
        self.paths_setup = True

    def remove_paths(self):
        self.comp_dest_dir = None
        self.opcode_set_dir = None
        self.opcode_set_table_dir = None
        self.ssdt_dir = None
        self.component_pa_dir = None
        self.ssap_dir = None
        self.peer_attr_dir = None
        self.req_vcat_dir = None
        self.rsp_vcat_dir = None
        self.rit_dir = None
        self.switch_dir = None
        self.ces_dir = None
        self.rkd_dir = None
        self.rsp_pg_dir = None
        self.rsp_pg_table_dir = None
        self.rsp_pte_table_dir = None
        self.caccess_dir = None
        self.caccess_rkey_dir = None
        self.service_uuid_dir = None
        self.service_uuid_table_dir = None
        self.precision_time_dir = None
        self.paths_setup = False

    def check_usable(self, prefix='control'):
        self.update_cstate(prefix=prefix)
        return (self.cstate == CState.CUp or self.cstate == CState.CLP or
                self.cstate == CState.CDLP)

    def warn_unusable(self, msg: str) -> bool:
        log.warning(f'{self}: {msg}')
        self.usable = False
        return False

    # Returns True if component is usable - is C-Up/C-LP/C-DLP, not C-Down
    def comp_init(self, pfm, prefix='control', ingress_iface=None, route=None):
        zargs = zephyr_conf.args
        genz = zephyr_conf.genz
        log.debug(f'comp_init for {self}')
        self.usable = True  # assume comp will be usable, until something goes wrong
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
                return self.warn_unusable('core structure returned all-ones data')
            # verify good data near structure end (check ZUUID)
            if core.ZUUID != genzUUID:
                return self.warn_unusable(f'invalid core structure ZUUID {core.ZUUID}')
            # save cstate and use below to control writes (e.g., CID0)
            try:
                cstatus = genz.CStatus(core.CStatus, core, check=True)
            except AllOnesData:
                return self.warn_unusable('CStatus is all-ones')
            self.cstate = CState(cstatus.field.CState)
            # save some other key values
            try:
                cap1 = genz.CAP1(core.CAP1, core, check=True)
            except AllOnesData:
                return self.warn_unusable('CAP1 is all-ones')
            self.timer_unit = cap1.field.TimerUnit
            self.ctl_timer_unit = cap1.field.CtlTimerUnit
            self.cclass = core.BaseCClass
            self.max_data = core.MaxData
            self.max_iface = core.MaxInterface
            self.cuuid = core.CUUID
            self.serial = core.SerialNumber
            self.cuuid_serial = f'{self.cuuid}:{self.serial:#018x}'
            if zargs.pause_after is not None and len(self.fab) % zargs.pause_after == 0:
                set_trace()
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
                except AllOnesData:
                    log.warning(f'{self.interfaces[ifnum]}: iface_read returned all-ones data')
                except IndexError:
                    pass
            # end for
            if pfm and self.cstate is CState.CCFG:
                if zargs.reclaim:
                    # lookup cuuid_serial and potentially adjust GCID
                    self.fab.reassign_gcid(self)
                # set CV/CID0/SID0 - first Gen-Z control write if !local_br
                # Revisit: support subnets and multiple CIDs
                core.CID0 = self.gcid.cid
                core.CV = 1
                self.control_write(core, genz.CoreStructure.CV, sz=8)
            # Revisit: MGR-UUID capture does not work on some components
            if pfm and zargs.write_mgruuid:
                # For non-local-bridge components in C-CFG, MGR-UUID will have
                # been captured on CV/CID0/SID0 write, so skip this
                # set MGR-UUID
                core.MGRUUIDl = int.from_bytes(self.mgr_uuid.bytes[0:8],
                                           byteorder='little')
                core.MGRUUIDh = int.from_bytes(self.mgr_uuid.bytes[8:16],
                                           byteorder='little')
                self.control_write(core, genz.CoreStructure.MGRUUIDl, sz=16)
            try:
                rows, cols = self.ssdt_size(prefix=prefix)
            except AllOnesData:
                return self.warn_unusable('ssdt_size returned all-ones data')
            # initialize SSDT route info (required before fixup_ssdt())
            from zephyr_route import RouteInfo
            self.route_info = [[RouteInfo() for j in range(cols)]
                               for i in range(rows)]
            # setup SSDT and RIT entries for route(s) back to FM
            if pfm and ingress_iface is not None:
                self.fixup_ssdt(route, pfm)
                self.rit_write(ingress_iface, 1 << ingress_iface.num)
            try:
                ssap_sz = self.ssap_size(prefix=prefix)
            except AllOnesData:
                return self.warn_unusable('ssap_size returned all-ones data')
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
                except AllOnesData:
                    return self.warn_unusable('CV/CID0 returned all-ones data')
                # Revisit: retry if CCTO expired?
                if core.CV == 0 and core.CID0 == 0:
                    return self.warn_unusable('CV/CID0 is 0 - CCTO expired')
                # we have set up just enough for "normal" responses to work -
                # tell the kernel about the new/changed component and stop DR
                try:
                    if self.cstate is CState.CCFG:
                        self.add_fab_comp()
                        self.tmp_gcid = None
                        self.dr = None
                        prefix = 'control'
                except Exception as e:
                    return self.warn_unusable(f'add_fab_comp(gcid={self.gcid},tmp_gcid={self.tmp_gcid},dr={self.dr}) failed with exception {e}')
                # replace DR routes from PFM with non-DR versions
                self.fab.replace_dr_routes(pfm, self)
            # end if pfm
        # end with
        self.fru_uuid = get_fru_uuid(self.path)
        self.fab.add_comp(self)
        self.fab.update_assigned_gcids(self)
        # initialize Responder Page Grid structure
        # Revisit: should we be doing this when reclaiming a C-Up comp?
        self.rsp_page_grid_init(core, readOnly=not pfm)
        self.peer_attr_init(readOnly=not pfm)
        if pfm:
            # initial ACREQ/ACRSP is unchanged; Control ops allowed
            # Revisit: NLL paIdx
            self.ssap_write(pfm.gcid.cid, self.fab.fm_akey, paIdx=0)
        if self.is_responder and self.core.MaxData > 0:
            from zephyr_res import Producer
            self.producer = Producer(self)
        if not pfm: # SFM init stops here
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
            # not all-ones and that it matches ours
            try:
                self.control_read(core, genz.CoreStructure.MGRUUIDl,
                                  sz=16, check=True)
            except AllOnesData:
                return self.warn_unusable('all-ones MGRUUID - component not owned')
            if core.MGRUUID != self.mgr_uuid:
                return self.warn_unusable(f'component MGRUUID {core.MGRUUID} != PFM MGRUUID {self.mgr_uuid} - component not owned')
            # re-read fields modified by HW during CID capture on 1st write
            self.control_read(core, genz.CoreStructure.PMCID, sz=8)
            self.control_read(core, genz.CoreStructure.CAP1Control, sz=8)
            self.control_read(core, genz.CoreStructure.CAP2Control, sz=8)
            # set PFMSID/PFMCID (must be before PrimaryFabMgrRole = 1)
            # Revisit: subnets
            core.PFMCID = pfm.gcid.cid
            self.control_write(core, genz.CoreStructure.PMCID, sz=8)
            # set PFMCIDValid; do not clear other CID/SID valid bits (yet)
            cap2ctl = genz.CAP2Control(core.CAP2Control, core)
            cap2ctl.PFMCIDValid = 1
            core.CAP2Control = cap2ctl.val
            self.control_write(core, genz.CoreStructure.CAP2Control, sz=8)
            # set HostMgrMGRUUIDEnb, MGRUUIDEnb
            cap1ctl = genz.CAP1Control(core.CAP1Control, core)
            uuEnb = HostMgrUUID.Core if self.local_br else HostMgrUUID.Zero
            cap1ctl.HostMgrMGRUUIDEnb = uuEnb
            cap1ctl.MGRUUIDEnb = 1
            # set ManagerType, PrimaryFabMgrRole; must be before PMCIDValid=0
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
            # clear other CID/SID valid bits - after ManagerType=1
            cap2ctl.field.PMCIDValid = 0
            cap2ctl.field.SFMCIDValid = 0
            cap2ctl.field.PFMSIDValid = 0
            cap2ctl.field.SFMSIDValid = 0
            core.CAP2Control = cap2ctl.val
            self.control_write(core, genz.CoreStructure.CAP2Control, sz=8)
            # set CompNonce
            core.CompNonce = self.nonce
            self.control_write(core, genz.CoreStructure.CompNonce, sz=8)
            # check that at least 1 interface can be brought Up
            iupCnt = 0
            for ifnum in range(0, core.MaxInterface):
                try:
                    iup = self.interfaces[ifnum].iface_init(prefix=prefix,
                                                no_akeys=zargs.no_akeys)
                    if iup:
                        iupCnt += 1
                except IndexError:
                    del self.interfaces[-1] # Revisit: why?
            if iupCnt == 0:
                self.usable = False
                return False
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
            core.UERT = int(zargs.uert * 1000)  # Revisit: range checks
            self.control_write(core, genz.CoreStructure.UERT, sz=8)
            # Revisit: set UNRSP, FPST, PCO FPST, NLMUTO
            # Revisit: set REQNIRTO, REQABNIRTO
            # set ControlTO, ControlDRTO
            # Revisit: how to compute reasonable values?
            core.ControlTO = self.ctl_timeout_val(zargs.control_to)
            core.ControlDRTO = self.ctl_timeout_val(zargs.control_drto)
            self.control_write(core, genz.CoreStructure.ControlTO, sz=4)
            # set MaxRequests
            # Revisit: Why would FM choose < MaxREQSuppReqs? Only for P2P?
            # Revisit: only for requesters
            core.MaxRequests = core.MaxREQSuppReqs
            self.control_write(core, genz.CoreStructure.MaxRequests, sz=8)
            # Revisit: set MaxPwrCtl (to NPWR?)
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
            # enable component AKeys (if not --no-akeys)
            # do not enable if PFM bridge cannot generate AKeys
            enb = not zargs.no_akeys and pfm.akey_sup
            self.enable_akeys(enb=enb)
            # initialize CAccess RKeys
            self.caccess_rkey_init()
            # if component is usable, set ComponentEnb - transition to C-Up
            if self.usable:
                # Revisit: before setting ComponentEnb, once again check that
                # CCTO never expired
                try:
                    cctl = genz.CControl(core.CControl, core, check=True)
                except AllOnesData:
                    return self.warn_unusable('CControl is all-ones')
                cctl.field.ComponentEnb = 1
                core.CControl = cctl.val
                self.control_write(core, genz.CoreStructure.CControl, sz=8)
                log.info(f'{self.gcid} transitioning to C-Up')
                # update our peer's peer-info (about us, now that we're C-Up)
                if (ingress_iface is not None and
                    ingress_iface.peer_iface is not None):
                    ingress_iface.peer_iface.update_peer_info()
                if zargs.sleep > 0.0:
                    log.debug('sleeping {} seconds for slow switch C-Up transition'.format(zargs.sleep))
                    time.sleep(zargs.sleep)
            else:
                log.info('{} has no usable interfaces'.format(self.path))
        # end with
        if self.has_switch:
            try:
                self.switch_init(core)
            except AllOnesData:
                return self.warn_unusable('switch_init returned all-ones data')
        self.comp_err_signal_init(core)
        if self.usable and self.is_requester:
            self.fab.rkds.add_comps_to_rkd([self], self.fab.all_rkd)
        self.fab.update_comp(self, forceTimestamp=True)
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
            if opcode_set.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: opcode set all-ones data')
            log.debug('{}: {}'.format(self.gcid, opcode_set))
            cap1 = genz.OpCodeSetCAP1(opcode_set.CAP1, opcode_set, check=True)
            cap1ctl = genz.OpCodeSetCAP1Control(opcode_set.CAP1Control,
                                                opcode_set, check=True)
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
            # Enable all Supported OpCodes for
            # Core64/Control/DR/Atomic1/LDM1/Advanced1 OpClasses
            opcode_set_table.EnabledCore64OpCodeSet = (
                opcode_set_table.SupportedCore64OpCodeSet)
            opcode_set_table.EnabledControlOpCodeSet = (
                opcode_set_table.SupportedControlOpCodeSet)
            opcode_set_table.EnabledDROpCodeSet = (
                opcode_set_table.SupportedDROpCodeSet)
            opcode_set_table.EnabledAtomic1OpCodeSet = (
                opcode_set_table.SupportedAtomic1OpCodeSet)
            opcode_set_table.EnabledLDM1OpCodeSet = (
                opcode_set_table.SupportedLDM1OpCodeSet)
            opcode_set_table.EnabledAdvanced1OpCodeSet = (
                opcode_set_table.SupportedAdvanced1OpCodeSet)
            # Revisit: add support for other OpClasses
            # Revisit: orthus tries to use >16-byte writes and fails
            #self.control_write(opcode_set_table, genz.OpCodeSetTable.SetID,
            #                   sz=opcode_set_table.Size, off=0)
            opcode_set_class = opcode_set_table.__class__
            self.control_write(opcode_set_table,
                               genz.OpCodeSetTable.EnabledCore64OpCodeSet,
                               sz=8, off=0)
            self.control_write(opcode_set_table,
                               genz.OpCodeSetTable.EnabledControlOpCodeSet,
                               sz=8, off=0)
            self.control_write(opcode_set_table,
                               opcode_set_class.EnabledDROpCodeSet,
                               sz=8, off=0)
            self.control_write(opcode_set_table,
                               genz.OpCodeSetTable.EnabledAtomic1OpCodeSet,
                               sz=8, off=0)
            self.control_write(opcode_set_table,
                               genz.OpCodeSetTable.EnabledLDM1OpCodeSet,
                               sz=8, off=0)
            self.control_write(opcode_set_table,
                               genz.OpCodeSetTable.EnabledAdvanced1OpCodeSet,
                               sz=8, off=0)
        # end with

    def cerror_init(self, ces, clearStatus=True):
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
        if clearStatus:
            self.control_write(ces,
                    genz.ComponentErrorSignalStructure.CErrorStatus, sz=8)
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

    def cevent_init(self, ces, clearStatus=True):
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
        if clearStatus:
            self.control_write(ces,
                    genz.ComponentErrorSignalStructure.CEventStatus, sz=8)
        # Set CEventDetect - last, after other CEvent fields setup
        cevt_det = genz.CEventDetect(ces.CEventDetect, ces)
        cevt_det.field.UnableToCommAuthDest = 1
        cevt_det.field.ExcessiveRNRNAK = 1
        cevt_det.field.CompThermShutdown = 1
        # Revisit: other events
        ces.CEventDetect = cevt_det.val
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.CEventDetect, sz=8)

    def ievent_init(self, ces, newPeerComp=False, clearStatus=True):
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
        if clearStatus:
            self.control_write(ces,
                    genz.ComponentErrorSignalStructure.IEventStatus, sz=8)
        # Set IEventDetect - last, after other IEvent fields setup
        ievt_det = genz.IEventDetect(ces.IEventDetect, ces)
        ievt_det.field.FullIfaceReset = 1
        ievt_det.field.WarmIfaceReset = 1
        ievt_det.field.NewPeerComp = newPeerComp
        ievt_det.field.ExceededTransientErrThresh = 1
        ievt_det.field.IfacePerfDegradation = 1
        ces.IEventDetect = ievt_det.val
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.IEventDetect, sz=8)

    def ievent_update(self, newPeerComp=False):
        if self.ces_dir is None:
            return
        if self.cstate is not CState.CUp:
            return
        ces_file = self.ces_dir / 'component_error_and_signal_event'
        with ces_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            ces = self.map.fileToStruct('component_error_and_signal_event',
                                        data, fd=f.fileno(),
                                        verbosity=self.verbosity)
            if ces.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
            self.ievent_init(ces, newPeerComp=newPeerComp)
        # end with

    def clear_cerror_status(self, bitNum):
        ces_file = self.ces_dir / 'component_error_and_signal_event'
        with ces_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            ces = self.map.fileToStruct('component_error_and_signal_event',
                                        data, fd=f.fileno(),
                                        verbosity=self.verbosity)
            if ces.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
            genz = zephyr_conf.genz
            cerror_status = genz.CErrorStatus(ces.CErrorStatus, ces)
            ces.CErrorStatus = (1 << bitNum)  # bits are RW1CS
            log.debug(f'{self}: writing CErrorStatus={ces.CErrorStatus:#x}, was {cerror_status.val:#x}')
            self.control_write(ces, genz.ComponentErrorSignalStructure.CErrorStatus,
                               sz=8)
        # end with

    def clear_cevent_status(self, bitNum):
        ces_file = self.ces_dir / 'component_error_and_signal_event'
        with ces_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            ces = self.map.fileToStruct('component_error_and_signal_event',
                                        data, fd=f.fileno(),
                                        verbosity=self.verbosity)
            if ces.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
            genz = zephyr_conf.genz
            cevent_status = genz.CEventStatus(ces.CEventStatus, ces)
            ces.CEventStatus = (1 << bitNum)  # bits are RW1CS
            log.debug(f'{self}: writing CEventStatus={ces.CEventStatus:#x}, was {cevent_status.val:#x}')
            self.control_write(ces, genz.ComponentErrorSignalStructure.CEventStatus,
                               sz=8)
        # end with

    def clear_ievent_status(self, bitNum):
        ces_file = self.ces_dir / 'component_error_and_signal_event'
        with ces_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            ces = self.map.fileToStruct('component_error_and_signal_event',
                                        data, fd=f.fileno(),
                                        verbosity=self.verbosity)
            if ces.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
            genz = zephyr_conf.genz
            ievent_status = genz.IEventStatus(ces.IEventStatus, ces)
            ces.IEventStatus = (1 << bitNum)  # bits are RW1CS
            log.debug(f'{self}: writing IEventStatus={ces.IEventStatus:#x}, was {ievent_status.val:#x}')
            self.control_write(ces, genz.ComponentErrorSignalStructure.IEventStatus,
                               sz=8)
        # end with

    def pfm_uep_init(self, ces, pfm, valid=True):
        genz = zephyr_conf.genz
        if pfm is None or self is pfm:
            valid = False
        # Set MV/MgmtVC/Iface0
        pfm_rts = self.fab.get_routes(self, pfm)
        if len(pfm_rts) == 0:
            valid = False
        ces.MgmtVC0 = 0 # Revisit: VC should come from route
        ces.MgmtIface0 = pfm_rts[0][0].egress_iface.num if valid else 0
        ces.MV0 = int(valid)
        pfmUEPMask = (0x01 if valid else 0) # use MgmtVC/Iface0
        for i in range(0, len(pfm_rts) if valid else 1):
            if not valid or pfm_rts[i][0].egress_iface.num != ces.MgmtIface0:
                # an HA route using a different egress_iface
                ces.MgmtVC1 = 0 # Revisit: VC should come from route
                ces.MgmtIface1 = pfm_rts[i][0].egress_iface.num if valid else 0
                ces.MV1 = int(valid)
                pfmUEPMask |= (0x2 if valid else 0) # also use MgmtVC/Iface1
                break
            # end if
        # end for
        # write MgmtVC/IFace 0, 1, and (unused) 2
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.MV0, sz=8)
        # Set PFM UEP Mask
        ces.PFMUEPMask = pfmUEPMask
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.PMUEPMask, sz=8)

    def pfm_uep_update(self, pfm, valid=True):
        if self.ces_dir is None:
            return
        ces_file = self.ces_dir / 'component_error_and_signal_event'
        with ces_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            ces = self.map.fileToStruct('component_error_and_signal_event',
                                        data, fd=f.fileno(),
                                        verbosity=self.verbosity)
            if ces.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
            self.pfm_uep_init(ces, pfm, valid=valid)

    def sfm_uep_init(self, ces, sfm, valid=True):
        genz = zephyr_conf.genz
        if sfm is None or self is sfm:
            valid = False
        # Set MV/MgmtVC/Iface3
        sfm_rts = self.fab.get_routes(self, sfm)
        if len(sfm_rts) == 0:
            valid = False
        ces.MgmtVC3 = 0 # Revisit: VC should come from route
        ces.MgmtIface3 = sfm_rts[0][0].egress_iface.num if valid else 0
        ces.MV3 = int(valid)
        sfmUEPMask = (0x08 if valid else 0) # use MgmtVC/Iface3
        for i in range(0, len(sfm_rts) if valid else 1):
            if not valid or sfm_rts[i][0].egress_iface.num != ces.MgmtIface3:
                # an HA route using a different egress_iface
                ces.MgmtVC4 = 0 # Revisit: VC should come from route
                ces.MgmtIface4 = sfm_rts[i][0].egress_iface.num if valid else 0
                ces.MV4 = int(valid)
                sfmUEPMask |= (0x10 if valid else 0) # also use MgmtVC/Iface4
                break
            # end if
        # end for
        # write MgmtVC/IFace 3, 4, and (unused) 5
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.MV3, sz=8)
        # Set SFM UEP Mask
        ces.SFMUEPMask = sfmUEPMask
        self.control_write(ces,
                    genz.ComponentErrorSignalStructure.PMUEPMask, sz=8)

    def sfm_uep_update(self, sfm, valid=True):
        if self.ces_dir is None:
            return
        ces_file = self.ces_dir / 'component_error_and_signal_event'
        with ces_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            ces = self.map.fileToStruct('component_error_and_signal_event',
                                        data, fd=f.fileno(),
                                        verbosity=self.verbosity)
            if ces.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
            self.sfm_uep_init(ces, sfm, valid=valid)

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
            if ces.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
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
            self.pfm_uep_init(ces, self.fab.pfm)
        # end with

    def switch_init(self, core) -> None:
        genz = zephyr_conf.genz
        switch_file = self.switch_dir / 'component_switch'
        with switch_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            switch = self.map.fileToStruct('component_switch', data, fd=f.fileno(),
                                           verbosity=self.verbosity)
            if switch.all_ones_type_vers_size():
                raise AllOnesData('switch structure returned all-ones data')
            log.debug('{}: {}'.format(self.gcid, switch))
            # Revisit: write MV/MGMT VC/MGMT Iface ID
            # Revisit: write MCPRTEnb, MSMCPRTEnb, Default MC Pkt Relay
            # Enable Packet Relay
            sw_op_ctl = genz.SwitchOpCTL(switch.SwitchOpCTL, core, check=True)
            sw_op_ctl.field.PktRelayEnb = 1
            switch.SwitchOpCTL = sw_op_ctl.val
            self.control_write(
                switch, genz.ComponentSwitchStructure.SwitchCAP1Control, sz=8)
        # end with

    def rsp_pte_update(self, chunk: 'ChunkTuple', zaddr: int, ps: int,
                       valid: int = 1, baseAddr: int = 0) -> None:
        if self.rsp_pg_dir is None:
            return
        if self.max_data == 0:
            log.warning(f'{self}: component has Rsp Page Grid but MaxData==0')
            return
        rsp_pte_table_file = self.rsp_pte_table_dir / 'pte_table'
        with rsp_pte_table_file.open(mode='rb+') as f:
            pte_table = self.rsp_pte_table
            pte_table.set_fd(f)
            ps_bytes = 1 << ps
            min_pte = (zaddr - baseAddr) // ps_bytes
            max_pte = min_pte + ceil(chunk.length / ps_bytes)
            local_addr = chunk.start # need not be page-aligned
            for i in range(min_pte, max_pte):
                pte_table[i].V = valid
                pte_table[i].RORKey = chunk.ro_rkey if valid else NO_ACCESS_RKEY.val
                pte_table[i].RWRKey = chunk.rw_rkey if valid else NO_ACCESS_RKEY.val
                pte_table[i].ADDR = local_addr
                # Revisit: add PA/CCE/CE/WPE/PSE/LPE/IE/PFE/RKMGR/PASID/RK_MGR
                self.control_write(pte_table, pte_table.element.V,
                                   off=pte_table.element.Size*i,
                                   sz=pte_table.element.Size)
                local_addr += ps_bytes # Revisit: alignment
            # end for
        # end with

    def caccess_update(self, chunk: 'ChunkTuple',
                       valid: int = 1, baseAddr: int = 0) -> None:
        # Revisit: only 1 c_access structure supported
        if self.caccess_dir is None or self.caccess_rkey_dir is None:
            return
        ps = self.caccess_ps
        caccess_rkey_file = self.caccess_rkey_dir / 'c_access_r_key'
        with caccess_rkey_file.open(mode='rb+') as f:
            caccess_rkey = self.caccess_rkey
            caccess_rkey.set_fd(f)
            ps_bytes = 1 << ps
            min_pte = (chunk.start - baseAddr) // ps_bytes
            max_pte = min_pte + ceil(chunk.length / ps_bytes)
            for i in range(min_pte, max_pte):
                caccess_rkey[i].RORKey = chunk.ro_rkey if valid else NO_ACCESS_RKEY.val
                caccess_rkey[i].RWRKey = chunk.rw_rkey if valid else NO_ACCESS_RKEY.val
                self.control_write(caccess_rkey, caccess_rkey.element.RORKey,
                                   off=caccess_rkey.element.Size*i,
                                   sz=caccess_rkey.element.Size)
            # end for
        # end with

    def peer_attr_init(self, readOnly=False):
        if self.peer_attr_dir is None:
            return
        pa = self.pa_read()
        if len(pa) < 2: # must have at least 2 rows
            return
        if not readOnly:
            self.pa_write(0, 0) # LL
            self.pa_write(1, 1) # NLL

    def rsp_page_grid_init(self, core, readOnly=False):
        if self.rsp_pg_dir is None:
            return
        if self.max_data == 0:
            log.warning(f'{self}: component has Rsp Page Grid but MaxData==0')
            return
        # Revisit: return if rsp_pg should be host managed
        rsp_pg_file = self.rsp_pg_dir / 'component_page_grid'
        with rsp_pg_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            pg = self.map.fileToStruct('component_page_grid', data,
                                       fd=f.fileno(),
                                       verbosity=self.verbosity)
            if pg.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: component page grid all-ones data')
            log.debug(f'{self}: {pg}')
            # Revisit: verify the PG-PTE-UUID
        # end with
        # Cover all of data space using 1 page grid.
        # The page size is chosen such that all of data space can
        # be mapped twice. This is used during RKey & zaddr transitions.
        # Any additional page grids will be allocated dynamically for creating
        # interleave groups.
        self.pte_cnt = pg.PTETableSz
        ps = max(ceil_log2(2 * self.max_data / self.pte_cnt), 20) # min ps for interleaving
        self.rsp_page_grid_ps = ps
        rsp_pg_table_file = self.rsp_pg_table_dir / 'pg_table'
        with rsp_pg_table_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            pg_table = self.map.fileToStruct('pg_table', data,
                                             path=rsp_pg_table_file,
                                             fd=f.fileno(), parent=pg,
                                             verbosity=self.verbosity)
            log.debug('{self}: {pg_table}')
            if not readOnly:
                # Responder pages start at zaddr 0 in PG0
                pg_table[0].PGBaseAddr = 0
                pg_table[0].PageSz = ps
                pg_table[0].RES = 0
                pg_table[0].PageCount = self.pte_cnt
                pg_table[0].BasePTEIdx = 0
                # All other PGs are initially disabled
                for i in range(1, pg.PGTableSz):
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
            log.debug('{self}: {pte_table}')
            self.rsp_pte_table = pte_table # for rsp_pte_update()
            if not readOnly:
                for i in range(0, self.pte_cnt):
                    pte_table[i].V = 0
                    pte_table[i].RORKey = NO_ACCESS_RKEY.val
                    pte_table[i].RWRKey = NO_ACCESS_RKEY.val
                    pte_table[i].ADDR = i * (1 << ps)
                for i in range(0, pg.PTETableSz):
                    self.control_write(pte_table, pte_table.element.V,
                                       off=pte_table.element.Size*i,
                                       sz=pte_table.element.Size)
        # end with

    def caccess_rkey_init(self, readOnly=False):
        genz = zephyr_conf.genz
        if self.caccess_dir is None or self.caccess_rkey_dir is None:
            return
        caccess_file = self.caccess_dir / 'component_c_access'
        with caccess_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            caccess = self.map.fileToStruct('component_c_access', data,
                                            fd=f.fileno(),
                                            verbosity=self.verbosity)
            if caccess.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: component c_access all-ones data')
            log.debug(f'{self}: {caccess}')
        # end with
        self.caccess_table_sz = caccess.CAccessTableSz
        cpage_sz = genz.CPageSz(caccess.CPageSz, caccess)
        self.caccess_ps = cpage_sz.ps()
        caccess_rkey_file = self.caccess_rkey_dir / 'c_access_r_key'
        with caccess_rkey_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            caccess_rkey = self.map.fileToStruct('c_access_r_key', data,
                                                 path=caccess_rkey_file,
                                                 fd=f.fileno(), parent=caccess,
                                                 verbosity=self.verbosity)
            log.debug('{self}: {caccess_rkey}')
            self.caccess_rkey = caccess_rkey # for caccess_update()
            if not readOnly:
                for i in range(0, self.caccess_table_sz):
                    caccess_rkey[i].RORKey = NO_ACCESS_RKEY.val
                    caccess_rkey[i].RWRKey = NO_ACCESS_RKEY.val
                    self.control_write(caccess_rkey, caccess_rkey.element.RORKey,
                                       off=caccess_rkey.element.Size*i,
                                       sz=caccess_rkey.element.Size)
                # end for
            # end if
        # end with
        # set CAccessCTL.RKeyEnb
        with caccess_file.open(mode='rb+') as f:
            caccess.set_fd(f)
            ctl = genz.CAccessCTL(caccess.CAccessCTL, caccess)
            ctl.RKeyEnb = 1
            caccess.CAccessCTL = ctl.val
            # Revisit: orthus cannot do 1-byte write of CAccessCTL
            self.control_write(caccess,
                               genz.ComponentCAccessStructure.CPageSz, sz=8)

    def comp_dest_read(self, prefix='control', haveCore=True):
        if self.comp_dest is not None:
            return self.comp_dest
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        comp_dest_file = self.comp_dest_dir / 'component_destination_table'
        with comp_dest_file.open(mode='rb') as f:
            data = bytearray(f.read())
            comp_dest = self.map.fileToStruct(
                'component_destination_table',
                data, fd=f.fileno(), verbosity=self.verbosity)
            if comp_dest.all_ones_type_vers_size():
                raise AllOnesData('comp dest structure returned all-ones data')
        # end with
        if haveCore:
            self.comp_dest = comp_dest
            self.core.comp_dest = comp_dest # Revisit: two copies
            self.core.comp_dest.HCS = self.route_control_read(prefix=prefix)
        return comp_dest

    def component_pa_read(self, prefix='control', haveCore=True):
        if self.component_pa is not None or self.component_pa_dir is None:
            return self.component_pa
        component_pa_file = self.component_pa_dir / 'component_pa'
        with component_pa_file.open(mode='rb') as f:
            data = bytearray(f.read())
            component_pa = self.map.fileToStruct(
                'component_pa',
                data, fd=f.fileno(), verbosity=self.verbosity)
            if component_pa.all_ones_type_vers_size():
                raise AllOnesData('component_pa structure returned all-ones data')
        # end with
        if haveCore:
            self.component_pa = component_pa
            self.core.component_pa = component_pa # Revisit: two copies
            #self.core.comp_dest.HCS = self.route_control_read(prefix=prefix) # Revisit
        return component_pa

    def service_uuid_read(self, prefix='control'):
        if self.service_uuid_table is not None or self.service_uuid_dir is None:
            return self.service_uuid_table
        service_uuid_file = self.service_uuid_dir / 'service_uuid'
        with service_uuid_file.open(mode='rb') as f:
            data = bytearray(f.read())
            service_uuid = self.map.fileToStruct(
                'service_uuid',
                data, fd=f.fileno(), verbosity=self.verbosity)
            if service_uuid.all_ones_type_vers_size():
                raise AllOnesData('service_uuid structure returned all-ones data')
        # end with
        service_uuid_table_file = self.service_uuid_table_dir / 's_uuid'
        with service_uuid_table_file.open(mode='rb') as f:
            data = bytearray(f.read())
            service_uuid_table = self.map.fileToStruct(
                's_uuid', data,
                parent=service_uuid, fd=f.fileno(), verbosity=self.verbosity)
        # end with
        self.service_uuid_table = service_uuid_table
        return service_uuid_table

    def precision_time_read(self, prefix='control'):
        if self.pt is not None or self.precision_time_dir is None:
            return self.pt
        precision_time_file = self.precision_time_dir / 'component_precision_time'
        with precision_time_file.open(mode='rb') as f:
            data = bytearray(f.read())
            precision_time = self.map.fileToStruct(
                'component_precision_time',
                data, fd=f.fileno(), verbosity=self.verbosity)
            if precision_time.all_ones_type_vers_size():
                raise AllOnesData('precision_time structure returned all-ones data')
        # end with
        self.pt = precision_time
        return precision_time

    def precision_time_write(self, pt):
        pass

    # returns route_control.HCS
    def route_control_read(self, prefix='control'):
        genz = zephyr_conf.genz
        # route control can be found either in comp_dest_dir or switch_dir
        if self.comp_dest_dir is not None:
            parent_dir = self.comp_dest_dir
        elif self.switch_dir is not None:
            parent_dir = self.switch_dir
        else:
            parent_dir = None
        try:  # Revisit: route control is required, but missing in some HW
            rc_dir = list(parent_dir.glob('route_control@*'))[0]
        except (AttributeError, IndexError):
            rc_dir = None
        if rc_dir is not None:
            rc_path = rc_dir / 'route_control'
            with rc_path.open(mode='rb') as f:
                data = bytearray(f.read())
                rc = self.map.fileToStruct('route_control', data,
                                parent=self.core.sw, core=self.core,
                                fd=f.fileno(), verbosity=self.verbosity)
                self.core.route_control = rc
                cap1 = genz.RCCAP1(rc.RCCAP1, rc, check=True)
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
            if self.core.sw.all_ones_type_vers_size():
                raise AllOnesData('switch structure returned all-ones data')
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

    def rkd_write(self, rkd: 'RKD', enable=True):
        if self.rkd_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        rkd_file = self.rkd_dir / 'component_rkd'
        with rkd_file.open(mode='rb+', buffering=0) as f:
            if self.rkd is None:
                data = bytearray(f.read())
                self.rkd = self.map.fileToStruct('component_rkd', data, path=rkd_file,
                                    core=self.core, parent=self.core,
                                    fd=f.fileno(), verbosity=self.verbosity)
            else:
                self.rkd.set_fd(f)
            row = self.rkd.assign_rkd(rkd.rkd, enable)
            self.control_write(self.rkd, self.rkd.AuthArray,
                               off=self.rkd.embeddedArray.cs_offset(row), sz=8)
        # end with

    def ssdt_size(self, prefix='control', haveCore=True):
        if self._ssdt_sz is not None:
            return self._ssdt_sz
        comp_dest = self.comp_dest_read(prefix=prefix, haveCore=haveCore)
        if comp_dest.SSDTPTR == 0:
            self._ssdt_sz = (0, 0)
        else:
            rows = comp_dest.SSDTSize
            cols = comp_dest.MaxRoutes
            self._ssdt_sz = (rows, cols)
        log.debug(f'{self.gcid}: ssdt_sz={self._ssdt_sz}')
        return self._ssdt_sz

    def compute_mhc_hc_row(self, row, info: 'RouteInfo',
                           cid: int, rt: int, hc: int, valid: int):
        elem = row[rt]
        curV = elem.V
        curHC = elem.HC if curV else MAX_HC
        if valid:
            newHC = min(hc, curHC)
            newV = 1
            cur_min = min(row, key=lambda x: x.HC if x.V else MAX_HC)
            curMHC = cur_min.HC if cur_min.V else MAX_HC
            newMHC = min(curMHC, newHC)
        else:
            newHC = info.min_hc()  # None if no remaining info items
            newV = 0 if newHC is None else 1
            curMHC = row[0].MHC
            new_min = min((row[i] for i in range(len(row))
                          if i != rt), key=lambda x: x.HC if x.V else MAX_HC)
            newMHC = min(new_min.HC if new_min.V else MAX_HC,
                         newHC if newHC is not None else MAX_HC)
            newMHC = 0 if newMHC == MAX_HC else newMHC
            newHC = 0 if newHC is None else newHC
        wr0 = newMHC != curMHC and rt != 0
        wrN = newV != curV or newHC != curHC or (newMHC != curMHC and rt == 0)
        return (newMHC, newHC, newV, wr0, wrN)

    def compute_mhc_hc(self, cid: int, rt: int, hc: int, valid: int):
        if self.ssdt is None:
            return (hc, hc, valid, rt != 0, False)
        row = self.ssdt[cid]
        info = self.route_info[cid][rt]
        return self.compute_mhc_hc_row(row, info, cid, rt, hc, valid)

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

    def fixup_ssdt(self, routes, pfm) -> None:
        self.ssdt_read() # required before set_ssdt()
        # must do all routes even though they all setup the SSDT exactly the same
        # (since they all use the same DR interface) because we must set the
        # route_info counter correctly as well as each route's rt_num
        for rt in routes:
            # use first route elem to correctly set SSDT HC & MHC and update rt_num
            elem = rt[0]
            elem.set_ssdt(pfm, updateRtNum=True)

    def ssap_size(self, prefix='control', haveCore=True) -> int:
        if self._ssap_sz is not None:
            return self._ssap_sz
        comp_pa = self.component_pa_read(prefix=prefix, haveCore=haveCore)
        if comp_pa is None or comp_pa.SSAPPTR == 0:
            self._ssap_sz = 0
        else:
            self._ssap_sz = comp_pa.sz_0_special(comp_pa.SSAPSz, 12)
        log.debug(f'{self.gcid}: ssap_sz={self._ssap_sz}')
        return self._ssap_sz

    def ssap_read(self):
        if self.ssap is not None or self.ssap_dir is None:
            return self.ssap
        # Revisit: avoid open/close (via "with") on every read?
        ssap_file = self.ssap_dir / 'ssap'
        with ssap_file.open(mode='rb+', buffering=0) as f:
            data = bytearray(f.read())
            self.ssap = self.map.fileToStruct('ssap', data, path=ssap_file,
                                    core=self.core, parent=self.comp_pa,
                                    fd=f.fileno(), verbosity=self.verbosity)
        return self.ssap

    def ssap_write(self, cid, akey: AKey = None, acreq=None, acrsp=None, paIdx=None):
        if self.ssap_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        ssap_file = self.ssap_dir / 'ssap'
        with ssap_file.open(mode='rb+', buffering=0) as f:
            if self.ssap is None:
                data = bytearray(f.read())
                self.ssap = self.map.fileToStruct('ssap', data, path=ssap_file,
                                    core=self.core, parent=self.component_pa,
                                    fd=f.fileno(), verbosity=self.verbosity)
            else:
                self.ssap.set_fd(f)
            sz = ctypes.sizeof(self.ssap.element)
            elem = None
            if self.ssap.pa_idx_sz > 0:
                elem = self.ssap.element.PAIdx
                if paIdx is not None:
                    self.ssap[cid].PAIdx = paIdx
            if not self.ssap.wc_akey:
                elem = self.ssap.element.AKey if elem is None else elem
                if akey is not None:
                    self.ssap[cid].AKey = akey
            if not self.ssap.wc_acreq:
                elem = self.ssap.element.ACREQ if elem is None else elem
                if acreq is not None:
                    self.ssap[cid].ACREQ = acreq
            if not self.ssap.wc_acrsp:
                elem = self.ssap.element.ACRSP if elem is None else elem
                if acrsp is not None:
                    self.ssap[cid].ACRSP = acrsp
            if elem is not None:
                self.control_write(self.ssap, elem,
                                   off=self.ssap.cs_offset(cid), sz=sz)
        # end with

    def pa_size(self, prefix='control', haveCore=True):
        if self._pa_sz is not None:
            return self._pa_sz
        comp_pa = self.component_pa_read(prefix=prefix, haveCore=haveCore)
        if comp_pa is None or comp_pa.PAPTR == 0:
            self._pa_sz = 0
        else:
            self._pa_sz = comp_pa.sz_0_special(comp_pa.PASize, 16)
        log.debug(f'{self.gcid}: pa_sz={self._pa_sz}')
        return self._pa_sz

    def pa_read(self):
        if self.pa is not None or self.peer_attr_dir is None:
            return self.pa
        # Revisit: avoid open/close (via "with") on every read?
        pa_file = self.peer_attr_dir / 'pa'
        with pa_file.open(mode='rb+', buffering=0) as f:
            data = bytearray(f.read())
            self.pa = self.map.fileToStruct('pa', data, path=pa_file,
                                    core=self.core, parent=self.component_pa,
                                    fd=f.fileno(), verbosity=self.verbosity)
        return self.pa

    def pa_write(self, paIdx, latDom):
        if self.peer_attr_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        pa_file = self.peer_attr_dir / 'pa'
        with pa_file.open(mode='rb+', buffering=0) as f:
            if self.pa is None:
                data = bytearray(f.read())
                self.pa = self.map.fileToStruct('pa', data, path=pa_file,
                                    core=self.core, parent=self.component_pa,
                                    fd=f.fileno(), verbosity=self.verbosity)
            else:
                self.pa.set_fd(f)
            sz = ctypes.sizeof(self.pa.element)
            self.pa[paIdx].LatencyDomain = latDom
            # Revisit: support other PeerAttr fields
            self.control_write(self.pa, self.pa.element.OpCodeSetTableID,
                               off=self.pa.cs_offset(paIdx), sz=sz)
        # end with

    @property
    def akey_sup(self, wildOk: bool = False) -> bool:
        '''Component has AKey support. Requires a ComponentPA structure
        and either a non-zero SSAPPTR or (if @wildOk) WildcardAKeySup.
        '''
        genz = zephyr_conf.genz
        comp_pa = self.component_pa_read()
        if comp_pa is None:
            return False
        cap1 = genz.PACAP1(comp_pa.PACAP1, comp_pa)
        return comp_pa.SSAPPTR != 0 or (cap1.WildcardAKeySup and wildOk)

    def enable_akeys(self, enb=True):
        genz = zephyr_conf.genz
        comp_pa = self.component_pa_read()
        if comp_pa is None:
            return
        cap1ctl = genz.PACAP1Control(comp_pa.PACAP1Control, comp_pa)
        cap1ctl.AKeyEnb = enb
        comp_pa.PACAP1Control = cap1ctl.val
        component_pa_file = self.component_pa_dir / 'component_pa'
        with component_pa_file.open(mode='rb+', buffering=0) as f:
            comp_pa.set_fd(f)
            self.control_write(comp_pa, genz.ComponentPAStructure.PACAP1Control, sz=4)

    @property
    def gtc_sup(self) -> bool:
        '''Component has Precision Time GTC support.
        Requires a ComponentPrecisionTime structure and PTGTCSup.
        '''
        genz = zephyr_conf.genz
        pt = self.precision_time_read()
        if pt is None:
            return False
        cap1 = genz.PTCAP1(pt.PTCAP1, pt)
        return cap1.PTGTCSup

    @property
    def pt_req_sup(self) -> bool:
        '''Component has Precision Time Requester support.
        Requires a ComponentPrecisionTime structure and PTReqSup.
        '''
        genz = zephyr_conf.genz
        pt = self.precision_time_read()
        if pt is None:
            return False
        cap1 = genz.PTCAP1(pt.PTCAP1, pt)
        return cap1.PTReqSup

    @property
    def pt_rsp_sup(self) -> bool:
        '''Component has Precision Time Responder support.
        Requires a ComponentPrecisionTime structure and PTRspSup.
        '''
        genz = zephyr_conf.genz
        pt = self.precision_time_read()
        if pt is None:
            return False
        cap1 = genz.PTCAP1(pt.PTCAP1, pt)
        return cap1.PTRspSup

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

    def update_ssap_dir(self, prefix='control'):
        if self.component_pa_dir is None:
            return
        self.component_pa_dir = list((self.path / prefix).glob(
            'component_pa@*'))[0]
        if self.ssap_dir is None:
            return
        self.ssap_dir = list(self.component_pa_dir.glob('ssap@*'))[0]
        log.debug('new ssap_dir = {}'.format(self.ssap_dir))

    def update_peer_attr_dir(self, prefix='control'):
        if self.component_pa_dir is None:
            return
        self.component_pa_dir = list((self.path / prefix).glob(
            'component_pa@*'))[0]
        if self.peer_attr_dir is None:
            return
        self.peer_attr_dir = list(self.component_pa_dir.glob('pa@*'))[0]
        log.debug('new peer_attr_dir = {}'.format(self.peer_attr_dir))

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

    def update_rkd_dir(self, prefix='control'):
        if self.rkd_dir is None:
            return
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        self.rkd_dir = list(self.comp_dest_dir.glob('component_rkd@*'))[0]
        log.debug('new rkd_dir = {}'.format(self.rkd_dir))

    def update_rsp_page_grid_dir(self, prefix='control'):
        if self.rsp_pg_dir is None:
            return
        self.rsp_pg_dir = self.find_rsp_page_grid_path(prefix)
        self.rsp_pg_table_dir = list(self.rsp_pg_dir.glob('pg_table@*'))[0]
        self.rsp_pte_table_dir = list(self.rsp_pg_dir.glob('pte_table@*'))[0]
        log.debug('new rsp_pg_dir = {}'.format(self.rsp_pg_dir))

    def update_caccess_dir(self, prefix='control'):
        # Revisit: only 1 c_access structure supported
        if self.caccess_dir is None or self.caccess_rkey_dir is None:
            return
        self.caccess_dir = list((self.path / prefix / 'component_c_access').glob(
            'component_c_access0@*'))[0]
        self.caccess_rkey_dir = list(self.caccess_dir.glob(
            'c_access_r_key@*'))[0]
        log.debug('new caccess_dir = {}'.format(self.caccess_dir))

    def update_service_uuid_dir(self, prefix='control'):
        if self.service_uuid_dir is None or self.service_uuid_table_dir is None:
            return
        self.service_uuid_dir = list((self.path / prefix).glob(
            'service_uuid@*'))[0]
        self.service_uuid_table_dir = list(self.service_uuid_dir.glob(
            's_uuid@*'))[0]
        log.debug('new service_uuid_dir = {}'.format(self.service_uuid_dir))

    def update_precision_time_dir(self, prefix='control'):
        # Revisit: only 1 precision_time structure supported
        if self.precision_time_dir is None:
            return
        self.precision_time_dir = list((self.path / prefix / 'component_precision_time').glob(
                'component_precision_time0@*'))[0]
        log.debug('new precision_time_dir = {}'.format(self.precision_time_dir))

    def update_path(self):
        log.debug('current path: {}'.format(self.path))
        self.path = self.fab.make_path(self.gcid)
        log.debug('new path: {}'.format(self.path))
        self.update_ssdt_dir()
        self.update_ssap_dir()
        self.update_peer_attr_dir()
        self.update_rit_dir()
        self.update_req_vcat_dir()
        self.update_rsp_vcat_dir()
        self.update_switch_dir()
        self.update_ces_dir()
        self.update_rkd_dir()
        self.update_opcode_set_dir()
        self.update_rsp_page_grid_dir()
        self.update_caccess_dir()
        self.update_service_uuid_dir()
        self.update_precision_time_dir()
        for iface in self.interfaces:
            iface.update_path(prefix='control')

    @property
    def rit_only(self):
        return self.ssdt_dir is None

    @property
    def has_switch(self):
        return self.switch_dir is not None

    @property
    def is_requester(self) -> bool:
        return self.core.MaxREQSuppReqs > 0

    @property
    def is_responder(self) -> bool:
        return self.core.MaxRSPSuppReqs > 0

    def acreqrsp(self, other: 'Component'):
        '''Use ACREQ/ACRSP to allow data traffic between:
        1. Components that have not been partitioned
        2. Components that share the same partition (and therefore AKey)
        3. Everybody, if --no-akeys
        No other combinations are allowed. Because Control pkts are not
        impacted by ACREQ/ACRSP, PFM/SFM are not special here.
        '''
        genz = zephyr_conf.genz
        no_akeys = zephyr_conf.args.no_akeys
        same_part = self.partition == other.partition
        acreq = (genz.ACREQRSP.FullAccess if no_akeys else
                 genz.ACREQRSP.RKeyRequired if self.is_requester and same_part
                 else genz.ACREQRSP.NoAccess)
        acrsp = (genz.ACREQRSP.FullAccess if no_akeys else
                 genz.ACREQRSP.RKeyRequired if self.is_responder and same_part
                 else genz.ACREQRSP.NoAccess)
        return (acreq, acrsp)

    def explore_interface(self, iface, pfm, ingress_iface,
                          send=False, reclaim=False):
        '''Explore one interface, @iface, on this component and initialize
        the peer Component connected to it. Recurse if the component has a
        switch.
        '''
        zargs = zephyr_conf.args
        iface.update_peer_info()
        # get peer CState
        peer_cstate = iface.peer_cstate
        peer_comp = iface.peer_comp
        if peer_comp:
            peer_comp.cstate = peer_cstate
        msg = '{}: exploring interface{}, peer cstate={!s}, '.format(
            iface, iface.num, peer_cstate)
        if iface.peer_inband_disabled:
            msg += 'peer inband management disabled - ignoring peer'
            log.info(msg)
            return
        elif iface.boundary_interface:
            msg += 'boundary interface - ignoring peer'
            log.info(msg)
            # Revisit: contact foreign FM
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
        reset_required = False
        if peer_cstate is CState.CUp:
            peer_c_reset_only = False
            # get PeerGCID
            peer_gcid = iface.peer_gcid
            msg += 'peer gcid={}'.format(peer_gcid)
            if peer_gcid is None:
                msg += ' peer is C-Up but GCID not valid - ignoring peer'
                log.warning(msg)
                return
            if peer_gcid in self.fab.comp_gcids: # another path?
                comp = self.fab.comp_gcids[peer_gcid]
                peer_iface = comp.interfaces[iface.peer_iface_num]
                iface.set_peer_iface(peer_iface)
                if peer_iface != iface.prev_peer_iface:  # different peer
                    self.fab.remove_link(iface, iface.prev_peer_iface)
                    # Revisit: send msg to SFM
                # bring peer iface to I-Up (if it isn't already)
                peer_istate, _ = peer_iface.iface_state()
                if peer_istate is not IState.IUp:
                    peer_iface.iface_init(no_akeys=zargs.no_akeys)
                nonce_valid = iface.do_nonce_exchange()
                if not nonce_valid:
                    iface.set_peer_iface(None)
                    msg += ' nonce mismatch'
                    log.warning(msg)
                    # Revisit: contact foreign FM
                    return
                added = self.fab.add_link(iface, peer_iface)
                # Revisit: use added to determine what to do
                msg += ' additional path to {}'.format(comp)
                log.info(msg)
                # new path might enable additional or shorter routes
                self.fab.recompute_routes(iface, peer_iface)
            elif reclaim:
                msg += ', reclaiming C-Up component'
                path = self.fab.make_path(peer_gcid)
                comp = Component(iface.peer_cclass, self.fab, self.map, path,
                                 self.mgr_uuid, br_gcid=self.br_gcid,
                                 netlink=self.nl, verbosity=self.verbosity)
                peer_iface = Interface(comp, iface.peer_iface_num, iface,
                                       usable=True)
                comp.found_cstate = peer_cstate
                iface.set_peer_iface(peer_iface)
                if peer_iface != iface.prev_peer_iface:  # different peer
                    self.fab.remove_link(iface, iface.prev_peer_iface)
                    # Revisit: send msg to SFM
                gcid = self.fab.assign_gcid(comp, proposed_gcid=peer_gcid,
                                            reclaim=reclaim)
                if gcid is None:
                    msg += ', gcid conflict, reset required'
                    log.warning(msg)
                    reset_required = True
                    peer_c_reset_only = True
                    routes = None
                else:
                    msg += ', retaining gcid={}'.format(gcid)
                    log.info(msg)
                if path.exists():
                    comp.remove_fab_comp(force=True)
                if not reset_required:
                    self.fab.add_link(iface, peer_iface)
                    routes = self.fab.setup_bidirectional_routing(
                        pfm, comp, write_to_ssdt=False)
                    pfm.ssap_write(comp.gcid.cid, self.fab.fm_akey, paIdx=0)
                    try:
                        comp.add_fab_comp(setup=True)
                    except Exception as e:
                        log.error(f'add_fab_comp(gcid={comp.gcid},tmp_gcid={comp.tmp_gcid},dr={comp.dr}) failed with exception {e}')
                        reset_required = True
                        peer_c_reset_only = True
                if not reset_required:
                    usable = comp.comp_init(pfm, ingress_iface=peer_iface,
                                            route=routes[1])
                    reset_required = not usable
                    if usable and comp.has_switch:  # if switch, recurse
                        comp.explore_interfaces(pfm, ingress_iface=peer_iface,
                                                reclaim=reclaim)
                if reset_required:
                    peer_cstate = comp.warm_reset(iface,
                                            peer_c_reset_only=peer_c_reset_only)
                    if peer_cstate is not CState.CCFG:
                        log.warning(f'unable to reset - ignoring component {comp} on {iface}')
                        if routes is not None:
                            self.fab.teardown_routing(pfm, comp, routes[0] + routes[1])
                        return
            else:
                msg += ' ignoring unknown component'
                log.warning(msg)
                return
            # end if peer_gcid
        # end if CUp
        if peer_cstate is CState.CCFG: # Note: not 'elif'
            from zephyr_route import DirectedRelay
            if peer_comp is None:
                dr = DirectedRelay(self, ingress_iface, iface) # temporary dr
                comp = Component(iface.peer_cclass, self.fab, self.map, dr.path,
                                 self.mgr_uuid, dr=dr, br_gcid=self.br_gcid,
                                 netlink=self.nl, verbosity=self.verbosity)
                peer_iface = Interface(comp, iface.peer_iface_num, iface)
                iface.set_peer_iface(peer_iface)
                if peer_iface != iface.prev_peer_iface:  # different peer
                    self.fab.remove_link(iface, iface.prev_peer_iface)
                    # Revisit: send msg to SFM
                # now that we have peer_iface, setup new DR that includes it
                dr = DirectedRelay(self, ingress_iface, iface, to_iface=peer_iface)
                comp.set_dr(dr)
                gcid = self.fab.assign_gcid(comp, reclaim=reclaim,
                                            cstate=peer_cstate)
                if gcid is None:
                    msg += 'no GCID available in pool - ignoring component'
                    log.warning(msg)
                    return
                op = 'add'
                msg += 'assigned gcid={}'.format(gcid)
                self.fab.add_link(iface, peer_iface)
            else: # have a known peer_comp
                comp = peer_comp
                peer_iface = iface.peer_iface
                dr = DirectedRelay(self, ingress_iface, iface, to_iface=peer_iface)
                comp.set_dr(dr)
                gcid = comp.gcid
                op = 'change'
                msg += 'reusing previously-assigned gcid={}'.format(gcid)
            if not reset_required:
                comp.found_cstate = peer_cstate
            # deal with "leftover" comp path from previous zephyr run
            path = self.fab.make_path(gcid)
            if path.exists():
                leftover = Component(iface.peer_cclass, self.fab, self.map,
                                     path, self.mgr_uuid,
                                     gcid=gcid, br_gcid=self.br_gcid,
                                     netlink=self.nl, verbosity=self.verbosity)
                leftover.remove_fab_comp(force=True)
                self.fab.remove_node(leftover)
                del self.fab.components[leftover.uuid]
            log.info(msg)
            routes = self.fab.setup_bidirectional_routing(
                pfm, comp, write_to_ssdt=False) # comp_init() will write SSDT
            pfm.ssap_write(comp.gcid.cid, self.fab.fm_akey, paIdx=0)
            try:
                comp.add_fab_dr_comp()
            except Exception as e:
                log.error(f'add_fab_dr_comp(gcid={comp.gcid}, dr_gcid={comp.dr.gcid}, dr_iface={comp.dr.egress_iface}) failed with exception {e}')
                self.fab.teardown_routing(pfm, comp, routes[0] + routes[1])
                return
            usable = comp.comp_init(pfm, prefix='dr', ingress_iface=peer_iface,
                                    route=routes[1])
            if send:
                js = comp.to_json(verbosity=1)
                self.fab.send_mgrs(['llamas'], 'mgr_topo', 'component', js,
                                   op=op, invertTypes=True)
            if usable and comp.has_switch:  # if switch, recurse
                comp.explore_interfaces(pfm, ingress_iface=peer_iface,
                                        send=send, reclaim=reclaim)
            elif not usable:
                log.warning(f'{comp} is not usable')
                self.fab.teardown_routing(pfm, comp, routes[0] + routes[1])
        # end if peer_cstate

    def explore_interfaces(self, pfm, ingress_iface=None, explore_ifaces=None,
                           send=False, reclaim=False):
        '''Explore all interfaces on this component, or just those passed
        in @explore_ifaces, skipping the @ingress_iface and any that are
        not usable.
        '''
        if explore_ifaces is None:
            # examine all interfaces (except ingress) & init those components
            zargs = zephyr_conf.args
            explore_ifaces = (reversed(self.interfaces) if zargs.reversed
                              else self.interfaces)
        for iface in explore_ifaces:
            if iface == ingress_iface:
                log.debug(f'{iface}: skipping ingress interface{iface.num}')
            elif iface.usable:
                try:
                    self.explore_interface(iface, pfm, ingress_iface,
                                           send=send, reclaim=reclaim)
                except AllOnesData as e:
                    log.warning(f'{iface}: interface{iface.num} config failed with exception "{e}" - marking unusable')
                    iface.usable = False
            else:
                log.info(f'{iface}: interface{iface.num} is not usable')

    def update_cstate(self, prefix='control', forceTimestamp=False):
        prev_cstate = self.cstate
        genz = zephyr_conf.genz
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            # Revisit: optimize this to avoid reading entire Core struct
            data = bytearray(f.read())
            core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                         verbosity=self.verbosity)
            cstatus = genz.CStatus(core.CStatus, core, check=True)
            self.cstate = CState(cstatus.field.CState)
            if forceTimestamp or (self.cstate != prev_cstate):
                self.fab.update_mod_timestamp(comp=self)

    def unreachable_comp(self, to, iface):
        log.warning(f'{self}: unreachable component {to} due to interface {iface} failure')


    def is_unreachable(self, fr: 'Component', bidirectional: bool = True) -> bool:
        '''Is this Component unreachable from Component @fr?
        Returns True if this Component is unusable or there are no routes
        from @fr to this Component, or, when @bidirectional is True, no routes
        from this Component back to @fr.
        '''
        return not self.usable or ((self is not fr and
                                    self.fab.routes.count_routes(fr, self) < 1) or
                                   (self is not fr and bidirectional and
                                    self.fab.routes.count_routes(self, fr) < 1))

    def warm_reset(self, iface, prefix='control', peer_c_reset_only=False):
        if not peer_c_reset_only:
            log.debug('attempting component warm reset of {}'.format(self))
            core_file = self.path / prefix / 'core@0x0/core'
            with core_file.open(mode='rb+') as f:
                genz = zephyr_conf.genz
                data = bytearray(f.read())
                core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                             verbosity=self.verbosity)
                try:
                    cctl = genz.CControl(core.CControl, core, check=True)
                except AllOnesData:
                    log.warning(f'{self}: CControl is all-ones')
                    return None
                cctl.ComponentReset = CReset.WarmReset
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

    def was_reset(self, peer_iface=None):
        '''Component was reset and is not operational until reconfigured'''
        self.usable = False
        fab = self.fab
        if peer_iface is None:
            peer_iface = self.nearest_iface_to(fab.pfm).peer_iface
        # mark all interfaces as unusable (and teardown all routes using them)
        log.info(f'{self} was reset - teardown all routes using it')
        for iface in self.interfaces:
            fab.iface_unusable(iface)
        # revert comp back to DR
        log.info(f'{self} revert to DR via {peer_iface}')
        dr_comp = peer_iface.comp
        from zephyr_route import DirectedRelay
        dr = DirectedRelay(dr_comp, None, peer_iface, to_iface=peer_iface.peer_iface)
        self.set_dr(dr)
        routes = fab.setup_bidirectional_routing(fab.pfm, self,
                            write_to_ssdt=False) # a later comp_init() will write SSDT
        try:
            self.add_fab_dr_comp()
        except Exception as e:
            log.error(f'add_fab_dr_comp(gcid={self.gcid}, dr_gcid={self.dr.gcid}, dr_iface={self.dr.egress_iface}) failed with exception {e}')
            fab.teardown_routing(fab.pfm, self, routes[0] + routes[1])

    def nearest_iface_to(self, to: 'Component'):
        rts = self.fab.get_routes(self, to)
        return rts[0][0].egress_iface

    def enable_sfm(self, sfm, prefix='control'):
        '''Enable @sfm as Secondary Fabric Manager of this component and
        setup bidirectional routing.
        '''
        zargs = zephyr_conf.args
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
        # Revisit: NLL paIdx
        acreq, acrsp = sfm.acreqrsp(self)
        sfm.ssap_write(self.gcid.cid, self.fab.fm_akey,
                       acreq=acreq, acrsp=acrsp, paIdx=0)
        acreq, acrsp = self.acreqrsp(sfm)
        self.ssap_write(sfm.gcid.cid, self.fab.fm_akey,
                        acreq=acreq, acrsp=acrsp, paIdx=0)
        routes = self.fab.setup_bidirectional_routing(sfm, self)
        self.sfm_uep_update(sfm)
        return routes # Revisit

    def disable_sfm(self, sfm, prefix='control'):
        '''Disable @sfm as Secondary Fabric Manager of this component and
        remove SFM routing.
        '''
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            genz = zephyr_conf.genz
            core = self.core
            core.set_fd(f)
            # Set Fabric Manager Transition bit (only on SFM)
            if self is sfm:
                cap1ctl = genz.CAP1Control(core.CAP1Control, core)
                cap1ctl.FabricMgrTransition = 1
                core.CAP1Control = cap1ctl.val
                self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
            # clear SFMCIDValid/SFMSIDValid
            cap2ctl = genz.CAP2Control(core.CAP2Control, core)
            cap2ctl.field.SFMCIDValid = 0
            cap2ctl.field.SFMSIDValid = 0
            core.CAP2Control = cap2ctl.val
            self.control_write(core, genz.CoreStructure.CAP2Control, sz=8)
            # clear SecondaryFabMgrRole, HostMgrMGRUUIDEnb (only on SFM)
            if self is sfm:
                cap1ctl.SecondaryFabMgrRole = 0
                cap1ctl.HostMgrMGRUUIDEnb = HostMgrUUID.Zero
                core.CAP1Control = cap1ctl.val
                self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
            # Clear Fabric Manager Transition bit
            if self is sfm:
                cap1ctl.FabricMgrTransition = 0
                core.CAP1Control = cap1ctl.val
                self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
        # end with
        self.sfm_uep_update(None, valid=False)
        # Revisit: remove SFM routes (when route refcounts are available)
        #routes = self.fab.setup_bidirectional_routing(sfm, self)
        # Revisit: disable fm_akey in sfm and self
        #return routes # Revisit

    def promote_sfm_to_pfm(self, sfm, pfm, prefix='control'):
        '''Promote @sfm to Primary Fabric Manager of this component and
        invalidate the previous SFM GCID (since it is now PFM).
        '''
        genz = zephyr_conf.genz
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            core = self.core
            core.set_fd(f)
            cap1ctl = genz.CAP1Control(core.CAP1Control, core)
            cap2ctl = genz.CAP2Control(core.CAP2Control, core)
            # Set Fabric Manager Transition bit (only on PFM/SFM)
            if self is pfm or self is sfm:
                cap1ctl.FabricMgrTransition = 1
                core.CAP1Control = cap1ctl.val
                self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
            # clear PrimaryFabMgrRole, HostMgrMGRUUIDEnb (only on PFM component)
            if self is pfm:
                cap1ctl.PrimaryFabMgrRole = 0
                cap1ctl.HostMgrMGRUUIDEnb = HostMgrUUID.Zero
                core.CAP1Control = cap1ctl.val
                self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
            # set SFM as new PFMSID/PFMCID (must be after PrimaryFabMgrRole = 0)
            # Revisit: subnets
            core.PFMCID = sfm.gcid.cid
            self.control_write(core, genz.CoreStructure.PMCID, sz=8)
            # set PrimaryFabMgrRole/clear SecondaryFabMgrRole (only on SFM)
            if self is sfm:
                cap1ctl.PrimaryFabMgrRole = 1
                cap1ctl.SecondaryFabMgrRole = 0
                core.CAP1Control = cap1ctl.val
                self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
            # clear SFMCIDValid/SFMSIDValid
            cap2ctl.field.SFMCIDValid = 0
            cap2ctl.field.SFMSIDValid = 0
            core.CAP2Control = cap2ctl.val
            self.control_write(core, genz.CoreStructure.CAP2Control, sz=8)
            # Clear Fabric Manager Transition bit
            if self is pfm or self is sfm:
                cap1ctl.FabricMgrTransition = 0
                core.CAP1Control = cap1ctl.val
                self.control_write(core, genz.CoreStructure.CAP1Control, sz=8)
        # end with
        # update UEP targets
        self.pfm_uep_update(sfm) # PFM UEPs target (former) SFM
        self.sfm_uep_update(None, valid=False) # no SFM UEPs
        # Revisit: remove PFM routes (when route refcounts are available)
        #routes = self.fab.setup_bidirectional_routing(sfm, self)
        #return routes # Revisit

    def precision_time_init(self, pt, req_iface: Interface, rsp_ifaces: List[Interface]):
        genz = zephyr_conf.genz
        zargs = zephyr_conf.args
        fab = self.fab
        gtc = fab.gtc
        self.pt = pt
        ctl = genz.PTCTL(pt.PTCTL, pt)
        cap1 = genz.PTCAP1(pt.PTCAP1, pt)
        pt.GTCCID = gtc.gcid.cid
        if 0 and self.gcid.sid != gtc.gcid.sid: # Revisit: subnets
            ctl.GTCSIDEnb = 1
            pt.GTCSID = gtc.gcid.sid
        else:
            ctl.GTCSIDEnb = 0
        if self is gtc:
            fab.PTDGranUnit = cap1.CompPTGranUnit
            fab.PTDGranularity = pt.CompPTGranularity
            ctl.PTGTCEnb = 1
        else:
            ctl.PTGTCEnb = 0
        if self.pt_rsp_sup and len(rsp_ifaces) > 0:
            ctl.PTRspEnb = 1
            for iface in rsp_ifaces:
                iface.update_precision_time_enb(1)
        else:
            ctl.PTRspEnb = 0
        if self.pt_req_sup and req_iface is not None:
            ctl.PTReqEnb = 1
            pt.PTRspCID = req_iface.peer_comp.gcid.cid
            if 0 and self.gcid.sid != req_iface.peer_comp.gcid.sid: # Revisit: subnets
                ctl.PTRspSIDEnb = 1
                pt.PTRspSID = req_iface.peer_comp.gcid.sid
            else:
                ctl.PTRspSIDEnb = 0
            pt.PTDIface = req_iface.num
            req_iface.update_precision_time_enb(1)
        else:
            ctl.PTReqEnb = 0
        ctl.PTDGranUnit = fab.PTDGranUnit
        pt.PTDGranularity = fab.PTDGranularity
        pt.PTRT = pt_ns_to_ptd_time(zargs.ptrt * 1e9, fab.PTDGranularity, fab.PTDGranUnit)
        # Revisit: add support for alternate PTRsp/PTDIface
        # Revisit: pt.TC, pt.LocalOffset
        self.control_write(pt,
                    genz.ComponentPrecisionTimeStructure.GTCCID, sz=8)
        self.control_write(pt,
                    genz.ComponentPrecisionTimeStructure.AltPTRspCID, sz=8)
        self.control_write(pt,
                    genz.ComponentPrecisionTimeStructure.PTRT, sz=8)
        if self is gtc:
            now = time.time_ns()
            pt.MasterTime = pt_ns_to_ptd_time(now, fab.PTDGranularity, fab.PTDGranUnit)
            self.control_write(pt,
                    genz.ComponentPrecisionTimeStructure.MasterTime, sz=8)
        pt.PTCTL = ctl.val
        # write enables in PTCTL last
        self.control_write(pt,
                           genz.ComponentPrecisionTimeStructure.PTCAP1, sz=4, off=4)

    def precision_time_enable(self, req_iface: Interface, rsp_ifaces: List[Interface]):
        if self.precision_time_dir is None:
            return
        if self.cstate is not CState.CUp:
            return
        precision_time_file = self.precision_time_dir / 'component_precision_time'
        with precision_time_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            pt = self.map.fileToStruct('component_precision_time',
                                       data, fd=f.fileno(), verbosity=self.verbosity)
            if pt.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: precision_time structure all-ones data')
            self.precision_time_init(pt, req_iface, rsp_ifaces)
        # end with

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

    def unreachable_comp(self, to, iface):
        super().unreachable_comp(to, iface)
        # notify llamas instance about unreachable resources
        fab = self.fab
        unreach = fab.resources.unreachable(self, to)
        endpoints = fab.mainapp.get_endpoints([self.cuuid_serial], None,
                                              'llamas', 'unreach_res')
        send_resource(unreach, endpoints)

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
                    self.update_ssap_dir()
                    self.update_peer_attr_dir()
                    self.update_rit_dir()
                    self.update_req_vcat_dir()
                    self.update_rsp_vcat_dir()
                    self.update_switch_dir()
                    self.update_ces_dir()
                    self.update_rkd_dir()
                    self.update_opcode_set_dir()
                    self.update_rsp_page_grid_dir()
                    self.update_caccess_dir()
                    self.update_service_uuid_dir()
                    self.update_precision_time_dir()
                    log.debug('new path: {}'.format(self.path))
                    for iface in self.interfaces:
                        iface.update_path()
                    self.fru_uuid = get_fru_uuid(self.path)
                    return
                # end if
            # end for br_path
        # end for fab_path

    def unreachable_comp(self, to, iface):
        super().unreachable_comp(to, iface)
        # remove "to" from /sys fabric
        if to.dr is not None:
            to.remove_fab_dr_comp()
        else:
            to.remove_fab_comp()
