#!/usr/bin/env python3

# Copyright  ©  2020 IntelliProp Inc.
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

import contextlib
import argparse
import os
import re
import ctypes
import random
import time
import json
import requests
import logging
import logging.config
import yaml
import flask_fat
from flask_fat import ConfigBuilder
import flask_fat
import networkx as nx
from itertools import islice
from uuid import UUID, uuid4
from pathlib import Path
from importlib import import_module
from genz.genz_common import GCID, CState, IState
from middleware.netlink_mngr import NetlinkManager
from typing import List
from pdb import set_trace, post_mortem
import traceback

INVALID_GCID = GCID(val=0xffffffff)
TEMP_SUBNET = 0xffff  # where we put uninitialized local bridges
INVALID_UUID = UUID(int=0xffffffffffffffffffffffffffffffff)
fabs = Path('/sys/bus/genz/fabrics')
randgen = random.SystemRandom() # crypto secure random numbers from os.urandom

with open('zephyr-fm/logging.yaml', 'r') as f:
    yconf = yaml.safe_load(f.read())
    logging.config.dictConfig(yconf)

log = logging.getLogger('zephyr')

class FMServer(flask_fat.APIBaseline):
    def __init__(self, conf, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conf = conf
        self.add_callback = {}

def cmd_add(url, **args):
    from datetime import datetime
    data = {
        'timestamp' : datetime.now()
    }
    data.update(args)
    resp = requests.post(url, data)
    if resp is None:
        return {}
    return json.loads(resp.text).get('data', {})

class Interface():
    def __init__(self, component, num, peer_iface=None):
        self.comp = component
        self.peer_iface = peer_iface
        self.num = num
        self.hvs = None
        self.lprt = None
        self.vcat = None

    def setup_paths(self, prefix):
        self._prefix = prefix
        try:
            self.iface_dir = list((self.comp.path / prefix / 'interface').glob(
                'interface{}@*'.format(self.num)))[0]
        except IndexError:
            log.error('{}: interface{} does not exist'.format(self.comp.gcid, self.num))
            self.usable = False
            raise
        try:
            self.lprt_dir = list(self.iface_dir.glob('lprt@*'))[0]
        except IndexError:
            self.lprt_dir = None
        try:
            self.vcat_dir = list(self.iface_dir.glob('vcat@*'))[0]
        except IndexError:
            self.vcat_dir = None

    def iface_read(self, prefix='control'):
        self.setup_paths(prefix)
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            if len(data) >= ctypes.sizeof(genz.InterfaceXStructure):
                iface = self.comp.map.fileToStruct('interfaceX', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            else:
                iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            log.debug('{}: interface{}={}'.format(self.comp.gcid, self.num, iface))
            self.hvs = iface.HVS  # for num_vcs()
        # end with
        return iface

    # Returns True if interface is usable - is I-Up, not I-Down/I-CFG/I-LP
    def iface_init(self, prefix='control'):
        self.setup_paths(prefix)
        iface_file = self.iface_dir / 'interface'
        is_switch = self.comp.has_switch
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            if len(data) >= ctypes.sizeof(genz.InterfaceXStructure):
                iface = self.comp.map.fileToStruct('interfaceX', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            else:
                iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            log.debug('{}: interface{}={}'.format(self.comp.gcid, self.num, iface))
            self.hvs = iface.HVS
            if not self.phy_init():
                log.info('{}: interface{} is not PHY-Up'.format(
                    self.comp.gcid, self.num))
                self.usable = False
                # Revisit: should config iface even if not PHY-Up
                return False

            icap1 = genz.ICAP1(iface.ICAP1, iface)
            # Revisit: select compatible LLR/P2PNextHdr/P2PEncrypt settings
            # Revisit: set CtlOpClassPktFiltEnb, if Switch (for now)
            # Revisit: select Core64 & Control OpClass
            # enable Explicit OpCodes, and LPRT (if Switch)
            icap1ctl = genz.ICAP1Control(iface.ICAP1Control, iface)
            icap1ctl.field.OpClassSelect = 0x1
            icap1ctl.field.LPRTEnb = is_switch
            iface.ICAP1Control = icap1ctl.val
            self.comp.control_write(iface,
                            genz.InterfaceStructure.ICAP1Control, sz=4, off=4)
            # set LinkCTLControl (depending on local_br, is_switch)
            lctl = genz.LinkCTLControl(iface.LinkCTLControl, iface)
            # xmit bits set on local_br and all switch ports
            xmit = 1 if (self.comp.local_br or is_switch) else 0
            lctl.field.XmitPeerCUpEnb = xmit
            lctl.field.XmitPeerCResetEnb = xmit
            lctl.field.XmitPeerEnterLinkUpLPEnb = xmit
            lctl.field.XmitPeerEnterLinkLPEnb = xmit
            lctl.field.XmitLinkResetEnb = xmit
            # Revisit: recv bits should be set everywhere except on local_br
            # or "hostile" sw ports
            recv = 0 if (self.comp.local_br) else 1
            lctl.field.RecvPeerCUpEnb = recv
            lctl.field.RecvPeerCResetEnb = recv
            lctl.field.RecvPeerEnterLinkUpLPEnb = recv
            lctl.field.RecvPeerEnterLinkLPEnb = recv
            lctl.field.RecvLinkResetEnb = recv
            iface.LinkCTLControl = lctl.val
            self.comp.control_write(iface,
                            genz.InterfaceStructure.LinkCTLControl, sz=4, off=4)
            # send Peer-Attribute 1 Link CTL - HW did this at link-up time,
            # but we don't know when that was, and things may have changed
            status = self.send_peer_attr1(iface, timeout=100000)
            if status == 0:
                log.warning('{}: send_peer_attr1 timeout on interface{}'.format(
                    self.comp.gcid, self.num))
            # Revisit: path time does not currently work in HW
            # send Path Time Link CTL
            #status = self.send_path_time(iface, timeout=100000)
            #if status == 0:
            #    log.warning('{}: send_path_time timeout on interface{}'.format(
            #        self.comp.gcid, self.num))
            # save PeerInterfaceID
            self.peer_iface_num = self.get_peer_iface_num(iface)
            ictl = genz.IControl(iface.IControl, iface)
            # set IfaceAKeyValidationEnb (if supported)
            ictl.field.IfaceAKeyValidationEnb = (1 if
                                    icap1.field.IfaceAKeyValidationSup else 0)
            # Revisit: set Ingress/Egress AKeyMask
            # Revisit: set IngressDREnb only when needed
            ictl.field.IngressDREnb = 1
            # enable interface
            ictl.field.IfaceEnb = 1
            iface.IControl = ictl.val
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IControl, sz=4, off=4)
            # Revisit: do we need to do this?
            istatus = genz.IStatus(0, iface)
            istatus.field.LinkRFCStatus = 1  # RW1C
            iface.IStatus = istatus.val
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IStatus, sz=4, off=0)
            # verify I-Up
            state = self.check_i_state(iface)
            self.usable = (state is IState.IUp)
            # Revisit: orthus goes I-Down if we do this earlier
            # set LinkRFCDisable (depending on local_br)
            ictl.field.LinkRFCDisable = 1 if self.comp.local_br else 0
            iface.IControl = ictl.val
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IControl, sz=4, off=4)
            # save PeerCState & PeerGCID
            self.peer_cstate = self.get_peer_cstate(iface)
            self.peer_gcid = self.get_peer_gcid(iface)
        # end with
        if is_switch:
            # initialize VCAT
            # Revisit: multiple Action columns
            for vc in range(0, self.hvs + 1):
                # Revisit: vc policies
                self.vcat_write(vc, (1 << vc))
        return self.usable

    def update_peer_info(self):
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            if len(data) >= ctypes.sizeof(genz.InterfaceXStructure):
                iface = self.comp.map.fileToStruct('interfaceX', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            else:
                iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            self.send_peer_attr1(iface)
            self.peer_cstate = self.get_peer_cstate(iface)
            self.peer_gcid = self.get_peer_gcid(iface)
            self.peer_cclass = self.get_peer_cclass(iface)
            self.peer_inband_disabled = self.get_peer_inband_mgmt_disabled(iface)
            self.peer_mgr_type = self.get_peer_mgr_type(iface)

    def send_peer_attr1(self, iface, timeout=10000):
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.field.PeerAttr1Req = 1
        iface.IControl = icontrol.val
        self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                sz=4, off=4)
        status = self.wait_link_ctl(iface, timeout)
        icontrol.field.PeerAttr1Req = 0
        iface.IControl = icontrol.val
        return status

    def send_path_time(self, iface, timeout=10000):
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.field.PathTimeReq = 1
        iface.IControl = icontrol.val
        self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                sz=4, off=4)
        status = self.wait_link_ctl(iface, timeout)
        icontrol.field.PathTimeReq = 0
        iface.IControl = icontrol.val
        return status

    def wait_link_ctl(self, iface, timeout):
        istatus = genz.IStatus(iface.IStatus, iface)
        start = time.time_ns()
        done = False
        while not done:
            self.comp.control_read(iface, genz.InterfaceStructure.IStatus, sz=4)
            istatus.val = iface.IStatus
            log.debug('{}: wait_link_ctl[{}]: completed={}, status={}'.format(
                self.comp.gcid, self.num,
                istatus.field.LinkCTLCompleted,
                istatus.field.LinkCTLComplStatus))
            now = time.time_ns()
            done = (((now - start) > timeout) or
                    (istatus.field.LinkCTLCompleted == 1))
        return istatus.field.LinkCTLComplStatus

    def check_i_state(self, iface, timeout=500000000):
        istatus = genz.IStatus(iface.IStatus, iface)
        start = time.time_ns()
        done = False
        while not done:
            self.comp.control_read(iface, genz.InterfaceStructure.IStatus, sz=4)
            istatus.val = iface.IStatus
            istate = IState(istatus.field.IState)
            log.debug('{}: check_i_state[{}]: state={}'.format(
                self.comp.gcid, self.num, istate))
            now = time.time_ns()
            # Revisit: allow caller to pass in list of expected states
            done = (((now - start) > timeout) or
                    (istate in [IState.IUp, IState.ILP]))
        self.istate = istate
        return istate

    def get_peer_cstate(self, iface):
        # Re-read PeerState
        self.comp.control_read(iface, genz.InterfaceStructure.PeerState,
                               sz=4, off=4)
        peer_state = genz.PeerState(iface.PeerState, iface)
        peer_cstate = CState(peer_state.field.PeerCState)
        log.debug('{}: get_peer_c_state[{}]: PeerCState={!s}'.format(
            self.comp.gcid, self.num, peer_cstate))
        return peer_cstate

    def get_peer_gcid(self, iface):
        # Re-read PeerCID/PeerSID/PeerState
        self.comp.control_read(iface, genz.InterfaceStructure.PeerCID, sz=8)
        peer_state = genz.PeerState(iface.PeerState, iface)
        peer_cid = iface.PeerCID if peer_state.field.PeerCIDValid else None
        peer_sid = (iface.PeerSID if peer_state.field.PeerSIDValid else
                    self.comp.gcid.sid)
        try:
            peer_gcid = GCID(sid=peer_sid, cid=peer_cid)
        except TypeError:
            peer_gcid = None
        log.debug('{}: get_peer_gcid[{}]: PeerGCID={}'.format(
            self.comp.gcid, self.num, peer_gcid))
        return peer_gcid

    def get_peer_iface_num(self, iface):
        # Revisit: should this re-read value?
        # Unlike cstate & gcid, unless there's re-cabling, this can't change
        peer_state = genz.PeerState(iface.PeerState, iface)
        log.debug('{}: get_peer_iface_num[{}]: PeerIfaceIDValid={}, PeerInterfaceID={}'.format(
            self.comp.gcid, self.num,
            peer_state.field.PeerIfaceIDValid, iface.PeerInterfaceID))
        return (iface.PeerInterfaceID if peer_state.field.PeerIfaceIDValid == 1
                else None)

    def get_peer_cclass(self, iface):
        # Revisit: should this re-read value?
        # Unlike cstate & gcid, unless there's re-cabling, this can't change
        peer_state = genz.PeerState(iface.PeerState, iface)
        log.debug('{}: get_peer_cclass[{}]: PeerBaseCClassValid={}, PeerCClass={}'.format(
            self.comp.gcid, self.num,
            peer_state.field.PeerBaseCClassValid, iface.PeerBaseCClass))
        return (iface.PeerBaseCClass if peer_state.field.PeerBaseCClassValid == 1
                else None)

    def get_peer_inband_mgmt_disabled(self, iface):
        # Revisit: should this re-read value?
        peer_state = genz.PeerState(iface.PeerState, iface)
        return peer_state.field.PeerInbandMgmtDisabled

    def get_peer_mgr_type(self, iface):
        # Revisit: should this re-read value?
        peer_state = genz.PeerState(iface.PeerState, iface)
        return peer_state.field.PeerMgrType

    def phy_init(self):
        # This does not actually init anything - it only checks PHY status
        # Revisit: handle multiple PHYs
        # Revisit: interface phy struct is mandatory, but does not exist
        # for links between hemispheres in current dual-hemisphere switch
        try:
            phy_dir = list((self.iface_dir / 'interface_phy').glob(
                'interface_phy0@*'))[0]
            phy_file = phy_dir / 'interface_phy'
            with phy_file.open(mode='rb+') as f:
                data = bytearray(f.read())
                phy = self.comp.map.fileToStruct('interface_phy', data, fd=f.fileno(),
                                                 verbosity=self.comp.verbosity)
                log.debug('{}: phy{}={}'.format(self.comp.gcid, self.num, phy))
                return self.phy_status_ok(phy)
        except IndexError:
            log.debug('{}: phy{} missing - assume PHY-Up'.format(
                self.comp.gcid, self.num))
            return True # Revisit

    # Returns True if interface PHY is usable - is PHY-Up/PHY-Up-LP*/PHY-LP*
    def phy_status_ok(self, phy):
        op_status = genz.PHYStatus(phy.PHYStatus, phy).field.PHYLayerOpStatus
        return op_status in [1, 3, 4, 5, 6]

    def lprt_write(self, cid, ei, valid=1, mhc=None, hc=None, vca=None):
        if self.lprt_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        # Revisit: multiple routes
        lprt_file = self.lprt_dir / 'lprt'
        with lprt_file.open(mode='rb+', buffering=0) as f:
            if self.lprt is None:
                data = bytearray(f.read())
                self.lprt = self.comp.map.fileToStruct('lprt', data, path=lprt_file,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            else:
                self.lprt.set_fd(f)
            self.lprt[cid].EI = ei
            self.lprt[cid].V = valid
            self.lprt[cid].MHC = mhc if mhc is not None else 0
            self.lprt[cid].HC = hc if hc is not None else 0
            self.lprt[cid].VCA = vca if vca is not None else 0
            self.comp.control_write(self.lprt, self.lprt.element.MHC,
                                    off=4*cid, sz=4)
        # end with

    def vcat_write(self, vc, vcm, action=0, th=None):
        if self.vcat_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        vcat_file = self.vcat_dir / 'vcat'
        with vcat_file.open(mode='rb+', buffering=0) as f:
            if self.vcat is None:
                data = bytearray(f.read())
                self.vcat = self.comp.map.fileToStruct('vcat', data, path=vcat_file,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            else:
                self.vcat.set_fd(f)
            # Revisit: multiple Action columns
            # Revisit: TH support
            self.vcat[vc].VCM = vcm
            self.comp.control_write(self.vcat, self.vcat.element.VCM,
                                    off=4*vc, sz=4)
        # end with

    def update_lprt_dir(self):
        if self.lprt_dir is None:
            return
        self.lprt_dir = list(self.iface_dir.glob('lprt@*'))[0]
        log.debug('new lprt_dir = {}'.format(self.lprt_dir))

    def update_vcat_dir(self):
        if self.vcat_dir is None:
            return
        self.vcat_dir = list(self.iface_dir.glob('vcat@*'))[0]
        log.debug('new vcat_dir = {}'.format(self.vcat_dir))

    def update_path(self, prefix=None):
        if prefix is not None:
            self._prefix = prefix
        log.debug('iface{}: current path: {}'.format(self.num, self.iface_dir))
        self.iface_dir = list((self.comp.path / self._prefix / 'interface').glob(
            'interface{}@*'.format(self.num)))[0]
        log.debug('iface{}: new path: {}'.format(self.num, self.iface_dir))
        self.update_lprt_dir()
        self.update_vcat_dir()

    def __repr__(self):
        return '{}({}.{})'.format(self.__class__.__name__,
                                  self.comp.gcid, self.num)

    def __str__(self):
        return '{}.{}'.format(self.comp.gcid, self.num)

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

    def __init__(self, cclass, fab, map, path, mgr_uuid, verbosity=0,
                 local_br=False, dr=None, tmp_gcid=None, br_gcid=None,
                 netlink=None, uuid=None):
        self.cclass = cclass
        self.fab = fab
        self.map = map
        self.path = path
        self.mgr_uuid = mgr_uuid
        self.verbosity = verbosity
        self.local_br = local_br
        self.tmp_gcid = tmp_gcid
        self.gcid = tmp_gcid if tmp_gcid is not None else INVALID_GCID
        self.br_gcid = br_gcid
        self.dr = dr
        self.nl = netlink
        self.interfaces = []
        self.uuid = uuid4() if uuid is None else uuid
        self.nonce = fab.generate_nonce()
        self._num_vcs = None
        self._req_vcat_sz = None
        self._rsp_vcat_sz = None
        self._ssdt_sz = None
        self._comp_dest = None
        self.ssdt = None
        self.rit = None
        fab.components[self.uuid] = self
        fab.add_node(self)

    def __hash__(self):
        return hash(self.uuid)

    def __eq__(self, other):
        return self.uuid == other.uuid

    # for LLMUTO, NLMUTO, NIRT, FPST, REQNIRTO, REQABNIRTO
    def timeout_val(self, time):
        return int(time / Component.timer_unit_list[self.timer_unit])

    # for ControlTO, ControlDRTO
    def ctl_timeout_val(self, time):
        return int(time / Component.ctl_timer_unit_list[self.ctl_timer_unit])

    # Revisit: the sz & off params are workarounds for ctypes bugs
    def control_read(self, struct, field, sz=None, off=0):
        off += field.offset
        if sz is None:
            sz = ctypes.sizeof(field)  # Revisit: this doesn't work
        struct.data[off:off+sz] = os.pread(struct.fd, sz, off)

    # Revisit: the sz & off params are workarounds for ctypes bugs
    def control_write(self, struct, field, sz=None, off=0):
        off += field.offset
        if sz is None:
            sz = ctypes.sizeof(field)  # Revisit: this doesn't work
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
        self.fab.update_path('/sys/devices/genz1')  # Revisit: hardcoded path
        if setup:
            self.setup_paths('control')
        else:
            self.update_path()
        self.fru_uuid = get_fru_uuid(self.path)
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

    def setup_paths(self, prefix):
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
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

    # Returns True if component is usable - is C-Up/C-LP/C-DLP, not C-Down
    def comp_init(self, pfm, prefix='control', ingress_iface=None):
        log.debug('comp_init for {}'.format(self))
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
            # Revisit: verify good data (check ZUUID?)
            # save cstate and use below to control writes (e.g., CID0)
            cstatus = genz.CStatus(core.CStatus, core)
            self.cstate = CState(cstatus.field.CState)
            # save some other key values
            cap1 = genz.CAP1(core.CAP1, core)
            self.timer_unit = cap1.field.TimerUnit
            self.ctl_timer_unit = cap1.field.CtlTimerUnit
            self.cclass = core.BaseCClass
            # create and read (but do not HW init) all interfaces
            for ifnum in range(0, core.MaxInterface):
                if (ingress_iface is not None) and (ingress_iface.num == ifnum):
                    iface = ingress_iface
                else:
                    iface = Interface(self, ifnum)
                self.interfaces.append(iface)
                try:
                    self.interfaces[ifnum].iface_read(prefix=prefix)
                except IndexError:
                    pass
            # end for
            if self.cstate is CState.CCFG:
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
            if ingress_iface is not None:
                self.ssdt_write(pfm.gcid.cid, ingress_iface.num)
                self.rit_write(ingress_iface, 1 << ingress_iface.num)
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
            core.LLReqDeadline = 600
            core.NLLReqDeadline = 1000
            if self.cstate is not CState.CUp:
                # DeadlineTick can only be modified in non-C-Up
                core.DeadlineTick = 1000  # 1us
            self.control_write(core, genz.CoreStructure.LLReqDeadline, sz=4)
            # Revisit: set DRReqDeadline
            # Revisit: set LLRspDeadline, NLLRspDeadline, RspDeadline
            # Revisit: compute values depending on topology, as described
            # in Core spec section 15.2, Deadline Semantics
            # Revisit: only for responders
            # Revisit: if no Component Peer Attr struct, LL/NLL must be same
            core.LLRspDeadline = 601
            core.NLLRspDeadline = 1001
            core.RspDeadLine = 800 # packet execution time
            self.control_write(core, genz.CoreStructure.LLRspDeadline, sz=8)
            # we have set up just enough for "normal" responses to work -
            # tell the kernel about the new/changed component and stop DR
            # Revisit: before doing so, read back the first thing we wrote
            # (CV/CID0/SID0), and if it's still set correctly assume that CCTO
            # did not expire; otherwise, do what? Go back and try again?
            try:
                if self.cstate is CState.CCFG:
                    self.add_fab_comp()
                    prefix = 'control'
            except Exception as e:
                log.error('add_fab_comp failed with exception {}'.format(e))
                self.usable = False
                return self.usable
        # end with
        # re-open core file at (potential) new location set by add_fab_comp()
        core_file = self.path / prefix / 'core@0x0/core'
        with core_file.open(mode='rb+') as f:
            core.set_fd(f)
            if self.cstate is not CState.CCFG or self.local_br:
                # For non-local-bridge components in C-CFG, MGR-UUID will have
                # been captured on CV/CID0/SID0 write, so skip this
                # set MGR-UUID
                core.MGRUUIDl = int.from_bytes(self.mgr_uuid.bytes[0:8],
                                           byteorder='little')
                core.MGRUUIDh = int.from_bytes(self.mgr_uuid.bytes[8:16],
                                           byteorder='little')
                self.control_write(core, genz.CoreStructure.MGRUUIDl, sz=16)
            # Revisit: read back MGRUUID, to confirm we own component
            # not safe until orthus can handle errors
            # set HostMgrMGRUUIDEnb (if local_br), MGRUUIDEnb
            cap1ctl = genz.CAP1Control(core.CAP1Control, core)
            if self.local_br:
                cap1ctl.field.HostMgrMGRUUIDEnb = 1 # Revisit: enum
            cap1ctl.field.MGRUUIDEnb = 1
            # set ManagerType, PrimaryFabMgrRole
            # clear PrimaryMgrRole, SecondaryFabMgrRole, PwrMgrEnb
            cap1ctl.field.ManagerType = 1
            cap1ctl.field.PrimaryMgrRole = 0
            if self.local_br:
                cap1ctl.field.PrimaryFabMgrRole = 1
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
            # set PFMSID/PFMCID
            # Revisit: subnets
            core.PFMCID = pfm.gcid.cid
            self.control_write(core, genz.CoreStructure.PMCID, sz=8)
            # set PFMCIDValid; clear other CID/SID valid bits
            cap2ctl = genz.CAP2Control(core.CAP2Control, core)
            cap2ctl.field.PMCIDValid = 0
            cap2ctl.field.PFMCIDValid = 1
            cap2ctl.field.SFMCIDValid = 0
            cap2ctl.field.PFMSIDValid = 0
            cap2ctl.field.SFMSIDValid = 0
            core.CAP2Control = cap2ctl.val
            self.control_write(core, genz.CoreStructure.CAP2Control, sz=8)
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
            # Revisit: set UNREQ, UNRSP, UERT, NIRT, FPST, NLMUTO
            # Revisit: set REQNIRTO, REQABNIRTO
            # set ControlTO, ControlDRTO
            # Revisit: how to compute reasonable values?
            core.ControlTO = self.ctl_timeout_val(5e-3)    # 5ms
            core.ControlDRTO = self.ctl_timeout_val(10e-3) # 10ms
            self.control_write(core, genz.CoreStructure.ControlTO, sz=4)
            # set MaxRequests
            # Revisit: Why would FM choose < MaxREQSuppReqs? Only for P2P?
            # Revisit: only for requesters
            core.MaxRequests = core.MaxREQSuppReqs
            self.control_write(core, genz.CoreStructure.MaxRequests, sz=8)
            # Revisit: set MaxPwrCtl (to NPWR?)
            # invalidate SSDT (except PFM CID written earlier)
            for cid in range(0, self.ssdt_size(prefix=prefix)):
                if cid != pfm.gcid.cid or ingress_iface is None:
                    self.ssdt_write(cid, 0x780|cid, valid=0) # Revisit: ei debug
            # initialize REQ-VCAT
            # Revisit: multiple Action columns
            for vc in range(0, self.req_vcat_size(prefix=prefix)[0]):
                # Revisit: vc policies
                self.req_vcat_write(vc, 0x2)
            # initialize RIT for each usable interface
            for iface in self.interfaces:
                if iface.usable:
                    self.rit_write(iface, 1 << iface.num)
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
            else:
                log.info('{} has no usable interfaces'.format(self.path))
        # end with
        if self.has_switch:
            self.switch_init(core)
        return self.usable

    def switch_init(self, core):
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

    def comp_dest_read(self, prefix='control'):
        if self._comp_dest is not None:
            return self._comp_dest
        comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        comp_dest_file = comp_dest_dir / 'component_destination_table'
        with comp_dest_file.open(mode='rb') as f:
            data = bytearray(f.read())
            self._comp_dest = self.map.fileToStruct(
                'component_destination_table',
                data, fd=f.fileno(), verbosity=self.verbosity)
        # end with
        return self._comp_dest

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
            data = bytearray(f.read())
            self.req_vcat = self.map.fileToStruct('req_vcat', data,
                                path=req_vcat_file,
                                fd=f.fileno(), verbosity=self.verbosity)
            # Revisit: multiple Action columns
            # Revisit: TH support
            self.req_vcat[vc].VCM = vcm
            self.control_write(self.req_vcat, self.req_vcat.element.VCM,
                               off=4*vc, sz=4)
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
            data = bytearray(f.read())
            self.rsp_vcat = self.map.fileToStruct('rsp_vcat', data,
                                path=rsp_vcat_file,
                                fd=f.fileno(), verbosity=self.verbosity)
            # Revisit: multiple Action columns
            # Revisit: TH support
            self.rsp_vcat[vc].VCM = vcm
            self.control_write(self.rsp_vcat, self.rsp_vcat.element.VCM,
                               off=4*vc, sz=4)
        # end with

    def ssdt_size(self, prefix='control'):
        if self._ssdt_sz is not None:
            return self._ssdt_sz
        comp_dest = self.comp_dest_read(prefix=prefix)
        self._ssdt_sz = comp_dest.SSDTSize
        log.debug('{}: ssdt_sz={}'.format(self.gcid, self._ssdt_sz))
        return self._ssdt_sz

    def ssdt_write(self, cid, ei, valid=1, mhc=None, hc=None, vca=None):
        if self.ssdt_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        # Revisit: multiple routes
        ssdt_file = self.ssdt_dir / 'ssdt'
        with ssdt_file.open(mode='rb+', buffering=0) as f:
            if self.ssdt is None:
                data = bytearray(f.read())
                self.ssdt = self.map.fileToStruct('ssdt', data, path=ssdt_file,
                                      fd=f.fileno(), verbosity=self.verbosity)
            else:
                self.ssdt.set_fd(f)
            self.ssdt[cid].EI = ei
            self.ssdt[cid].V = valid
            self.ssdt[cid].MHC = mhc if mhc is not None else 0
            self.ssdt[cid].HC = hc if hc is not None else 0
            self.ssdt[cid].VCA = vca if vca is not None else 0
            self.control_write(self.ssdt, self.ssdt.element.MHC,
                               off=4*cid, sz=4)
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

    def update_switch_dir(self, prefix='control'):
        if self.switch_dir is None:
            return
        self.comp_dest_dir = list((self.path / prefix).glob(
            'component_destination_table@*'))[0]
        self.switch_dir = list((self.path / prefix).glob(
            'component_switch@*'))[0]
        log.debug('new switch_dir = {}'.format(self.switch_dir))

    def update_path(self):
        log.debug('current path: {}'.format(self.path))
        self.path = self.fab.make_path(self.gcid)
        log.debug('new path: {}'.format(self.path))
        self.update_ssdt_dir()
        self.update_rit_dir()
        self.update_req_vcat_dir()
        self.update_rsp_vcat_dir()
        self.update_switch_dir()
        for iface in self.interfaces:
            iface.update_path(prefix='control')

    @property
    def has_switch(self):
        return self.switch_dir is not None

    def config_interface(self, iface, pfm, ingress_iface):
        iface.update_peer_info()
        # get peer CState
        peer_cstate = iface.peer_cstate
        msg = '{}: exploring interface{}, peer cstate={!s}, '.format(
            self.gcid, iface.num, peer_cstate)
        if iface.peer_inband_disabled:
            msg += 'peer inband management disabled - ignoring peer'
            log.info(msg)
            return
        if iface.peer_mgr_type == 0:  # Revisit: enum
            # Revisit: mamba/switch/orthus reporting wrong value
            #msg += 'peer manager type is not Fabric - ignoring peer'
            msg += 'peer manager type is not Fabric - claiming anyway, '
            #log.info(msg)
            #return
        # We need to distinguish 5 cases here:
        # 1. cstate is C-CFG - component is ready for us to configure
        #    using directed relay.
        # Revisit: we can't read MGR-UUID, so this doesn't work
        # Revisit: Russ says nonce exchange can work, but it's optional
        # 2. cstate is C-Up: Read MGR-UUID - 3 sub-cases:
        #    a. MGR-UUID matches our current MGR-UUID:
        #       Topology has a cycle; this is another path to a component
        #       we've already configured. Add new link to topology (for
        #       multipath routing); do nothing else.
        #    b. MGR-UUID matches a previous MGR-UUID we've used:
        #       Revisit: try to talk to it using previous C-Access
        #       If that fails, reset component and handle as case 1.
        #    c. MGR-UUID is unknown to us (or read fails):
        #       Revisit: try to contact foreign FM
        # 3. cstate is C-LP/C-DLP:
        #    Revisit: handle these power states
        # Note: C-Down is handled in explore_interfaces() - we never get here.
        if peer_cstate is CState.CUp:
            # get PeerGCID
            peer_gcid = iface.peer_gcid
            msg += 'peer gcid={}'.format(peer_gcid)
            if peer_gcid is None:
                msg += 'peer GCID not valid - ignoring peer'
                log.info(msg)
                return
            # Revisit: this assumes no other managers
            if peer_gcid in self.fab.comp_gcids: # another path
                comp = self.fab.comp_gcids[peer_gcid]
                peer_iface = comp.interfaces[iface.peer_iface_num]
                self.fab.add_link(self, iface, comp, peer_iface)
                route = self.fab.setup_routing(pfm, comp)
                self.fab.setup_routing(comp, pfm, route=route.invert())
                msg += ' additional path to {}'.format(peer_iface)
                log.info(msg)
            else:
                path = self.fab.make_path(peer_gcid)
                comp = Component(iface.peer_cclass, self.fab, self.map, path,
                                 self.mgr_uuid, br_gcid=self.br_gcid,
                                 netlink=self.nl, verbosity=self.verbosity)
                peer_iface = Interface(comp, iface.peer_iface_num, iface)
                iface.peer_iface = peer_iface
                gcid = self.fab.assign_gcid(comp, proposed_gcid=peer_gcid)
                if gcid is None:
                    msg += ' gcid conflict, ignoring component'
                    log.warning(msg)
                    return
                msg += ' retaining gcid={}'.format(gcid)
                log.info(msg)
                self.fab.add_link(self, iface, comp, peer_iface)
                route = self.fab.setup_routing(pfm, comp)
                self.fab.setup_routing(comp, pfm, write_ssdt=False,
                                       route=route.invert())
                try:
                    comp.add_fab_comp(setup=True)
                except Exception as e:
                    log.error('add_fab_comp failed with exception {}'.format(e))
                    return
                comp.comp_init(pfm, ingress_iface=peer_iface)
                cuuid = get_cuuid(comp.path)
                serial = get_serial(comp.path)
                cuuid_serial = str(cuuid) + ':' + serial
                comp.fab.cuuid_serial[cuuid_serial] = comp
                comp.fab.comp_gcids[comp.gcid] = comp
                if comp.has_switch:  # if switch, recurse
                    comp.explore_interfaces(pfm, ingress_iface=peer_iface)
        if peer_cstate is CState.CCFG:
            dr = DirectedRelay(self, ingress_iface, iface)
            comp = Component(iface.peer_cclass, self.fab, self.map, dr.path,
                             self.mgr_uuid, dr=dr, br_gcid=self.br_gcid,
                             netlink=self.nl, verbosity=self.verbosity)
            peer_iface = Interface(comp, iface.peer_iface_num, iface)
            iface.peer_iface = peer_iface
            gcid = self.fab.assign_gcid(comp)
            msg += 'assigned gcid={}'.format(gcid)
            log.info(msg)
            self.fab.add_link(self, iface, comp, peer_iface)
            log.debug('sleeping 2 seconds to help with perf problems')
            time.sleep(2.0) # Revisit: why does this help?
            route = self.fab.setup_routing(pfm, comp)
            self.fab.setup_routing(comp, pfm, write_ssdt=False,
                                   route=route.invert())
            try:
                comp.add_fab_dr_comp()
            except Exception as e:
                log.error('add_fab_dr_comp failed with exception {}'.format(e))
                return
            comp.comp_init(pfm, prefix='dr', ingress_iface=peer_iface)
            cuuid = get_cuuid(comp.path)
            serial = get_serial(comp.path)
            cuuid_serial = str(cuuid) + ':' + serial
            comp.fab.cuuid_serial[cuuid_serial] = comp
            comp.fab.comp_gcids[comp.gcid] = comp
            if comp.has_switch:  # if switch, recurse
                comp.explore_interfaces(pfm, ingress_iface=peer_iface)
        # end if peer_cstate

    def explore_interfaces(self, pfm, ingress_iface=None):
        # examine all interfaces (except ingress) & init those components
        for iface in self.interfaces:
            if iface == ingress_iface:
                log.debug('{}: skipping ingress interface{}'.format(
                    self.gcid, iface.num))
            elif iface.usable:
                self.config_interface(iface, pfm, ingress_iface)
            else:
                log.info('{}: interface{} is not usable'.format(
                    self.gcid, iface.num))

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, self.gcid)

class Memory(Component):
    cclasses = (0x1, 0x2)

class Switch(Component):
    cclasses = (0x3, 0x4, 0x5)

class Bridge(Component):
    cclasses = (0x14, 0x15)

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
                    log.debug('new path: {}'.format(self.path))
                    for iface in self.interfaces:
                        iface.update_path()
                    return
                # end if
            # end for br_path
        # end for fab_path

class Fabric(nx.MultiGraph):
    def __init__(self, nl, map, path, fab_uuid=None, grand_plan=None,
                 random_cids=False, accept_cids=False, verbosity=0):
        self.nl = nl
        self.map = map
        self.path = path
        self.fabnum = component_num(path)
        self.fab_uuid = fab_uuid
        self.mgr_uuid = uuid4()
        self.random_cids = random_cids
        self.accept_cids = accept_cids
        self.verbosity = verbosity
        self.bridges = []      # indexed by bridge number
        self.components = {}   # key: comp.uuid
        self.cuuid_serial = {} # key: cuuid:serial
        self.comp_gcids = {}   # key: comp.gcid
        self.assigned_gcids = []
        self.refill_gcids = True
        self.nonce_list = [ 0 ]
        super().__init__()
        log.info('fabric: {}, num={}, fab_uuid={}, mgr_uuid={}'.format(
            path, self.fabnum, self.fab_uuid, self.mgr_uuid))

    def assign_gcid(self, comp, ssdt_sz=4096, proposed_gcid=None):
        # Revisit: subnets
        # Revisit: CID conficts between accepted & assigned are possible
        random_cids = self.random_cids
        if self.refill_gcids:
            self.avail_gcids = (random.sample(range(1, ssdt_sz), ssdt_sz-1)
                                if random_cids else list(range(1, ssdt_sz)))
            self.refill_gcids = False
        if proposed_gcid is not None:
            try:
                self.avail_gcids.remove(proposed_gcid.cid)
                comp.gcid = proposed_gcid
            except ValueError:
                comp.gcid = None
        else:
            try:
                cid = self.avail_gcids.pop(0)
                comp.gcid = GCID(cid=cid)
            except IndexError:
                comp.gcid = None
        if comp.gcid is not None:
            self.assigned_gcids.append(comp.gcid)
        return comp.gcid

    def generate_nonce(self):
        while True:
            r = randgen.getrandbits(64)
            if not r in self.nonce_list:
                self.nonce_list.append(r)
                return r

    def fab_init(self):
        br_paths = self.path.glob('bridge*')
        # Revisit: deal with multiple bridges that may or may not be on same fabric
        for br_path in br_paths:
            cuuid = get_cuuid(br_path)
            serial = get_serial(br_path)
            cuuid_serial = str(cuuid) + ':' + serial
            cur_gcid = get_gcid(br_path)
            brnum = component_num(br_path)
            cclass = int(get_cclass(br_path))
            tmp_gcid = cur_gcid if cur_gcid.sid == TEMP_SUBNET else INVALID_GCID
            br = LocalBridge(cclass, self, self.map, br_path, self.mgr_uuid,
                             local_br=True, brnum=brnum, dr=None,
                             tmp_gcid=tmp_gcid, netlink=self.nl,
                             verbosity=self.verbosity)
            gcid = self.assign_gcid(br, ssdt_sz=br.ssdt_size())
            pfm = br
            log.info('{}:{} bridge{} {}'.format(self.fabnum, gcid, brnum, cuuid_serial))
            self.cuuid_serial[cuuid_serial] = br
            self.comp_gcids[br.gcid] = br
            br.comp_init(pfm)
            self.bridges.append(br)
            br.explore_interfaces(pfm)
        # end for br_path

    def shortest_path(self, fr: Component, to: Component) -> List[Component]:
        return nx.shortest_path(self, fr, to)

    def k_shortest_paths(self, fr: Component, to: Component,
                         k: int) -> List[List[Component]]:
        g = nx.Graph(self)  # Revisit: don't re-create g on every call
        return list(islice(nx.shortest_simple_paths(
            g, fr, to, weight=None), k))

    def route(self, fr: Component, to: Component) -> 'Route':
        # Revisit: edge weights, force start/end interface
        path = self.shortest_path(fr, to)
        return Route(path)

    def k_routes(self, fr: Component, to: Component, k: int) -> List['Route']:
        # Revisit: MultiGraph, edge weights, force start/end interface
        paths = self.k_shortest_paths(fr, to, k)
        return [Route(p) for p in paths]

    def write_route(self, route: 'Route', write_ssdt=True):
        for rt in route:
            if rt.ingress_iface is not None:
                # switch: add to's GCID to rt's LPRT
                rt.set_lprt(route.to)
            elif write_ssdt:
                # add to's GCID to rt's SSDT
                rt.set_ssdt(route.to)

    def setup_routing(self, fr: Component, to: Component,
                      write_ssdt=True, route=None) -> 'Route':
        if route is None:
            route = self.route(fr, to)
        log.info('adding route from {} to {} via {}'.format(fr, to, route))
        self.write_route(route, write_ssdt)
        return route

    # Revisit: could derive fr/to from fr_iface.comp/to_iface.comp
    def add_link(self, fr: Component, fr_iface: Interface,
                 to: Component, to_iface: Interface) -> None:
        # Revisit: need to prevent adding same link multiple times
        self.add_edges_from([(fr, to, {fr.uuid: fr_iface, to.uuid: to_iface})])

    def make_path(self, gcid):
        return fabs / 'fabric{f}/{f}:{s:04x}/{f}:{s:04x}:{c:03x}'.format(
            f=self.fabnum, s=gcid.sid, c=gcid.cid)

    def update_path(self, path):
        self.path = path
        self.fabnum = component_num(path)

class RouteElement():
    def __init__(self, comp: Component,
                 ingress_iface: Interface, egress_iface: Interface,
                 to_iface: Interface = None):
        self.comp = comp
        self.ingress_iface = ingress_iface
        self.egress_iface = egress_iface
        self.to_iface = to_iface
        self.dr = False

    @property
    def gcid(self):
        return self.comp.gcid

    @property
    def path(self):
        return self.egress_iface.iface_dir

    def set_ssdt(self, to: Component):
        self.comp.ssdt_write(to.gcid.cid, self.egress_iface.num)

    def set_lprt(self, to: Component):
        self.ingress_iface.lprt_write(to.gcid.cid, self.egress_iface.num)

    def __str__(self):
        # Revisit: handle self.dr
        return ('{}->{}'.format(self.egress_iface, self.to_iface)
                if self.to_iface else '{}'.format(self.egress_iface))

class DirectedRelay(RouteElement):
    def __init__(self, dr_comp: Component,
                 ingress_iface: Interface, dr_iface: Interface):
        super().__init__(dr_comp, ingress_iface, dr_iface)
        self.dr = True

class Route():
    def __init__(self, path: List[Component]):
        if len(path) < 2:
            raise(IndexError)
        self._path = path
        self._elems = []
        ingress_iface = None
        for fr, to in moving_window(2, path):
            # Revisit: MultiGraph
            edge_data = fr.fab.get_edge_data(fr, to)[0]
            egress_iface = edge_data[fr.uuid]
            to_iface = edge_data[to.uuid]
            elem = RouteElement(fr, ingress_iface, egress_iface, to_iface)
            self._elems.append(elem)
            ingress_iface = to_iface

    @property
    def fr(self):
        return self._path[0]

    @property
    def to(self):
        return self._path[-1]

    def invert(self) -> 'Route':
        # Revisit: MultiGraph - this does not guarantee identical links
        inverse = Route(self._path[::-1])
        return inverse

    def __getitem__(self, key):
        return self._elems[key]

    def __len__(self):
        return len(self._elems)

    def __iter__(self):
        return iter(self._elems)

    def __str__(self):
        return '[' + ','.join('{}'.format(e) for e in self._elems) + ']'

class Conf():
    def __init__(self, file):
        self.file = file
        self.add = {}

    def read_conf_file(self):
        with open(self.file, 'r') as f:
            self.data = json.load(f)
            return self.data

    def write_conf_file(self, data):
        self.data = data
        with open(self.file, 'w') as f:
            json.dump(self.data, f, indent=2)

    def add_resource(self, conf_add):
        fab = self.fab
        add = self.add
        add_args = {}
        try:
            prod_comp = fab.cuuid_serial[conf_add['producer']]
        except KeyError:
            log.warning('{}: producer component {} not found in fabric{}'.format(
                self.file, conf_add['producer'], fab.fabnum))
            return
        add_args['gcid']     = prod_comp.gcid.val
        add_args['cclass']   = prod_comp.cclass
        add_args['fru_uuid'] = str(prod_comp.fru_uuid)
        add_args['mgr_uuid'] = str(prod_comp.mgr_uuid)
        for res in conf_add['resources']:
            res['instance_uuid'] = str(uuid4())
            # Revisit: set up responder ZMMU if res['type'] is DATA (1)
        add_args['resources'] = conf_add['resources']
        for con in conf_add['consumers']:
            if not con in add:
                add[con] = []
            add[con].append(add_args)
            try:
                con_comp = fab.cuuid_serial[con]
            except KeyError:
                log.warning('{}: consumer component {} not found in fabric{}'.format(
                    self.file, con, fab.fabnum))
                continue
            # Revisit: consider delaying routing until llamas connects
            route = fab.setup_routing(con_comp, prod_comp)
            fab.setup_routing(prod_comp, con_comp, route=route.invert())
        # end for con
        return add_args

    def add_resources(self, fab):
        self.fab = fab
        add_res = self.data.get('add_resources', [])
        if len(add_res) == 0:
            log.info('add_resources not found in {}'.format(self.file))
        log.info('adding resources from {}'.format(self.file))
        for conf_add in add_res:
            self.add_resource(conf_add)
        return self.add

    def __repr__(self):
        return 'Conf(' + repr(self.data) + ')'

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

def get_serial(comp_path):
    serial = comp_path / 'serial'
    with serial.open(mode='r') as f:
        return f.read().rstrip()

def get_cclass(comp_path):
    cclass = comp_path / 'cclass'
    with cclass.open(mode='r') as f:
        return f.read().rstrip()

comp_num_re = re.compile(r'.*/([^0-9]+)([0-9]+)')

def component_num(comp_path):
    match = comp_num_re.match(str(comp_path))
    return int(match.group(2))

def moving_window(n, iterable):
    # return "n" items from iterable at a time, advancing 1 item per call
    start, stop = 0, n
    while stop <= len(iterable):
        yield iterable[start:stop]
        start += 1
        stop += 1


def main():
    global args
    global cols
    global genz
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', '--keyboard', action='store_true',
                        help='break to interactive keyboard at certain points')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-A', '--accept-cids', action='store_true',
                        help='accept pre-existing HW CIDs for all components')
    parser.add_argument('-R', '--random-cids', action='store_true',
                        help='generate random CIDs for all components')
    parser.add_argument('-G', '--genz-version', choices=['1.1'],
                        default='1.1',
                        help='Gen-Z spec version of Control Space structures')
    parser.add_argument('-P', '--post_mortem', action='store_true',
                        help='enter debugger on uncaught exception')
    args = parser.parse_args()
    args_vars = vars(args)
    log.debug('Gen-Z version = {}'.format(args.genz_version))
    genz = import_module('genz.genz_{}'.format(args.genz_version.replace('.', '_')))
    nl = NetlinkManager(config='./zephyr-fm/alpaka.conf')
    map = genz.ControlStructureMap()
    conf = Conf('zephyr-fm/zephyr-fabric.conf')
    try:
        data = conf.read_conf_file()
        fab_uuid = UUID(data['fabric_uuid'])
    except FileNotFoundError:
        # create new skeleton file
        data = {}
        fab_uuid = uuid4()
        data['fabric_uuid'] = str(fab_uuid)
        conf.write_conf_file(data)
    log.debug('conf={}'.format(conf))
    fabrics = {}
    if args.keyboard:
        set_trace()
    sys_devices = Path('/sys/devices')
    fab_paths = sys_devices.glob('genz*')
    fab = None
    for fab_path in fab_paths:
        fab = Fabric(nl, map, fab_path, random_cids=args.random_cids,
                     accept_cids=args.accept_cids, fab_uuid=fab_uuid,
                     verbosity=args.verbosity)
        fabrics[fab_path] = fab
        fab.fab_init()

    if fab is None:
        log.info('no local Gen-Z bridges found')
        return

    if args.keyboard:
        set_trace()

    conf.add_resources(fab)  # Revisit: multiple fabrics
    mainapp = FMServer(conf, 'zephyr', **args_vars)

    if args.keyboard:
        set_trace()

    mainapp.run()

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
