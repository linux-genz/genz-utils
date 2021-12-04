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
import time
from genz.genz_common import GCID, CState, IState, RKey, PHYOpStatus, ErrSeverity
from pdb import set_trace
import zephyr_conf
from zephyr_conf import log

class Interface():
    def __init__(self, component, num, peer_iface=None):
        self.comp = component
        self.peer_iface = peer_iface
        self.num = num
        self.hvs = None
        self.lprt = None
        self.vcat = None
        self.route_info = None
        # defaults until we can read actual state
        self.istate = IState.ICFG
        self.phy_status = PHYOpStatus.PHYUp
        self.phy_tx_lwr = 0
        self.phy_rx_lwr = 0

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
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            log.debug('{}: interface{}={}'.format(self.comp.gcid, self.num, iface))
            self.hvs = iface.HVS  # for num_vcs()
        # end with
        return iface

    def iface_state(self):
        iface = self.iface_read()
        state = self.check_i_state(iface, timeout=0, do_read=False)
        self.usable = (state is IState.IUp)
        return state

    # Returns True if interface is usable - is I-Up, not I-Down/I-CFG/I-LP
    def iface_init(self, prefix='control'):
        genz = zephyr_conf.genz
        self.setup_paths(prefix)
        iface_file = self.iface_dir / 'interface'
        is_switch = self.comp.has_switch
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            log.debug('{}: iface_init interface{}={}'.format(self.comp.gcid, self.num, iface))
            self.hvs = iface.HVS
            if not self.phy_init():
                log.info('{}: interface{} is not PHY-Up'.format(
                    self.comp.gcid, self.num))
                self.usable = False
                # Revisit: should config iface even if not PHY-Up
                return False

            icap1 = genz.ICAP1(iface.ICAP1, iface)
            self.ierror_init(iface, icap1)
            # Revisit: select compatible LLR/P2PNextHdr/P2PEncrypt settings
            # Revisit: set CtlOpClassPktFiltEnb, if Switch (for now)
            # enable Explicit OpCodes, and LPRT (if Switch)
            icap1ctl = genz.ICAP1Control(iface.ICAP1Control, iface)
            icap1ctl.field.OpClassSelect = 0x1
            icap1ctl.field.LPRTEnb = is_switch
            iface.ICAP1Control = icap1ctl.val
            log.debug('{}: writing ICAP1Control'.format(self))
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
            log.debug('{}: writing LinkCTLControl'.format(self))
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
            log.debug('{}: writing IControl IfaceEnb'.format(self))
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IControl, sz=4, off=4)
            # Revisit: do we need to do this?
            istatus = genz.IStatus(0, iface)
            istatus.field.LinkRFCStatus = 1  # RW1C
            iface.IStatus = istatus.val
            log.debug('{}: writing IStatus'.format(self))
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IStatus, sz=4, off=0)
            # verify I-Up
            state = self.check_i_state(iface)
            self.usable = (state is IState.IUp)
            # Revisit: orthus goes I-Down if we do this earlier
            # set LinkRFCDisable (depending on local_br)
            ictl.field.LinkRFCDisable = 1 if self.comp.local_br else 0
            iface.IControl = ictl.val
            log.debug('{}: writing IControl LinkRFCDisable'.format(self))
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IControl, sz=4, off=4)
            # save PeerCState & PeerGCID
            self.peer_cstate = self.get_peer_cstate(iface)
            self.peer_gcid = self.get_peer_gcid(iface)
        # end with
        if is_switch:
            # initialize VCAT
            # Revisit: multiple Action columns
            log.debug('{}: writing VCAT'.format(self))
            for vc in range(0, self.hvs + 1):
                # Revisit: vc policies
                self.vcat_write(vc, (1 << vc))
        log.debug('{}: iface_init done'.format(self))
        return self.usable

    def ierror_init(self, iface, icap1):
        if icap1.field.IfaceErrFieldsSup == 0:
            return
        genz = zephyr_conf.genz
        # Set IErrorSigTgt
        ierr_tgt = genz.IErrorSigTgt(iface.IErrorSigTgt, iface)
        sig_tgt = genz.SigTgt.TgtIntr1 if self.comp.local_br else genz.SigTgt.TgtUEP
        ierr_tgt.field.ExcessivePHYRetraining = sig_tgt
        ierr_tgt.field.NonTransientLinkErr = sig_tgt
        ierr_tgt.field.IfaceContainment = sig_tgt
        ierr_tgt.field.IfaceFCFwdProgressViolation = sig_tgt
        ierr_tgt.field.UnexpectedPHYFailure = sig_tgt
        ierr_tgt.field.IfaceAE = sig_tgt
        ierr_tgt.field.SwitchPktRelayFailure = sig_tgt
        iface.IErrorSigTgt = ((ierr_tgt.val[2] << 32) |
                              (ierr_tgt.val[1] << 16) | ierr_tgt.val[0])
        log.debug('{}: writing IErrorSigTgt'.format(self))
        # Revisit: at least on orthus, sz=6 turns into an 8-byte ControlWrite
        self.comp.control_write(iface,
                            genz.InterfaceStructure.IErrorSigTgt, sz=6)
        # Set IErrorDetect - last, after other IError fields setup
        ierr_det = genz.IErrorDetect(iface.IErrorDetect, iface)
        ierr_det.field.ExcessivePHYRetraining = 1
        ierr_det.field.NonTransientLinkErr = 1
        ierr_det.field.IfaceContainment = 1
        ierr_det.field.IfaceFCFwdProgressViolation = 1
        ierr_det.field.UnexpectedPHYFailure = 1
        ierr_det.field.IfaceAE = 1
        ierr_det.field.SwitchPktRelayFailure = 1
        # Revisit: other interface errors
        iface.IErrorDetect = ierr_det.val
        log.debug('{}: writing IErrorDetect'.format(self))
        # Revisit: switch doesn't like sz=2, off=2, because at least on orthus
        # that turns into a 4-byte ControlWrite to a 2-byte-aligned addr
        #self.comp.control_write(iface,
        #                    genz.InterfaceStructure.IErrorDetect, sz=2, off=2)
        # Revisit: major side-effect - IErrorStatus is cleared (bits are RW1CS)
        self.comp.control_write(iface,
                            genz.InterfaceStructure.IErrorStatus, sz=8)

    def update_peer_info(self):
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            self.send_peer_attr1(iface)
            self.peer_cstate = self.get_peer_cstate(iface)
            self.peer_gcid = self.get_peer_gcid(iface)
            self.peer_cclass = self.get_peer_cclass(iface)
            self.peer_inband_disabled = self.get_peer_inband_mgmt_disabled(iface)
            self.peer_mgr_type = self.get_peer_mgr_type(iface)

    def send_peer_attr1(self, iface, timeout=10000):
        genz = zephyr_conf.genz
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.field.PeerAttr1Req = 1
        iface.IControl = icontrol.val
        log.debug('{}: sending Peer-Attr1'.format(self))
        self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                sz=4, off=4)
        status = self.wait_link_ctl(iface, timeout)
        icontrol.field.PeerAttr1Req = 0
        iface.IControl = icontrol.val
        return status

    def peer_c_reset(self):
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            status = self.send_peer_c_reset(iface)
        return status

    def send_peer_c_reset(self, iface, timeout=10000):
        genz = zephyr_conf.genz
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.field.PeerCReset = 1
        iface.IControl = icontrol.val
        self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                sz=4, off=4)
        status = self.wait_link_ctl(iface, timeout)
        icontrol.field.PeerCReset = 0
        iface.IControl = icontrol.val
        return status

    def send_path_time(self, iface, timeout=10000):
        genz = zephyr_conf.genz
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
        genz = zephyr_conf.genz
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

    def check_i_state(self, iface, timeout=500000000, do_read=True):
        genz = zephyr_conf.genz
        istatus = genz.IStatus(iface.IStatus, iface)
        start = time.time_ns()
        done = False
        while not done:
            if do_read:
                self.comp.control_read(iface,
                                       genz.InterfaceStructure.IStatus, sz=4)
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
        genz = zephyr_conf.genz
        # Re-read PeerState
        self.comp.control_read(iface, genz.InterfaceStructure.PeerState,
                               sz=4, off=4)
        peer_state = genz.PeerState(iface.PeerState, iface)
        peer_cstate = CState(peer_state.field.PeerCState)
        log.debug('{}: get_peer_c_state[{}]: PeerCState={!s}'.format(
            self.comp.gcid, self.num, peer_cstate))
        return peer_cstate

    def get_peer_gcid(self, iface):
        genz = zephyr_conf.genz
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
        genz = zephyr_conf.genz
        # Revisit: should this re-read value?
        # Unlike cstate & gcid, unless there's re-cabling, this can't change
        peer_state = genz.PeerState(iface.PeerState, iface)
        log.debug('{}: get_peer_iface_num[{}]: PeerIfaceIDValid={}, PeerInterfaceID={}'.format(
            self.comp.gcid, self.num,
            peer_state.field.PeerIfaceIDValid, iface.PeerInterfaceID))
        return (iface.PeerInterfaceID if peer_state.field.PeerIfaceIDValid == 1
                else None)

    def get_peer_cclass(self, iface):
        genz = zephyr_conf.genz
        # Revisit: should this re-read value?
        # Unlike cstate & gcid, unless there's re-cabling, this can't change
        peer_state = genz.PeerState(iface.PeerState, iface)
        log.debug('{}: get_peer_cclass[{}]: PeerBaseCClassValid={}, PeerCClass={}'.format(
            self.comp.gcid, self.num,
            peer_state.field.PeerBaseCClassValid, iface.PeerBaseCClass))
        return (iface.PeerBaseCClass if peer_state.field.PeerBaseCClassValid == 1
                else None)

    def get_peer_inband_mgmt_disabled(self, iface):
        genz = zephyr_conf.genz
        # Revisit: should this re-read value?
        peer_state = genz.PeerState(iface.PeerState, iface)
        return peer_state.field.PeerInbandMgmtDisabled

    def get_peer_mgr_type(self, iface):
        genz = zephyr_conf.genz
        # Revisit: should this re-read value?
        peer_state = genz.PeerState(iface.PeerState, iface)
        return peer_state.field.PeerMgrType

    @property
    def peer_comp(self):
        return self.peer_iface.comp if self.peer_iface is not None else None

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
            self.phy_status = PHYOpStatus.PHYUp
            self.phy_tx_lwr = 0
            self.phy_rx_lwr = 0
            return True # Revisit

    # Returns True if interface PHY is usable - is PHY-Up/PHY-Up-LP*
    # Also sets phy_status/phy[tx|rx]_lwr, for use by to_json()
    def phy_status_ok(self, phy):
        genz = zephyr_conf.genz
        phy_status = genz.PHYStatus(phy.PHYStatus, phy)
        op_status = phy_status.field.PHYLayerOpStatus
        self.phy_status = PHYOpStatus(op_status)
        self.phy_tx_lwr = phy_status.field.PHYTxLinkWidthReduced
        self.phy_rx_lwr = phy_status.field.PHYRxLinkWidthReduced
        return self.phy_status.up_or_uplp()

    def compute_mhc(self, cid, rt, hc, valid):
        if self.lprt is None:
            return (hc, rt != 0)
        if valid:
            # Revisit: enum
            cur_min = min(self.lprt[cid], key=lambda x: x.HC if x.V else 63)
            cur_min = cur_min.HC if cur_min.V else 63
            new_min = min(cur_min, hc)
        else:
            cur_min = self.lprt[cid][0].MHC
            new_min = min((self.lprt[cid][i] for i in range(len(self.lprt[cid]))
                          if i != rt), key=lambda x: x.HC if x.V else 63)
            new_min = new_min.HC if new_min.V else 63
        return (new_min, new_min != cur_min and rt != 0)

    def lprt_read(self):
        if self.lprt_dir is None:
            return
        if self.lprt is not None:
            return
        from zephyr_route import RouteInfo
        # Revisit: avoid open/close (via "with") on every read?
        lprt_file = self.lprt_dir / 'lprt'
        with lprt_file.open(mode='rb+', buffering=0) as f:
            data = bytearray(f.read())
            self.lprt = self.comp.map.fileToStruct('lprt', data,
                                path=lprt_file, core=self.comp.core,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            self.route_info = [[RouteInfo() for j in range(self.lprt.cols)]
                               for i in range(self.lprt.rows)]
        # end with

    def lprt_write(self, cid, ei, rt=0, valid=1, mhc=None, hc=None, vca=None,
                   mhcOnly=False):
        if self.lprt_dir is None:
            return
        from zephyr_route import RouteInfo
        # Revisit: avoid open/close (via "with") on every write?
        lprt_file = self.lprt_dir / 'lprt'
        with lprt_file.open(mode='rb+', buffering=0) as f:
            if self.lprt is None:
                data = bytearray(f.read())
                self.lprt = self.comp.map.fileToStruct('lprt', data,
                                path=lprt_file, core=self.comp.core,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
                self.route_info = [[RouteInfo() for j in range(self.lprt.cols)]
                                   for i in range(self.lprt.rows)]
            else:
                self.lprt.set_fd(f)
            sz = ctypes.sizeof(self.lprt.element)
            self.lprt[cid][rt].MHC = mhc if (mhc is not None and rt == 0) else 0
            if not mhcOnly:
                self.lprt[cid][rt].EI = ei
                self.lprt[cid][rt].V = valid
                self.lprt[cid][rt].HC = hc if hc is not None else 0
                self.lprt[cid][rt].VCA = vca if vca is not None else 0
            self.comp.control_write(self.lprt, self.lprt.element.MHC,
                                    off=self.lprt.cs_offset(cid, rt), sz=sz)
        # end with

    def vcat_write(self, vc, vcm, action=0, th=None):
        if self.vcat_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        vcat_file = self.vcat_dir / 'vcat'
        with vcat_file.open(mode='rb+', buffering=0) as f:
            if self.vcat is None:
                data = bytearray(f.read())
                self.vcat = self.comp.map.fileToStruct('vcat', data,
                                path=vcat_file, core=self.comp.core,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            else:
                self.vcat.set_fd(f)
            sz = ctypes.sizeof(self.vcat.element)
            self.vcat[vc][action].VCM = vcm
            if th is not None and sz == 8:
                self.vcat[vc][action].TH = th
            self.comp.control_write(self.vcat, self.vcat.element.VCM,
                                    off=self.vcat.cs_offset(vc, action), sz=sz)
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

    @property
    def boundary_interface(self):
        comp = self.comp
        dot_num = '.{}'.format(self.num)
        cs_name = comp.cuuid_serial + dot_num
        gc_name = str(comp.gcid) + dot_num
        return any(x in comp.fab.conf.data.get('boundary_interfaces', [])
                   for x in {cs_name, gc_name})

    def to_json(self):
        return { 'num': str(self),
                 'state': str(self.istate),
                 'phy': { 'status': str(self.phy_status),
                          'tx_LWR': self.phy_tx_lwr,
                          'rx_LWR': self.phy_rx_lwr }
                }

    def __hash__(self):
        return hash(str(self.comp.uuid) + '.{}'.format(self.num))

    def __repr__(self):
        return '{}({}.{})'.format(self.__class__.__name__,
                                  self.comp.gcid, self.num)

    def __str__(self):
        return '{}.{}'.format(self.comp.gcid, self.num)
