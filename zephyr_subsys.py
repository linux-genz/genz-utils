#!/usr/bin/env python3

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
import networkx as nx
from uuid import UUID, uuid4
from pathlib import Path
from genz_common import GCID
from middleware.netlink_mngr import NetlinkManager
from pdb import set_trace

INVALID_GCID = GCID(val=0xffffffff)
TEMP_SUBNET = 0xffff  # where we put uninitialized local bridges

class Interface():
    def __init__(self, component, num):
        self.comp = component
        self.num = num

    # Returns True if interface is usable - is I-Up/I-LP, not I-Down/I-CFG
    def iface_init(self):
        self.iface_dir = list((self.comp.path / 'control/interface').glob(
            'interface{}@*'.format(self.num)))[0]
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            if len(data) >= ctypes.sizeof(genz.InterfaceXStructure):
                iface = self.comp.map.fileToStruct('interfaceX', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            else:
                iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            if self.comp.verbosity:
                print(iface)

            if not self.phy_init():
                if self.comp.verbosity:
                    print('interface {} is not usable'.format(self.num))
                    self.usable = False
                # return False  # Revisit: no return to test code below

            icap1 = genz.ICAP1(iface.ICAP1, iface)
            # Revisit: select compatible LLR/P2PNextHdr/P2PEncrypt settings
            # Revisit: set CtlOpClassPktFiltEnb, if Switch (for now)
            # Revisit: select Core64 & Control OpClass
            # enable Explicit OpCodes
            icap1ctl = genz.ICAP1Control(iface.ICAP1Control, iface)
            icap1ctl.field.OpClassSelect = 0x1
            iface.ICAP1Control = icap1ctl.val
            self.comp.control_write(iface,
                            genz.InterfaceStructure.ICAP1Control, sz=4, off=4)
            # set LinkCTLControl (depending on local_br)
            lctl = genz.LinkCTLControl(iface.LinkCTLControl, iface)
            if self.comp.local_br:
                lctl.field.XmitPeerCUpEnb = 1
                lctl.field.XmitPeerCResetEnb = 1
                lctl.field.XmitPeerEnterLinkUpLPEnb = 1
                lctl.field.XmitPeerEnterLinkLPEnb = 1
                lctl.field.XmitLinkResetEnb = 1
                lctl.field.RecvPeerCUpEnb = 0
                lctl.field.RecvPeerCResetEnb = 0
                lctl.field.RecvPeerEnterLinkUpLPEnb = 0
                lctl.field.RecvPeerEnterLinkLPEnb = 0
                lctl.field.RecvLinkResetEnb = 0
            else:
                lctl.field.XmitPeerCUpEnb = 0
                lctl.field.XmitPeerCResetEnb = 0
                lctl.field.XmitPeerEnterLinkUpLPEnb = 0
                lctl.field.XmitPeerEnterLinkLPEnb = 0
                lctl.field.XmitLinkResetEnb = 0
                lctl.field.RecvPeerCUpEnb = 1
                lctl.field.RecvPeerCResetEnb = 1
                lctl.field.RecvPeerEnterLinkUpLPEnb = 1
                lctl.field.RecvPeerEnterLinkLPEnb = 1
                lctl.field.RecvLinkResetEnb = 1
            iface.LinkCTLControl = lctl.val
            self.comp.control_write(iface,
                            genz.InterfaceStructure.LinkCTLControl, sz=4, off=4)
            # send Peer-Attribute 1 Link CTL - HW did this at link-up time,
            # but we don't know when that was, and things may have changed
            status = self.send_peer_attr1(iface, timeout=100000)
            if status == 0:
                if self.comp.verbosity:
                    print('send_peer_attr1 timeout')
            # send Path Time Link CTL
            status = self.send_path_time(iface, timeout=100000)
            if status == 0:
                if self.comp.verbosity:
                    print('send_path_time timeout')
            # set LinkRFCDisable (depending on local_br)
            ictl = genz.IControl(iface.IControl, iface)
            ictl.field.LinkRFCDisable = 1 if self.comp.local_br else 0
            # set IfaceAKeyValidationEnb (if supported)
            ictl.field.IfaceAKeyValidationEnb = (1 if
                                    icap1.field.IfaceAKeyValidationSup else 0)
            # Revisit: set Ingress/Egress AKeyMask
            # Revisit: set IngressDREnb
            # enable interface
            ictl.field.IfaceEnb = 1
            iface.IControl = ictl.val
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IControl, sz=4, off=4)
            # Revisit: verify I-Up
            state = self.check_i_state(iface)
            if state in [2, 3]:
                self.usable = True
        # end with
        return self.usable

    def send_peer_attr1(self, iface, timeout=0):
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.field.PeerAttr1Req = 1
        iface.IControl = icontrol.val
        self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                sz=4, off=4)
        status = self.wait_link_ctl(iface, timeout)
        return status

    def send_path_time(self, iface, timeout=0):
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.field.PathTimeReq = 1
        iface.IControl = icontrol.val
        self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                sz=4, off=4)
        status = self.wait_link_ctl(iface, timeout)
        return status

    def wait_link_ctl(self, iface, timeout):
        istatus = genz.IStatus(iface.IStatus, iface)
        start = time.time_ns()
        done = False
        while not done:
            self.comp.control_read(iface, genz.InterfaceStructure.IStatus, sz=4)
            istatus.val = iface.IStatus
            if self.comp.verbosity:
                print('wait_link_ctl: completed={}, status={}'.format(
                    istatus.field.LinkCTLCompleted,
                    istatus.field.LinkCTLComplStatus))
            now = time.time_ns()
            done = (((now - start) > timeout) or
                    (istatus.field.LinkCTLCompleted == 1))
        return istatus.field.LinkCTLComplStatus

    def check_i_state(self, iface):
        istatus = genz.IStatus(iface.IStatus, iface)
        # Revisit: loop with timeout?
        self.comp.control_read(iface, genz.InterfaceStructure.IStatus, sz=4)
        istatus.val = iface.IStatus
        if self.comp.verbosity:
            print('check_i_status: state={}'.format(
                istatus.field.IState))
        return istatus.field.IState

    def phy_init(self):
        # This does not actually init anything - it only checks PHY status
        # Revisit: handle multiple PHYs
        phy_dir = list((self.iface_dir / 'interface_phy').glob(
            'interface_phy0@*'))[0]
        phy_file = phy_dir / 'interface_phy'
        with phy_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            phy = self.comp.map.fileToStruct('interface_phy', data, fd=f.fileno(),
                                             verbosity=self.comp.verbosity)
            if self.comp.verbosity:
                print(phy)
            return self.phy_status_ok(phy)

    # Returns True if interface PHY is usable - is PHY-Up/PHY-Up-LP*/PHY-LP*
    def phy_status_ok(self, phy):
        op_status = genz.PHYStatus(phy.PHYStatus, phy).field.PHYLayerOpStatus
        return op_status in [1, 3, 4, 5, 6, 7, 8, 9, 0xa]

