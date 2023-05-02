#!/usr/bin/env python3

# Copyright  ©  2020-2022 IntelliProp Inc.
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
import ctypes
import json
import requests
import time
from uuid import UUID
from importlib import import_module
from genz.genz_common import GCID
from pdb import set_trace, post_mortem
import traceback

def send_fake_uep(url, js):
    hdrs = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    msg = requests.post(url, json=js)
    return msg

def main():
    global args
    global cols
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--event', action='store', default=None,
                        help='UEP event type')
    parser.add_argument('-g', '--gcid', action='store', default=None,
                        help='UEP GCID')
    parser.add_argument('--es', action='store', type=int,
                        default=None, help='UEP event-specific data')
    parser.add_argument('--event-id', action='store', type=int,
                        default=None, help='UEP event-id')
    parser.add_argument('-i', '--iface', action='store', type=int,
                        default=None, help='UEP interface')
    parser.add_argument('-l', '--local', action='store_true',
                        help='locally generated UEP')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-G', '--genz-version', choices=['1.1'],
                        default='1.1', help='Gen-Z spec version')
    parser.add_argument('-P', '--post_mortem', action='store_true',
                        help='enter debugger on uncaught exception')
    parser.add_argument('--br-gcid', action='store', default=None,
                        help='UEP target bridge GCID')
    parser.add_argument('--rc-gcid', action='store', default=None,
                        help='UEP RC GCID')
    parser.add_argument('--mgr-uuid', action='store', default=None,
                        help='manager uuid')
    parser.add_argument('url', help='post UEP json to this zephyr fabric/uep url')
    args = parser.parse_args()
    if args.verbosity > 5:
        print('Gen-Z version = {}'.format(args.genz_version))
    genz = import_module('genz.genz_{}'.format(args.genz_version.replace('.', '_')))
    uep_rec = genz.UEPEventRecord()
    if args.gcid is not None:
        gcid = GCID(str=args.gcid)
        uep_rec.SCID = gcid.cid
        uep_rec.SSID = gcid.sid
        uep_rec.GC = 1 if gcid.sid != 0 else 0 # Revisit
    if args.iface is not None:
        uep_rec.IfaceID = args.iface
        uep_rec.IV = 1
    if args.rc_gcid is not None:
        rc_gcid = GCID(str=args.rc_gcid)
        uep_rec.RCCID = rc_gcid.cid
        uep_rec.RCSID = rc_gcid.sid
        uep_rec.CV = 1
        uep_rec.SV = 1 if rc_gcid.sid != 0 else 0 # Revisit
    if args.event is not None:
        if isinstance(args.event, int):
            event = args.event
        else:
            try:
                event = genz.eventType[args.event]
            except KeyError:
                print(f'unknown event type: {args.event}')
                return
        uep_rec.Event = event
    if args.es is not None:
        uep_rec.ES = args.es
    if args.event_id is not None:
        uep_rec.EventID = args.event_id
    br_gcid = GCID(str=args.br_gcid)
    mgr_uuid = UUID(args.mgr_uuid)
    flags = 0x22  # Revisit: GENZ_UEP_INFO_VERS | ts_valid
    flags |= 0x10 if args.local else 0
    now = time.time_ns()
    attrs = { 'GENZ_A_UEP_MGR_UUID'    : str(mgr_uuid),
              'GENZ_A_UEP_BRIDGE_GCID' : br_gcid.val,
              'GENZ_A_UEP_FLAGS'       : flags,
              'GENZ_A_UEP_TS_SEC'      : int(now / 1000000000),
              'GENZ_A_UEP_TS_NSEC'     : now % 1000000000,
              'GENZ_A_UEP_REC'         : uep_rec.to_json() }
    if args.verbosity > 0:
        print(f'sending fake UEP: {attrs} to {args.url}')
    res = send_fake_uep(args.url, attrs)
    if args.verbosity > 0:
        print(f'{res}, {res.text}')

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
