#!/usr/bin/env python3

# Copyright  ©  2020-2021 IntelliProp Inc.
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
import re
from uuid import UUID
from pathlib import Path
from importlib import import_module
from genz.genz_common import GCID
from pdb import set_trace, post_mortem
import traceback

re_ohb_first_match = re.compile('^time: (?P<time>0x[0-9a-fA-F]+)\s+' +
                                '(?P<last>last )?data: (?P<user>0x[0-9a-fA-F]+)\s+' +
                                '(?P<data>.*) first$')
re_ohb_last_match  = re.compile('^time: (?P<time>0x[0-9a-fA-F]+)\s+' +
                                'last data: (?P<user>0x[0-9a-fA-F]+)\s+' +
                                '(?P<data>.*$)')
re_ohb_other_match = re.compile('^time: (?P<time>0x[0-9a-fA-F]+)\s+' +
                                'data: (?P<user>0x[0-9a-fA-F]+)\s+' +
                                '(?P<data>.*)')
re_zmmu_match = re.compile('^Starting .*ZMMU .*Dump$')

class PacketSorter():
    def __init__(self):
        self.sorter = {}

    def append(self, pkt):
        pkt.sorter = self
        if pkt.isRequest:
            uniq = pkt.uniqueness
            self.sorter.setdefault(uniq, []).append(pkt)

    def find_request_packet(self, pkt):
        if pkt.isRequest:
            return pkt
        uniq = pkt.uniqueness
        pkt_list = self.sorter.get(uniq)
        if pkt_list is None:
            return None
        req = None
        min_diff = None
        for p in pkt_list:
            diff = pkt.cycle - p.cycle
            if diff < 0:
                continue
            elif min_diff is None or diff < min_diff:
                min_diff = diff
                req = p

        return req

    def req_rsp_sort(self, pkt):
        if pkt.isRequest:
            return pkt.cycle
        else:
            req = self.find_request_packet(pkt)
            return (req.cycle + 1) if req is not None else pkt.cycle


def parse_pkt_data(genz, args, matches, sorter):
    cycle = int(matches[0].group('time'), base=0)
    time = cycle * 2.5e-9
    user = int(matches[0].group('user'), base=0)
    data = bytearray()
    no_user = False
    for m in matches:
        dws = [int(dw, base=0) for dw in m.group('data').split()]
        if len(dws) == 7:  # no user field
            dws.insert(0, int(m.group('user'), base=0))
            no_user = True
        for dw in reversed(dws):
            data.extend(dw.to_bytes(4, 'little'))
    pkt = genz.Packet.dataToPkt(data, verbosity=args.verbosity, csv=args.csv)
    pkt.cycle = cycle
    pkt.time = time
    pkt.user = 0xff if no_user else user
    sorter.append(pkt)
    return pkt

def packet_reqrsp_sort(pkt):
    return pkt.sorter.req_rsp_sort(pkt)

def process_text(genz, args, fname):
    with open(fname) as f:
        pkts = []
        pkt_sorter = PacketSorter()
        pkt_matches = []
        in_pkt = False
        line_num = 0
        for line in f:
            line_num += 1
            m_zmmu = re_zmmu_match.match(line)
            if m_zmmu is not None:
                break
            if in_pkt:
                m_last = re_ohb_last_match.match(line)
                if m_last is not None:
                    in_pkt = False
                    pkt_matches.append(m_last)
                    pkt = parse_pkt_data(genz, args, pkt_matches, pkt_sorter)
                    pkts.append(pkt)
                    pkt_matches = []
                else:
                    m_other = re_ohb_other_match.match(line)
                    if m_other is not None:
                        pkt_matches.append(m_other)
                    else:
                        print('Warning: invalid pkt data at line {} of {}: "{}"'.format(
                            line_num, fname, line.rstrip()))
                        in_pkt = False
                        pkt_matches = []
            else:
                m_first = re_ohb_first_match.match(line)
                if m_first is not None:
                    pkt_matches.append(m_first)
                    in_pkt = True if m_first.group('last') is None else False
                    if not in_pkt:
                        pkt = parse_pkt_data(genz, args, pkt_matches, pkt_sorter)
                        pkts.append(pkt)
                        pkt_matches = []
            # end if in_pkt
        # end for line

        if args.time_sort:
            pkts.sort(key=lambda p: p.time)
        elif args.reqrsp_sort:
            pkts.sort(key=packet_reqrsp_sort)
        first = True
        prev_req = None
        for pkt in pkts:
            is_req = pkt.isRequest
            delta = 0 if first else (
                (pkt.time - prev_req.time) if is_req and prev_req is not None
                else (pkt.time - prev_pkt.time))
            first = False
            yield (pkt, delta)
            prev_pkt = pkt
            prev_req = pkt if is_req else prev_req