class DirectedRelay():
    def __init__(self, dr_comp, dr_iface):
        self.comp = dr_comp
        self.iface = dr_iface

    @property
    def gcid(self):
        return self.comp.gcid

class Component():
    timer_unit_list = [ 1e-9, 10*1e-9, 100*1e-9, 1e-6, 10*1e-6, 100*1e-6,
                        1e-3, 10*1e-3, 100*1e-3, 1.0 ]
    ctl_timer_unit_list = [ 1e-6, 10*1e-6, 100*1e-6, 1e-3 ]

    def __init__(self, fab, map, path, mgr_uuid, verbosity=0, local_br=False,
                 dr=None, tmp_gcid=None, br_gcid=None, netlink=None):
        self.fab = fab
        self.map = map
        self.path = path
        self.mgr_uuid = mgr_uuid
        self.verbosity = verbosity
        self.local_br = local_br
        self.tmp_gcid = tmp_gcid
        self.br_gcid = br_gcid
        self.dr = dr
        self.nl = netlink
        self.interfaces = []

    def __hash__(self):
        return hash(self.path)  # Revisit: broken when path changes

    def __eq__(self, other):
        return self.path == other.path  # Revisit: broken when path changes

    def timeout_val(self, time):
        return int(time / Component.timer_unit_list[self.timer_unit])

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

    def add_fab_comp(self):
        cmd_name = self.nl.cfg.get('ADD_FAB_COMP')
        data = {'gcid':     self.gcid.val,
                'br_gcid':  self.br_gcid.val,
                'tmp_gcid': self.tmp_gcid.val,
                'dr_gcid':  self.dr.gcid.val if self.dr else INVALID_GCID.val,
                'dr_iface': self.dr.iface if self.dr else 0,
                'mgr_uuid': self.mgr_uuid,
        }
        msg = self.nl.build_msg(cmd=cmd_name, data=data)
        ret = self.nl.sendmsg(msg)
        self.update_path()
        return ret

    # Returns the current component GCID
    def get_gcid(self):
        gcid = None
        core_file = self.path / 'control/core@0x0/core'
        with core_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                         verbosity=self.verbosity)
            if core.CV:
                gcid = GCID(val=core.CID0)  # Revisit: Subnets
        return gcid

    # Returns True if component is usable - is C-Up/C-LP/C-DLP, not C-Down
    def comp_init(self, gcid, pfm_gcid, random_cid=False):
        self.usable = False
        self.gcid = gcid
        if self.local_br:
            self.br_gcid = gcid
        core_file = self.path / 'control/core@0x0/core'
        with core_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            core = self.map.fileToStruct('core', data, fd=f.fileno(),
                                         verbosity=self.verbosity)
            if self.verbosity:
                print(core)
            # save some key values
            cap1 = genz.CAP1(core.CAP1, core)
            self.timer_unit = cap1.field.TimerUnit
            self.ctl_timer_unit = cap1.field.CtlTimerUnit
            # set CV/CID0/SID0
            # Revisit: support subnets and multiple CIDs
            core.CID0 = gcid.cid
            core.CV = 1
            self.control_write(core, genz.CoreStructure.CV, sz=8)
            # set MGR-UUID
            # Revisit: for non-local-bridge components, MGR-UUID will have
            # been captured on CV/CID0/SID0 write, so skip this
            core.MGRUUIDl = int.from_bytes(self.mgr_uuid.bytes[0:8],
                                           byteorder='little')
            core.MGRUUIDh = int.from_bytes(self.mgr_uuid.bytes[8:16],
                                           byteorder='little')
            self.control_write(core, genz.CoreStructure.MGRUUIDl, sz=16)
            # Revisit: read back something, to confirm we own component
            # set HostMgrMGRUUIDEnb, MGRUUIDEnb
            cap1ctl = genz.CAP1Control(core.CAP1Control, core)
            cap1ctl.field.HostMgrMGRUUIDEnb = 1 # Revisit: enum
            cap1ctl.field.MGRUUIDEnb = 1
            # set ManagerType, PrimaryFabMgrRole
            # clear PrimaryMgrRole, SecondaryFabMgrRole, PwrMgrEnb
            cap1ctl.field.ManagerType = 1
            cap1ctl.field.PrimaryMgrRole = 0
            cap1ctl.field.PrimaryFabMgrRole = 1
            cap1ctl.field.SecondaryFabMgrRole = 0
            cap1ctl.field.PwrMgrEnb = 0
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
            core.PFMCID = pfm_gcid.cid
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
            for iface in range(0, core.MaxInterface):
                self.interfaces.append(Interface(self, iface))
                iup = self.interfaces[iface].iface_init()
                if iup:
                    self.usable = True
            # Revisit: set LLMUTO, UNREQ, UNRSP, UERT, NIRT, FPST, NLMUTO
            # Revisit: set REQNIRTO, REQABNIRTO
            # Revisit: set LLReqDeadline, NLLReqDeadline, DeadlineTick
            # Revisit: set LLRspDeadline, NLLRspDeadline, RspDeadline, DRReqDeadline
            # Revisit: set ControlTO, ControlDRTO
            # set MaxRequests
            # Revisit: Why would FM choose < MaxREQSuppReqs? Only for P2P?
            core.MaxRequests = core.MaxREQSuppReqs
            self.control_write(core, genz.CoreStructure.MaxRequests, sz=8)
            # Revisit: set MaxPwrCtl (to NPWR?)
            # If component is usable, set ComponentEnb
            if self.usable:
                cctl = genz.CControl(core.CControl, core)
                cctl.field.ComponentEnb = 1
                core.CControl = cctl.val
                self.control_write(core, genz.CoreStructure.CControl, sz=8)
            else:
                if self.verbosity:
                    print('{} has no usable interfaces'.format(self.path))
            # Tell the kernel about the new/changed component
            # Revisit: don't do add_fab_comp if fab/GCID not changing
            try:
                self.add_fab_comp()
            except Exception as e:
                if self.verbosity:
                    print('add_fab_comp failed with exception {}'.format(e))
                self.usable = False
        # end with
        return self.usable

