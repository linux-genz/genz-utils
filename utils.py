#!/usr/bin/env python3

# Copyright  ©  2020-2024 IntelliProp Inc.
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

from uuid import UUID
from pdb import set_trace, post_mortem
from textwrap import fill
import genz.genz_1_1 as genz

def range(rng: str):
    spl = rng.split('-')
    hi = int(spl[1], base=16)
    lo = int(spl[0], base=16)
    sz = hi - lo + 1
    print(f'range: {lo:#08x}-{hi:#08x} = {sz} ({sz/(1<<20)}MiB)')

class Foo:
    def arg_test(self, **kwargs):
        for k, v in kwargs.items():
            print(f'k={k}, v={v}')

def make_pkts():
    pkt_list = []
    payload3 = bytearray('IntelliProp, Inc.', 'utf-8')
    payLen3 = len(payload3)

    fields0 = { 'VC': 1, 'SCID': 0x5, 'DCID': 0x11, 'RDSize': payLen3,
                'AKey': 1, 'Deadline': 222, 'PM': 1 }
    pkt0 = genz.PacketFactory('Core64', 'Read', verbosity=1,
                              RK=True, RKey=0x01020304, Tag=9, **fields0)
    pkt0.Addr = 0xfedcba9876543210
    pkt0.set_crcs()
    pkt_list.append(pkt0)

    fields1 = { 'VC': 1, 'SCID': 0x5, 'DCID': 0x22, 'RDSize': 16, 'GC': 1,
                'SSID': 0x1234, 'DSID': 0xabcd, 'AKey': 1, 'Deadline': 422 }
    pkt1 = genz.PacketFactory('Control', 'Read', verbosity=1,
                              RK=True, RKey=0x01020304, Tag=7, **fields1)
    pkt1.MGRUUID = UUID('849b7e6a-e0a1-4676-941f-64a5dec8bb07')
    pkt1.Addr = 0x123456789abcd
    pkt1.set_crcs()
    pkt_list.append(pkt1)

    payload2 = bytearray('Hello World', 'ascii')
    fields2 = { 'VC': 1, 'SCID': 0x5, 'DCID': 0x10, 'Deadline': 422 }
    pkt2 = genz.PacketFactory('Control', 'Write', payLen=len(payload2),
                              verbosity=1, DR=True, DRIface=3, Tag=8, **fields2)
    pkt2.MGRUUID = pkt1.MGRUUID
    pkt2.Addr = 0xabcdef
    pkt2.set_payload(payload2)
    pkt2.set_crcs()
    pkt_list.append(pkt2)

    # payload3 defined above
    fields3 = { 'VC': 0, 'DCID': 0x5, 'SCID': 0x11, 'Deadline': 211, 'PM': 1 }
    pkt3 = genz.PacketFactory('Core64', 'ReadResponse', payLen=payLen3,
                              verbosity=3, Tag=9, AKey=0x31, **fields3)
    pkt3.RRSPReason = 0xc
    pkt3.set_payload(payload3)
    pkt3.set_crcs()
    pkt_list.append(pkt3)

    payload4 = bytearray(16)
    pkt4 = genz.PacketFactory('Control', 'ReadResponse', verbosity=3,
                              VC=0, SCID=0x22, DCID=0x5, payLen=len(payload4),
                              GC=1, SSID=0xabcd, DSID=0x1234, Tag=7)
    pkt4.set_payload(payload4)
    pkt4.set_crcs()
    pkt_list.append(pkt4)

    pkt5 = genz.PacketFactory('Control', 'StandaloneAck', verbosity=3,
                              VC=0, SCID=0x10, DCID=0x5, Tag=8, Reason=0x6)
    pkt5.RS = 0xa5
    pkt5.set_crcs()
    pkt_list.append(pkt5)

    pkt6 = genz.PacketFactory('Control', 'UnsolicitedEvent', verbosity=3,
                              VC=0, SCID=0x10, DCID=0x5, IV=1, IfaceID=0x3)
    pkt6.Event = 0x1f
    pkt6.EventID = 0x9
    pkt6.CV = 1
    pkt6.SV = 1
    pkt6.RCCID = 0x22
    pkt6.RCSID = 0xabcd
    pkt6.ES = 0xabcde
    pkt6.set_crcs()
    pkt_list.append(pkt6)

    payload7 = bytearray(0x4a926e442c1d798ff1477902.to_bytes(12, byteorder='little'))
    payLen7 = len(payload7)
    fields7 = { 'VC': 1, 'SCID': 0x1, 'DCID': 0x6, 'Deadline': 346,
                'REQCTXID': 0xabcdef}
    pkt7 = genz.PacketFactory('CtxId', 'WriteMSG', payLen=payLen7,
                              verbosity=1, MSGSZ=1, Tag=0x3e, **fields7)
    pkt7.RSPCTXID = 0x123456
    pkt7.MSGID = 0x02040608
    pkt7.set_payload(payload7)
    pkt7.set_crcs()
    pkt_list.append(pkt7)

    fields8 = { 'VC': 1, 'SCID': 0x1, 'DCID': 0x26, 'Deadline': 446,
                'REQCTXID': 0xa0c0e0}
    pkt8 = genz.PacketFactory('Control', 'UnrelWriteMSG', payLen=payLen7,
                              verbosity=1, MSGSZ=1, Tag=0x3f, **fields8)
    pkt8.RSPCTXID = 0x010203
    pkt8.MSGID = 0x11223344
    pkt8.set_payload(payload7)
    pkt8.set_crcs()
    pkt_list.append(pkt8)

    fields9 = { 'VC': 1, 'SCID': 0x1, 'DCID': 0x36, 'Deadline': 646,
                'REQCTXID': 0xa0c0e0, 'DR': 1, 'DRIface': 0x1, 'SDR': 1}
    pkt9 = genz.PacketFactory('DR', 'UnrelWriteMSG', payLen=payLen7,
                              verbosity=1, MSGSZ=1, Tag=0x40, **fields9)
    pkt9.RSPCTXID = 0x010203
    pkt9.MSGID = 0x22334455
    pkt9.set_payload(payload7)
    pkt9.set_crcs()
    pkt_list.append(pkt9)

    fields10 = { 'VC': 1, 'SCID': 0x1, 'Deadline': 146, 'RT': 1, 'CH': 1,
                 'MGID': 0xabc, 'RCVTag': 0x0102030405060708090a0b0c}
    pkt10 = genz.PacketFactory('Multicast', 'UnrelWriteMSG', payLen=payLen7,
                               verbosity=1, MSGSZ=1, Tag=0x41, **fields10)
    pkt10.MSGID = 0x22334455
    pkt10.set_payload(payload7)
    pkt10.set_crcs()
    pkt_list.append(pkt10)

    pkt11 = genz.PacketFactory('Adv2', 'PTREQ', verbosity=1, NP=1,
                               GTCCID=0x22,
                               VC=1, SCID=0x10, DCID=0x5, Tag=0x42)
    pkt11.set_crcs()
    pkt_list.append(pkt11)

    pkt12 = genz.PacketFactory('Adv2', 'PTRSP', verbosity=1, TP=1, SV=1, GTCSID=0xabcd,
                               GTCCID=0x21, MasterTime=0x123456789abcdef, PropDelay=0x87654,
                               VC=1, SCID=0x5, DCID=0x10, Tag=0x43)
    pkt12.set_crcs()
    pkt_list.append(pkt12)

    return pkt_list

def print_pkts(pkts, width=120, wrap=False):
    for i, pkt in enumerate(pkts):
        if wrap:
            pkt_str = fill(str(pkt), width=width-3, subsequent_indent=" "*8)
        else: # no wrap
            pkt_str = str(pkt)
        print(f'{i}: {pkt_str}')

def main():
    pkts = make_pkts()
    print_pkts(pkts, width=110, wrap=True)

if __name__ == '__main__':
    try:
        main()
    except Exception as post_err:
        if args.post_mortem:
            traceback.print_exc()
            post_mortem()
        else:
            raise
