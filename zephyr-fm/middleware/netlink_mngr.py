#!/usr/bin/python3

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
import socket
import uuid
import logging
import os

from pprint import pprint
from pdb import set_trace

import alpaka
from message_model.add_fabric_component import ModelAddFabricComponent

class NetlinkManager(alpaka.Messenger):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def build_msg(self, cmd, **kwargs):
        data = kwargs.get('data', None)
        attrs = []
        err_msg = 'build_msg required "%s" parameter is None or missing!'
        if cmd is None:
            logging.error(err_msg % 'cmd')
            return None
        if data is None:
            logging.error(err_msg % 'data')
            return None

        cmd_index = self.cfg.cmd_opts.get(cmd)

        contract = self.cfg.get('CONTRACT', {}).get(cmd_index)
        if contract is None:
            contract = data

        kwargs['model'] = ModelAddFabricComponent
        super().build_msg(cmd, **kwargs)
        msg = self.msg_model()

        #Convert a data structure into the parameters that kernel understands
        # for key, value in data.items():
        #     nl_key_name = contract[key] #key must be there at this point
        #     if isinstance(value, str):
        #         if value.isdigit():
        #             #parse digit str into float or int. Assume '.' in str is a float.
        #             if '.' in value: value = float(value)
        #             else: value = int(value)

        #     #This is a Hack to extract UUID! Wait for a precedent to break this.
        #     if 'uuid' in nl_key_name.lower():
        #         value = uuid.UUID(str(value)).bytes

        #     attrs.append([ nl_key_name, value ])

        attrs.append(['GENZ_A_FC_GCID',         data['gcid']])
        attrs.append(['GENZ_A_FC_BRIDGE_GCID',  data['br_gcid']])
        attrs.append(['GENZ_A_FC_TEMP_GCID',    data['tmp_gcid']])
        attrs.append(['GENZ_A_FC_DR_GCID',      data['dr_gcid']])
        attrs.append(['GENZ_A_FC_DR_INTERFACE', data['dr_iface']])
        attrs.append(['GENZ_A_FC_MGR_UUID',     data['mgr_uuid'].bytes])

        msg['attrs'] = attrs
        msg['cmd'] = cmd_index
        msg['pid'] = os.getpid()
        msg['version'] = self.cfg.version
        return msg

# if __name__ == "__main__":
#     genznl = NetlinkManager()
#     # genznl = Talker(config='../config')
#     UUID = YodelAyHeHUUID()
#     msg = genznl.build_msg(genznl.cfg.get('ADD'), gcid=4242, cclass=43, uuid=UUID)
#     print('Sending PID=%d UUID=%s' % (msg['pid'], str(UUID)))
#     try:
#         # If it works, get a packet.  If not, raise an error.
#         retval = genznl.sendmsg(msg)
#         resperr = retval[0]['header']['error']
#         if resperr:
#             print('--------!!netlink_mngr: __main__!!!-------')
#             pprint(retval)
#             raise RuntimeError(resperr)
#         print('Success')
#     except Exception as exc:
#         raise SystemExit(str(exc))

#     raise SystemExit(0)