class Bridge(Component):
    def __init__(self, *args, brnum, **kwargs):
        self.brnum = brnum
        super().__init__(*args, **kwargs)

    def explore_interfaces(self):
        # examine our bridge interfaces & init those components
        for iface in self.interfaces:
            if iface.usable:
                if self.verbosity:
                    print('exploring interface {}'.format(iface.num))
                #do_something() # Revisit
            else:
                if self.verbosity:
                    print('interface{} is not usable'.format(iface.num))

    # ssdt_size is used to limit the range of random CIDs
    def ssdt_size(self):
        comp_dest_dir = list((self.path / 'control').glob(
            'component_destination_table@*'))[0]
        comp_dest_file = comp_dest_dir / 'component_destination_table'
        with comp_dest_file.open(mode='rb') as f:
            data = bytearray(f.read())
            comp_dest = self.map.fileToStruct('component_destination_table',
                                              data, fd=f.fileno(),
                                              verbosity=self.verbosity)
            ssdt_sz = comp_dest.SSDTSize
            if self.verbosity:
                print('ssdt_sz={}'.format(ssdt_sz))
            return ssdt_sz

    def update_path(self):
        if self.verbosity:
            print('current path: {}'.format(self.path))
        sys_devices = Path('/sys/devices')
        fabrics = sys_devices.glob('genz*')
        for fab_path in fabrics:
            br_paths = fab_path.glob('bridge*')
            for br_path in br_paths:
                br_num = component_num(br_path)
                if self.brnum == br_num:
                    self.path = br_path
                    if self.verbosity:
                        print('new path: {}'.format(self.path))
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
        self.bridges = []
        self.components = []
        self.rand_list = []
        self.gcid = GCID(cid=1)  # Revisit: grand plan
        if self.verbosity:
            print('fabric: {}, num={}, mgr_uuid={}'.format(path, self.fabnum,
                                                           self.mgr_uuid))

    def fab_init(self):
        br_paths = self.path.glob('bridge*')
        for br_path in br_paths:
            cuuid = get_cuuid(br_path)
            cur_gcid = get_gcid(br_path)
            brnum = component_num(br_path)
            tmp_gcid = cur_gcid if cur_gcid.sid == TEMP_SUBNET else INVALID_GCID
            br = Bridge(self, self.map, br_path, self.mgr_uuid, local_br=True,
                        brnum=brnum, dr=None,
                        tmp_gcid=tmp_gcid, netlink=self.nl,
                        verbosity=self.verbosity)
            ssdt_sz = br.ssdt_size()
            if self.accept_cids:
                hw_gcid = br.get_gcid()
                if hw_gcid is not None:
                    self.gcid = hw_gcid
                    self.random_cids = False
            if self.random_cids:
                if len(self.rand_list) == 0:
                    self.rand_list = random.sample(range(0, ssdt_sz), ssdt_sz)
                    self.rand_index = 0
                self.gcid.cid = self.rand_list[self.rand_index]
            pfm_gcid = self.gcid
            print('{}:{} bridge{} {}'.format(self.fabnum, self.gcid, brnum, cuuid))
            br.comp_init(self.gcid, pfm_gcid, self.random_cids)
            self.bridges.append(br)
            if self.random_cids:
                self.rand_index += 1
            else:
                self.gcid.cid += 1
            br.explore_interfaces()