def process_tuser_tdata(genz, args, tuser: str, tdata: str):
    if tuser is not None:
        user = int(tuser, 16)
        no_user = False
    else:
        no_user = True
    data = bytearray.fromhex(tdata)
    data.reverse()
    pkt = genz.Packet.dataToPkt(data, verbosity=args.verbosity, csv=args.csv)
    pkt.user = 0xff if no_user else user
    return pkt


def main():
    global args
    global cols
    parser = argparse.ArgumentParser()
    #parser.add_argument('file', help='the file containing binary packet data')
    parser.add_argument('-C', '--csv', action='store_true',
                        help='output CSV format')
    parser.add_argument('-d', '--time_delta', action='store_true',
                        help='print inter-packet time delta')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-G', '--genz-version', choices=['1.1'],
                        default='1.1',
                        help='Gen-Z spec version of packets')
    parser.add_argument('-P', '--post_mortem', action='store_true',
                        help='enter debugger on uncaught exception')
    parser.add_argument('-r', '--reqrsp_sort', action='store_true',
                        help='sort output packets by matching request-response')
    parser.add_argument('-t', '--time_sort', action='store_true',
                        help='sort output packets by time')
    parser.add_argument('-T', '--text', action='store',
                        help='input file containing ohb packet text')
    parser.add_argument('--tdata', action='store',
                        help='single packet tdata field')
    parser.add_argument('--tuser', action='store',
                        help='single packet tuser field')
    parser.add_argument('--ns', action='store_true',
                        help='output times in ns')
    args = parser.parse_args()
    if args.verbosity > 5:
        print('Gen-Z version = {}'.format(args.genz_version))
    genz = import_module('genz.genz_{}'.format(args.genz_version.replace('.', '_')))
    unit = 'nS' if args.ns else 'uS'
    if args.text:
        if args.csv:
            print('Time,Delta,Intf,OpcName,OCL,OpCode,LEN,SCID,DCID,Tag,VC,PCRC,AKey,Deadline,ECN,GC,NH,PM,LP,TA,RK,DR,DRIface,RDSize,PadCNT,Addr,MGRUUID,TC,NS,UN,PU,RC,MS,PD,FPS,RRSPReason,RNR_QD,RS,Reason,ECRC')
        for pkt, delta in process_text(genz, args, args.text):
            intf = pkt.user & 0xfff
            pkt_time = pkt.time*1e9 if args.ns else pkt.time*1e6
            pkt_delta = delta*1e9 if args.ns else delta*1e6
            if args.csv:
                print(f'{pkt_time:.6f},{pkt_delta:.6f},{intf:x},{pkt}')
            elif args.time_delta:
                print(f'Time: {pkt_time:16.6f}{unit}, Delta: {pkt_delta:14.6f}{unit}, Intf: {intf:x}, {pkt}')
            else:
                print(f'Time: {pkt_time:16.6f}{unit}, Intf: {intf:x}, {pkt}')
        # end for
    elif args.tuser and args.tdata:
        pkt = process_tuser_tdata(genz, args, args.tuser, args.tdata)
        intf = pkt.user & 0xfff
        pkt_time = 0
        pkt_delta = 0
        if args.csv:
            print(f'{pkt_time:.6f},{pkt_delta:.6f},{intf:x},{pkt}')
        elif args.time_delta:
            print(f'Time: {pkt_time:16.6f}{unit}, Delta: {pkt_delta:14.6f}{unit}, Intf: {intf:x}, {pkt}')
        else:
            print(f'Time: {pkt_time:16.6f}{unit}, Intf: {intf:x}, {pkt}')
    # end if args.text

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
