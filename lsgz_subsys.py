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
import ctypes
import re
from uuid import UUID
from pathlib import Path
from genz_common import GCID
from pdb import set_trace

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

def get_struct(fpath, map, parent=None, core=None, verbosity=0):
    fname = fpath.name
    with fpath.open(mode='rb') as f:
        data = bytearray(f.read())
        # special case for 'interface' - optional fields
        if (fname == 'interface' and
            len(data) >= ctypes.sizeof(genz.InterfaceXStructure)):
            fname = 'interfaceX'
        struct = map.fileToStruct(fname, data, path=fpath,
                                  parent=parent, core=core,
                                  verbosity=verbosity)
        return struct

def get_parent(fpath, dpath, parents):
    parent = parents['core@0x0']  # default parent, if we do not find another
    for p in reversed(dpath.parents[0].parts):
        if p == 'control':
            break
        if '@0x' in p:
            parent = parents[p]
            break
    return parent

def main():
    global cols
    global genz
    parser = argparse.ArgumentParser()
    #parser.add_argument('file', help='the file containing control space')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-G', '--genz-version', choices=['1.1'],
                        default='1.1',
                        help='Gen-Z spec version of Control Space structures')
    args = parser.parse_args()
    if args.verbosity > 5:
        print('Gen-Z version = {}'.format(args.genz_version))
    genz = __import__('genz_{}'.format(args.genz_version.replace('.', '_')))
    map = genz.ControlStructureMap()
    sys_devices = Path('/sys/devices')
    fabrics = sys_devices.glob('genz*')
    for fab in fabrics:
        fabnum = component_num(fab)
        #print('fabric: {}, num={}'.format(fab, fabnum))
        bridges = fab.glob('bridge*')
        for br in bridges:
            gcid = get_gcid(br)
            cuuid = get_cuuid(br)
            brnum = component_num(br)
            print('{}:{} bridge{} {}'.format(fabnum, gcid, brnum, cuuid))
            if args.verbosity < 1:
                continue
            parents = {}
            ctl = br / 'control'
            # do core structure first
            core_path = ctl / 'core@0x0' / 'core'
            core = get_struct(core_path, map, verbosity=args.verbosity)
            print('  {}='.format('core@0x0'), end='')
            print(core)
            parents['core@0x0'] = core
            for dir, dirnames, filenames in os.walk(ctl):
                #print('{}, {}, {}'.format(dir, dirnames, filenames))
                for file in filenames:
                    if file == 'core':  # we already did core
                        continue
                    dpath = Path(dir)
                    print('  {}='.format(dpath.name), end='')
                    fpath = dpath / file
                    parent = get_parent(fpath, dpath, parents)
                    struct = get_struct(fpath, map, core=core, parent=parent,
                                        verbosity=args.verbosity)
                    print(struct)
                    parents[dpath.name] = struct
                # end for filenames
            # end for dir
        # end for br
    # end for fab

if __name__ == '__main__':
    main()