class Conf():
    def __init__(self, file):
        self.file = file

    def read_conf_file(self):
        with open(self.file, 'r') as f:
            self.data = json.load(f)
            return self.data

    def write_conf_file(self, data):
        self.data = data
        with open(self.file, 'w') as f:
            json.dump(self.data, f, indent=2)

    def __repr__(self):
        return repr(self.data)

def get_gcid(comp_path):
    gcid = comp_path / 'gcid'
    with gcid.open(mode='r') as f:
        return GCID(str=f.read().rstrip())

def get_cuuid(comp_path):
    cuuid = comp_path / 'cuuid'
    with cuuid.open(mode='r') as f:
        return UUID(f.read().rstrip())

comp_num_re = re.compile(r'.*/([^0-9]+)([0-9]+)')

def component_num(comp_path):
    match = comp_num_re.match(str(comp_path))
    return int(match.group(2))

def main():
    global cols
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
    args = parser.parse_args()
    if args.verbosity > 5:
        print('Gen-Z version = {}'.format(args.genz_version))
    global genz
    genz = __import__('genz_{}'.format(args.genz_version.replace('.', '_')))
    nl = NetlinkManager(config='./alpaka.conf')
    map = genz.ControlStructureMap()
    conf = Conf('zephyr.conf')
    try:
        data = conf.read_conf_file()
        fab_uuid = UUID(data['fabric_uuid'])
    except FileNotFoundError:
        # create new skeleton file
        data = {}
        fab_uuid = uuid4()
        data['fabric_uuid'] = str(fab_uuid)
        conf.write_conf_file(data)
    if args.verbosity:
        print('conf={}'.format(conf))
    fabrics = {}
    if args.keyboard:
        set_trace()
    sys_devices = Path('/sys/devices')
    fab_paths = sys_devices.glob('genz*')
    for fab_path in fab_paths:
        fab = Fabric(nl, map, fab_path, random_cids=args.random_cids,
                     accept_cids=args.accept_cids, verbosity=args.verbosity)
        fabrics[fab_path] = fab
        fab.fab_init()

    if args.keyboard:
        set_trace()

if __name__ == '__main__':
    main()
