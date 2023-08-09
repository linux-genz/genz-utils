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
from typing import List, Tuple, Iterator
from genz.genz_common import GCID, CState, IState, AKey, RKey, PHYOpStatus, ErrSeverity, RefCount, MAX_HC, AllOnesData
from pdb import set_trace
import zephyr_conf
from zephyr_conf import log

class Interface():
    def __init__(self, component, num, peer_iface=None, usable=False):
        self.comp = component
        self.set_peer_iface(peer_iface, init=True)
        self.num = num
        self.hvs = None
        self.lprt = None
        self.vcat = None
        self.istats = None
        self.route_info = None
        self.peer_nonce = None
        # defaults until we can read actual state
        self.usable = usable
        self.istate = IState.ICFG
        self.phy_status = PHYOpStatus.PHYUp
        self.phy_tx_lwr = 0
        self.phy_rx_lwr = 0
        self.mod_timestamp = None
        self.ingress_akey_mask_refcount = RefCount((64, 1))
        self.egress_akey_mask_refcount = RefCount((64, 1))

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
        try:
            self.istats_dir = list(self.iface_dir.glob('interface_statistics@*'))[0]
        except IndexError:
            self.istats_dir = None

    def iface_read(self, prefix='control'):
        self.setup_paths(prefix)
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            if iface.all_ones_type_vers_size():
                raise AllOnesData('interface structure returned all-ones data')
            log.debug(f'{self}: interface{self.num}={iface}')
            self.hvs = iface.HVS  # for num_vcs()
        # end with
        return iface

    def iface_state(self, ts=None) -> Tuple:
        iface = self.iface_read()
        state, changed = self.check_i_state(iface, do_read=False, ts=ts)
        self.usable = (state is IState.IUp)
        return (state, changed)

    def warn_unusable(self, msg: str) -> bool:
        log.warning(f'{self}: {msg}')
        self.usable = False
        return False

    # Returns True if interface is usable - is I-Up, not I-Down/I-CFG/I-LP
    def iface_init(self, prefix='control', no_akeys=False):
        genz = zephyr_conf.genz
        self.setup_paths(prefix)
        iface_file = self.iface_dir / 'interface'
        is_switch = self.comp.has_switch
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            if iface.all_ones_type_vers_size():
                return self.warn_unusable(
                    f'iface_init interface{self.num} returned all-ones data')
            log.debug(f'{self}: iface_init interface{self.num}={iface}')
            self.hvs = iface.HVS
            if not self.phy_init()[0]:
                log.info(f'{self}: interface{self.num} is not PHY-Up')
                self.usable = False
                # Revisit: should config iface even if not PHY-Up
                return False

            icap1 = genz.ICAP1(iface.ICAP1, iface)
            self.ierror_init(iface, icap1)
            # Revisit: select compatible LLR/P2PNextHdr/P2PEncrypt settings
            # Revisit: set CtlOpClassPktFiltEnb, if Switch (for now)
            # enable Explicit OpCodes, LPRT (if Switch), and IErrFaultInjEnb
            try:
                icap1ctl = genz.ICAP1Control(iface.ICAP1Control, iface, check=True)
            except AllOnesData:
                return self.warn_unusable('ICAP1Control is all-ones')
            icap1ctl.field.OpClassSelect = 0x1
            icap1ctl.field.LPRTEnb = is_switch
            icap1ctl.field.IErrFaultInjEnb = 1 # Revisit: Always?
            iface.ICAP1Control = icap1ctl.val
            log.debug(f'{self}: writing ICAP1Control={icap1ctl.val:#x}')
            self.comp.control_write(iface,
                            genz.InterfaceStructure.ICAP1Control, sz=4, off=4)
            # set LinkCTLControl (depending on local_br, is_switch)
            try:
                lctl = genz.LinkCTLControl(iface.LinkCTLControl, iface, check=True)
            except AllOnesData:
                return self.warn_unusable('LinkCTLControl is all-ones')
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
            log.debug(f'{self}: writing LinkCTLControl={lctl.val:#x}')
            self.comp.control_write(iface,
                            genz.InterfaceStructure.LinkCTLControl, sz=4, off=4)
            # send Peer-Attribute 1 Link CTL - HW did this at link-up time,
            # but we don't know when that was, and things may have changed
            status = self.send_peer_attr1(iface, timeout=100000)
            if status == 0:
                return self.warn_unusable(
                    f'send_peer_attr1 timeout on interface{self.num}')
            # send Path Time Link CTL
            status = self.send_path_time(iface, timeout=100000)
            if status == 0:
                log.warning(f'{self}: send_path_time timeout on interface{self.num}')
            # save PeerInterfaceID
            self.peer_iface_num = self.get_peer_iface_num(iface)
            try:
                ictl = genz.IControl(iface.IControl, iface, check=True)
            except AllOnesData:
                return self.warn_unusable('IControl is all-ones')
            # set IfaceAKeyValidationEnb (if supported and not --no-akeys)
            ictl.IfaceAKeyValidationEnb = (1 if not no_akeys and
                                           icap1.IfaceAKeyValidationSup else 0)
            # Revisit: set Ingress/Egress AKeyMask
            # Revisit: set IngressDREnb only when needed
            ictl.field.IngressDREnb = 1
            # set auto-stop
            ictl.AutoStop = 1
            # enable interface
            ictl.field.IfaceEnb = 1
            iface.IControl = ictl.val
            log.debug(f'{self}: writing IControl IfaceEnb/IngressDREnb/AutoStop={ictl.val:#x}')
            self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                    sz=4, off=4, check=True)
            # clear IStatus RW1C bits that we might care about later
            istatus = genz.IStatus(0, iface) # all 0 IStatus
            istatus.field.FullIfaceReset = 1
            istatus.field.WarmIfaceReset = 1
            istatus.field.LinkRFCStatus = 1
            istatus.field.PeerLinkRFCReady = 1
            istatus.field.ExceededTransientErrThresh = 1
            istatus.field.LUpToLLPTransitionFailed = 1
            istatus.field.IfaceContainment = 1
            iface.IStatus = istatus.val
            log.debug(f'{self}: writing IStatus={istatus.val:#x}')
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IStatus, sz=4, off=0)
            # verify I-Up
            try:
                state = self.check_i_state(iface)[0]
            except AllOnesData:
                return self.warn_unusable('check_i_state all-ones')
            self.usable = (state is IState.IUp)
            # Revisit: orthus goes I-Down if we do this earlier
            # set LinkRFCDisable (depending on local_br)
            ictl.field.LinkRFCDisable = 1 if self.comp.local_br else 0
            iface.IControl = ictl.val
            log.debug(f'{self}: writing IControl LinkRFCDisable={ictl.val:#x}')
            self.comp.control_write(iface,
                            genz.InterfaceStructure.IControl, sz=4, off=4)
            # save PeerCState & PeerGCID
            self.peer_cstate = self.get_peer_cstate(iface)
            self.peer_gcid = self.get_peer_gcid(iface)
            if (self.peer_iface is not None and not
                self.peer_comp.is_unreachable(self.comp.fab.pfm)):
                nonce_valid = self.nonce_exchange(iface)
                if not nonce_valid:
                    log.warning(f'{self}: invalid nonce exchange')
        # end with
        self.istats_write(enb=True)
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
        if icap1.IfaceErrFieldsSup == 0:
            return
        genz = zephyr_conf.genz
        # Set IErrorSigTgt
        try:
            ierr_tgt = genz.IErrorSigTgt(iface.IErrorSigTgt, iface, check=True)
        except AllOnesData:
            return self.warn_unusable('IErrorSigTgt is all-ones')
        sig_tgt = genz.SigTgt.TgtIntr1 if self.comp.local_br else genz.SigTgt.TgtUEP
        tgt_none = genz.SigTgt.TgtNone
        ierr_tgt.ExcessivePHYRetraining = sig_tgt
        ierr_tgt.NonTransientLinkErr = sig_tgt
        ierr_tgt.IfaceContainment = sig_tgt
        ierr_tgt.IfaceAKEYViolation = tgt_none # Revisit: AKeys
        ierr_tgt.IfaceFCFwdProgressViolation = sig_tgt
        ierr_tgt.UnexpectedPHYFailure = sig_tgt
        ierr_tgt.P2PSECE = tgt_none
        ierr_tgt.IfaceAE = sig_tgt
        ierr_tgt.SwitchPktRelayFailure = sig_tgt
        iface.IErrorSigTgt = ((ierr_tgt.val[2] << 32) |
                              (ierr_tgt.val[1] << 16) | ierr_tgt.val[0])
        log.debug('{}: writing IErrorSigTgt'.format(self))
        # Revisit: sz=6 on orthus causes it to clear TETH/TETE/FCFWDProgress
        #self.comp.control_write(iface, genz.InterfaceStructure.IErrorSigTgt,
        #                        sz=6)
        self.comp.control_write(iface, genz.InterfaceStructure.IErrorSigTgt,
                                sz=8)
        # Set IErrorDetect - last, after other IError fields setup
        try:
            ierr_det = genz.IErrorDetect(iface.IErrorDetect, iface, check=True)
        except AllOnesData:
            return self.warn_unusable('IErrorDetect is all-ones')
        ierr_det.ExcessivePHYRetraining = 1
        ierr_det.NonTransientLinkErr = 1
        ierr_det.IfaceContainment = 1
        ierr_det.IfaceAKEYViolation = 0 # Revisit: AKeys
        ierr_det.IfaceFCFwdProgressViolation = 1
        ierr_det.UnexpectedPHYFailure = 1
        ierr_det.P2PSECE = 0
        ierr_det.IfaceAE = 1
        ierr_det.SwitchPktRelayFailure = 1
        iface.IErrorDetect = ierr_det.val
        log.debug(f'{self}: writing IErrorDetect={ierr_det.val:#x}')
        # Revisit: switch doesn't like sz=2, off=2, because at least on orthus
        # that turns into a 4-byte ControlWrite to a 2-byte-aligned addr
        #self.comp.control_write(iface,
        #                    genz.InterfaceStructure.IErrorDetect, sz=2, off=2)
        # Revisit: major side-effect - IErrorStatus is cleared (bits are RW1CS)
        self.comp.control_write(iface, genz.InterfaceStructure.IErrorStatus,
                                sz=4)

    def clear_ierror_status(self, bitNum: int) -> None:
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            if iface.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
            genz = zephyr_conf.genz
            ierror_status = genz.IErrorStatus(iface.IErrorStatus, iface,
                                              check=True)
            iface.IErrorStatus = (1 << bitNum)  # bits are RW1CS
            log.debug(f'{self}: writing IErrorStatus={iface.IErrorStatus:#x}, was {ierror_status.val:#x}')
            # Revisit: really want sz=2, but that doesn't work on orthus
            self.comp.control_write(iface, genz.InterfaceStructure.IErrorStatus,
                                    sz=4)
        # end with

    def nonce_exchange(self, iface) -> bool:
        '''Do nonce exchange between this interface and its peer, where
        this interface has already been opened & read.
        '''
        args = zephyr_conf.args
        # do nonce init of peer
        try:
            self.peer_iface.do_nonce_init(sendNonce=False, noNonce=args.no_nonce)
        except Exception as e:  # Revisit: restrict to specific exceptions
            # unable to talk to peer interface from PFM
            log.warning(f'{self}: exception during nonce init of peer {self.peer_iface} - {e}')
            return False
        # do nonce init and exchange
        try:
            nonce_valid = self.nonce_init(iface, sendNonce=True,
                                          noNonce=args.no_nonce)
        except AllOnesData as e:
            log.warning(f'{self}: exception during nonce init - {e}')
            return False
        return nonce_valid

    def do_nonce_exchange(self) -> bool:
        '''Do nonce exchange between this interface and its peer, where
        neither interface has been opened & read.
        '''
        args = zephyr_conf.args
        # do nonce init of peer
        try:
            self.peer_iface.do_nonce_init(sendNonce=False, noNonce=args.no_nonce)
        except AllOnesData as e:
            log.warning(f'{self}: exception during nonce init of peer {self.peer_iface} - {e}')
            return False
        # do nonce init and exchange
        try:
            nonce_valid = self.do_nonce_init(sendNonce=True, noNonce=args.no_nonce)
        except AllOnesData as e:
            log.warning(f'{self}: exception during nonce init - {e}')
            return False
        return nonce_valid

    def do_nonce_init(self, sendNonce=True, noNonce=False) -> bool:
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            if iface.all_ones_type_vers_size():
                raise AllOnesData('interface structure returned all-ones data')
            status = self.nonce_init(iface, sendNonce=sendNonce, noNonce=noNonce)
        return status

    def nonce_init(self, iface, sendNonce=True, noNonce=False) -> bool:
        log.debug(f'{self}: nonce_init, sendNonce={sendNonce}, noNonce={noNonce}')
        try:
            self.peer_nonce = self.peer_comp.nonce
        except AttributeError:
            log.debug(f'{self}: no peer_comp yet')
            return False
        genz = zephyr_conf.genz
        icap1ctl = genz.ICAP1Control(iface.ICAP1Control, iface, check=True)
        # (temporarily) disable PeerNonceValidationEnb
        icap1ctl.PeerNonceValidationEnb = 0
        iface.ICAP1Control = icap1ctl.val
        self.comp.control_write(iface,
                            genz.InterfaceStructure.ICAP1Control, sz=4, off=4)
        if noNonce:
            return True # claim valid when explicitly disabled
        # write PeerNonce
        iface.PeerNonce = self.peer_nonce
        self.comp.control_write(iface,
                            genz.InterfaceStructure.PeerNonce, sz=8)
        # (re)enable PeerNonceValidationEnb
        icap1ctl.PeerNonceValidationEnb = 1
        iface.ICAP1Control = icap1ctl.val
        self.comp.control_write(iface,
                            genz.InterfaceStructure.ICAP1Control, sz=4, off=4)
        # initiate nonce exchange if sendNonce is True
        if sendNonce:
            return self.send_nonce_exchange(iface)
        return False

    def update_peer_info(self):
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            if iface.all_ones_type_vers_size():
                raise AllOnesData(f'{self}: all-ones data')
            self.send_peer_attr1(iface)
            self.peer_cstate = self.get_peer_cstate(iface)
            self.peer_gcid = self.get_peer_gcid(iface)
            self.peer_cclass = self.get_peer_cclass(iface)
            self.peer_inband_disabled = self.get_peer_inband_mgmt_disabled(iface)
            self.peer_mgr_type = self.get_peer_mgr_type(iface)

    def send_peer_attr1(self, iface, timeout=10000): # timeout in ns
        genz = zephyr_conf.genz
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.field.PeerAttr1Req = 1
        iface.IControl = icontrol.val
        log.debug(f'{self}: sending Peer-Attr1')
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
            if iface.all_ones_type_vers_size():
                raise AllOnesData('interface structure returned all-ones data')
            status = self.send_peer_c_reset(iface)
        return status

    def send_peer_c_reset(self, iface, timeout=10000): # timeout in ns
        genz = zephyr_conf.genz
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.field.PeerCReset = 1
        iface.IControl = icontrol.val
        self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                sz=4, off=4)
        status = self.wait_link_ctl(iface, timeout)
        # Revisit: wait for peer to no longer be C-Up
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

    def send_nonce_exchange(self, iface, timeout=10000) -> bool:
        genz = zephyr_conf.genz
        icontrol = genz.IControl(iface.IControl, iface)
        icontrol.PeerNonceReq = 1
        iface.IControl = icontrol.val
        self.comp.control_write(iface, genz.InterfaceStructure.IControl,
                                sz=4, off=4)
        status = self.wait_link_ctl(iface, timeout)
        icontrol.PeerNonceReq = 0
        iface.IControl = icontrol.val
        if status != 1: # Revisit: enum
            return False
        istatus = genz.IStatus(iface.IStatus, iface)
        return istatus.PeerNonceDetected == 1

    def wait_link_ctl(self, iface, timeout):
        genz = zephyr_conf.genz
        istatus = genz.IStatus(iface.IStatus, iface)
        start = time.time_ns()
        done = False
        while not done:
            self.comp.control_read(iface, genz.InterfaceStructure.IStatus, sz=4)
            istatus.val = iface.IStatus
            log.debug(f'{self}: wait_link_ctl: completed={istatus.field.LinkCTLCompleted}, status={istatus.field.LinkCTLComplStatus}')
            now = time.time_ns()
            done = (((now - start) > timeout) or
                    (istatus.field.LinkCTLCompleted == 1))
        return istatus.field.LinkCTLComplStatus

    def check_i_state(self, iface, timeout=500000000, do_read=True,
                      expected = [IState.IUp, IState.ILP], ts=None) -> Tuple:
        prev_istate = self.istate
        genz = zephyr_conf.genz
        istatus = genz.IStatus(iface.IStatus, iface)
        start = time.time_ns()
        done = False
        while not done:
            if do_read:
                self.comp.control_read(iface, genz.InterfaceStructure.IStatus,
                                       sz=4, check=True)
            istatus.val = iface.IStatus
            istate = IState(istatus.field.IState)
            log.debug(f'{self}: check_i_state: state={istate}')
            now = time.time_ns()
            done = ((not do_read) or ((now - start) > timeout) or
                    (istate in expected))
        self.istate = istate
        self.conditional_update_mod_timestamp(prev_istate, istate,
                                              ts=now if ts is None else ts)
        return (istate, prev_istate != istate)

    def conditional_update_mod_timestamp(self, prev, cur, ts=None):
        if prev != cur:
            if ts is None:
                ts = time.time_ns()
            self.mod_timestamp = ts
            self.comp.fab.update_mod_timestamp(ts=ts)

    def get_peer_cstate(self, iface):
        genz = zephyr_conf.genz
        # Re-read PeerState
        self.comp.control_read(iface, genz.InterfaceStructure.PeerState,
                               sz=4, off=4)
        peer_state = genz.PeerState(iface.PeerState, iface)
        peer_cstate = CState(peer_state.field.PeerCState)
        log.debug('{}: get_peer_c_state: PeerCState={!s}'.format(
            self, peer_cstate))
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
        log.debug(f'{self}: get_peer_gcid: PeerGCID={peer_gcid}')
        return peer_gcid

    def get_peer_iface_num(self, iface):
        genz = zephyr_conf.genz
        # Revisit: should this re-read value?
        # Unlike cstate & gcid, unless there's re-cabling, this can't change
        peer_state = genz.PeerState(iface.PeerState, iface)
        log.debug(f'{self}: get_peer_iface_num: PeerIfaceIDValid={peer_state.field.PeerIfaceIDValid}, PeerInterfaceID={iface.PeerInterfaceID}')
        return (iface.PeerInterfaceID if peer_state.field.PeerIfaceIDValid == 1
                else None)

    def get_peer_cclass(self, iface):
        genz = zephyr_conf.genz
        # Revisit: should this re-read value?
        # Unlike cstate & gcid, unless there's re-cabling, this can't change
        peer_state = genz.PeerState(iface.PeerState, iface)
        log.debug(f'{self}: get_peer_cclass: PeerBaseCClassValid={peer_state.field.PeerBaseCClassValid}, PeerCClass={iface.PeerBaseCClass}')
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

    def set_peer_iface(self, peer_iface, init=False) -> None:
        if not init and self.peer_iface is not None:
            self.peer_iface.peer_iface = None
        self.peer_iface = peer_iface
        if peer_iface is not None:
            peer_iface.peer_iface = self

    @property
    def peer_comp(self):
        return self.peer_iface.comp if self.peer_iface is not None else None

    def phy_init(self) -> Tuple:
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
                if phy.all_ones_type_vers_size():
                    raise AllOnesData(f'{self}: PHY all-ones data')
                log.debug(f'{self}: phy={phy}')
                return self.phy_status_ok(phy)
        except IndexError:
            log.debug(f'{self}: phy missing - assume PHY-Up')
            self.phy_status = PHYOpStatus.PHYUp
            self.phy_tx_lwr = 0
            self.phy_rx_lwr = 0
            return (True, False) # Revisit

    # Returns Tuple: (phy_usable, phy_changed)
    # phy_usable: True if interface PHY is usable - is PHY-Up/PHY-Up-LP*
    # phy_changed: True if prev status/tx_lwr/rx_lwr != current status
    # Also sets phy_status/phy[tx|rx]_lwr, for use by to_json()
    def phy_status_ok(self, phy) -> Tuple:
        prev_state = (self.phy_status, self.phy_tx_lwr, self.phy_rx_lwr)
        genz = zephyr_conf.genz
        phy_status = genz.PHYStatus(phy.PHYStatus, phy)
        op_status = phy_status.field.PHYLayerOpStatus
        self.phy_status = PHYOpStatus(op_status)
        self.phy_tx_lwr = phy_status.field.PHYTxLinkWidthReduced
        self.phy_rx_lwr = phy_status.field.PHYRxLinkWidthReduced
        cur_state = (self.phy_status, self.phy_tx_lwr, self.phy_rx_lwr)
        self.conditional_update_mod_timestamp(prev_state, cur_state)
        return (self.phy_status.up_or_uplp(), prev_state != cur_state)

    def compute_mhc_hc(self, cid: int, rt: int, hc: int, valid: int):
        if self.lprt is None:
            return (hc, hc, valid, rt != 0, False)
        row = self.lprt[cid]
        info = self.route_info[cid][rt]
        return self.comp.compute_mhc_hc_row(row, info, cid, rt, hc, valid)

    def lprt_read(self, force: bool = False, verbosity: int = None):
        if self.lprt_dir is None:
            return
        if self.lprt is not None and not force:
            return
        if verbosity is None:
            verbosity = self.comp.verbosity
        from zephyr_route import RouteInfo
        # Revisit: avoid open/close (via "with") on every read?
        lprt_file = self.lprt_dir / 'lprt'
        with lprt_file.open(mode='rb+', buffering=0) as f:
            data = bytearray(f.read())
            self.lprt = self.comp.map.fileToStruct('lprt', data,
                                path=lprt_file, core=self.comp.core,
                                fd=f.fileno(), verbosity=verbosity)
            if self.route_info is None:
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

    def istats_write(self, enb=True, reset=False, snapshot=False):
        if self.istats_dir is None:
            return
        # Revisit: avoid open/close (via "with") on every write?
        istats_file = self.istats_dir / 'interface_statistics'
        with istats_file.open(mode='rb+', buffering=0) as f:
            if self.istats is None:
                data = bytearray(f.read())
                self.istats = self.comp.map.fileToStruct('interface_statistics',
                                data, path=istats_file, core=self.comp.core,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
                if self.istats.all_ones_type_vers_size():
                    raise AllOnesData(f'{self}: interface stats all-ones data')
            else:
                self.istats.set_fd(f)
            genz = zephyr_conf.genz
            istat_ctl = genz.IStatControl(self.istats.IStatControl, self.istats,
                                          check=True)
            istat_ctl.StatsEnb = int(enb)
            istat_ctl.StatsReset = int(reset)
            istat_ctl.InitiateStatsSnapshot = int(snapshot)
            self.istats.IStatControl = istat_ctl.val
            log.debug(f'{self}: writing IStatControl, val={istat_ctl.val:#x}')
            # Revisit: current control-oc HW is broken for sz < 4
            #self.comp.control_write(self.istats,
            #                    genz.InterfaceStatisticsStructure.IStatControl,
            #                    sz=1, off=6)
            self.istats.IStatStatus = 0
            self.comp.control_write(self.istats,
                                genz.InterfaceStatisticsStructure.IStatCAP1,
                                sz=4, off=4)
            # Revisit: implement snapshots
        #end with

    def update_ingress_akey_mask(self, akey: AKey, enable: bool,
                                 refcountOnly: bool = False):
        if enable:
            doWrite = self.ingress_akey_mask_refcount.inc(akey)
        else:
            doWrite = self.ingress_akey_mask_refcount.dec(akey)
        if not doWrite or refcountOnly:
            return
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            if iface.all_ones_type_vers_size():
                raise AllOnesData('interface structure returned all-ones data')
            if enable:
                iface.IngressAKeyMask |= akey.mask
            else:
                iface.IngressAKeyMask &= ~akey.mask
            self.comp.control_write(iface, type(iface).IngressAKeyMask, sz=8)
        # end with

    def update_egress_akey_mask(self, akey: AKey, enable: bool,
                                refcountOnly: bool = False):
        if enable:
            doWrite = self.egress_akey_mask_refcount.inc(akey)
        else:
            doWrite = self.egress_akey_mask_refcount.dec(akey)
        if not doWrite or refcountOnly:
            return
        iface_file = self.iface_dir / 'interface'
        with iface_file.open(mode='rb+') as f:
            data = bytearray(f.read())
            iface = self.comp.map.fileToStruct('interface', data,
                                fd=f.fileno(), verbosity=self.comp.verbosity)
            if iface.all_ones_type_vers_size():
                raise AllOnesData('interface structure returned all-ones data')
            if enable:
                iface.EgressAKeyMask |= akey.mask
            else:
                iface.EgressAKeyMask &= ~akey.mask
            self.comp.control_write(iface, type(iface).EgressAKeyMask, sz=8)
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

    def update_istats_dir(self):
        if self.istats_dir is None:
            return
        self.istats_dir = list(self.iface_dir.glob('interface_statistics@*'))[0]
        log.debug('new istats_dir = {}'.format(self.istats_dir))

    def update_path(self, prefix=None):
        if prefix is not None:
            self._prefix = prefix
        log.debug('iface{}: current path: {}'.format(self.num, self.iface_dir))
        self.iface_dir = list((self.comp.path / self._prefix / 'interface').glob(
            'interface{}@*'.format(self.num)))[0]
        log.debug('iface{}: new path: {}'.format(self.num, self.iface_dir))
        self.update_lprt_dir()
        self.update_vcat_dir()
        self.update_istats_dir()

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
                 'usable': self.usable,
                 'mod_timestamp': self.mod_timestamp,
                 'phy': { 'status': str(self.phy_status),
                          'tx_LWR': self.phy_tx_lwr,
                          'rx_LWR': self.phy_rx_lwr }
                }

    def __eq__(self, other):
        if isinstance(other, Interface):
            return self.comp == other.comp and self.num == other.num
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, Interface):
            if self.comp != other.comp:
                return NotImplemented
            return self.num < other.num
        return NotImplemented

    def __hash__(self):
        return hash(str(self.comp.uuid) + '.{}'.format(self.num))

    def __repr__(self):
        return '{}({}.{})'.format(self.__class__.__name__,
                                  self.comp.gcid, self.num)

    def __str__(self):
        return '{}.{}'.format(self.comp.gcid, self.num)
