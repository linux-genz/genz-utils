#!/usr/bin/env python3

""" Find matching zephyr instance

If there is only a single zephyr instance, then no options are required.
If there are multiple, then sufficient command line arguments must be supplied
to narrow them down to a single match.
"""

import argparse
import logging
from time import sleep
from typing import cast
from uuid import UUID

from zeroconf import IPVersion, ServiceBrowser, ServiceListener, ServiceStateChange, Zeroconf, ZeroconfServiceTypes, ServiceInfo


def service_info(info: ServiceInfo) -> str:
    addresses = [f'{addr}:{cast(int, info.port)}' for addr in info.parsed_scoped_addresses()]
    r = f'  Addresses: {", ".join(addresses)}\n'
    r += f'  Weight: {info.weight}, priority: {info.priority}\n'
    r += f'  Server: {info.server}'
    if info.properties:
        r += '\n' + '  Properties:'
        fab_uuid = UUID(bytes=info.properties[b'fab_uuid'])
        mgr_uuid = UUID(bytes=info.properties[b'mgr_uuid'])
        pfm = bool(int(info.properties[b'pfm']))
        r += '\n' + f'    fab_uuid: {fab_uuid}'
        r += '\n' + f'    mgr_uuid: {mgr_uuid}'
        r += '\n' + f'    pfm: {pfm}'
        #for key, value in info.properties.items():
        #    r += '\n' + f'    {str(key, "utf-8")}: {value}'
    return r


class Listener(ServiceListener):
    def add_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        #print(f"Service {name} of type {type} Added")
        info = zeroconf.get_service_info(type, name)
        if info:
            print(service_info(info))

    def remove_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        print(f"Service {name} of type {type} Removed")
        info = zeroconf.get_service_info(type, name)
        if info:
            print(service_info(info))

    def update_service(self, zeroconf: Zeroconf, type: str, name: str) -> None:
        print(f"Service {name} of type {type} Updated")
        info = zeroconf.get_service_info(type, name)
        if info:
            print(service_info(info))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--all', action='store_true', help='List all available zephyr instances')
    version_group = parser.add_mutually_exclusive_group()
    version_group.add_argument('--v6', action='store_true')
    version_group.add_argument('--v6-only', action='store_true')
    global args
    args = parser.parse_args()

    if args.debug:
        logging.getLogger('zeroconf').setLevel(logging.DEBUG)
    if args.v6:
        ip_version = IPVersion.All
    elif args.v6_only:
        ip_version = IPVersion.V6Only
    else:
        ip_version = IPVersion.V4Only

    zeroconf = Zeroconf(ip_version=ip_version)
    listener = Listener()
    services = ['_genz-fm._tcp.local.']

    if args.debug:
        print(f'\nBrowsing {len(services)} service(s): {services}, press Ctrl-C to exit...\n')
    browser = ServiceBrowser(zeroconf, services, listener)

    try:
        while True:
            sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        zeroconf.close()
