# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
#    under the License.

import os
import re
import socket
import subprocess

import pyroute2
import webob

from octavia.amphorae.backends.agent import api_server
from octavia.amphorae.backends.agent.api_server import util
from octavia.amphorae.backends.utils import network_utils
from octavia.common import constants as consts
from octavia.common import exceptions


class AmphoraInfo(object):
    def __init__(self, osutils):
        self._osutils = osutils

    def compile_amphora_info(self, extend_udp_driver=None):
        extend_body = {}
        if extend_udp_driver:
            extend_body = self._get_extend_body_from_udp_driver(
                extend_udp_driver)
        body = {'hostname': socket.gethostname(),
                'haproxy_version':
                    self._get_version_of_installed_package('haproxy'),
                'api_version': api_server.VERSION}
        if extend_body:
            body.update(extend_body)
        return webob.Response(json=body)

    def compile_amphora_details(self, extend_udp_driver=None):
        haproxy_listener_list = sorted(util.get_listeners())
        extend_body = {}
        udp_listener_list = []
        if extend_udp_driver:
            udp_listener_list = util.get_udp_listeners()
            extend_data = self._get_extend_body_from_udp_driver(
                extend_udp_driver)
            udp_count = self._count_udp_listener_processes(extend_udp_driver,
                                                           udp_listener_list)
            extend_body['udp_listener_process_count'] = udp_count
            extend_body.update(extend_data)
        meminfo = self._get_meminfo()
        cpu = self._cpu()
        st = os.statvfs('/')
        body = {'hostname': socket.gethostname(),
                'haproxy_version':
                    self._get_version_of_installed_package('haproxy'),
                'api_version': api_server.VERSION,
                'networks': self._get_networks(),
                'active': True,
                'haproxy_count':
                    self._count_haproxy_processes(haproxy_listener_list),
                'cpu': {
                    'total': cpu['total'],
                    'user': cpu['user'],
                    'system': cpu['system'],
                    'soft_irq': cpu['softirq'], },
                'memory': {
                    'total': meminfo['MemTotal'],
                    'free': meminfo['MemFree'],
                    'buffers': meminfo['Buffers'],
                    'cached': meminfo['Cached'],
                    'swap_used': meminfo['SwapCached'],
                    'shared': meminfo['Shmem'],
                    'slab': meminfo['Slab'], },
                'disk': {
                    'used': (st.f_blocks - st.f_bfree) * st.f_frsize,
                    'available': st.f_bavail * st.f_frsize},
                'load': self._load(),
                'topology': consts.TOPOLOGY_SINGLE,
                'topology_status': consts.TOPOLOGY_STATUS_OK,
                'listeners': sorted(list(
                    set(haproxy_listener_list + udp_listener_list)))
                if udp_listener_list else haproxy_listener_list,
                'packages': {}}
        if extend_body:
            body.update(extend_body)
        return webob.Response(json=body)

    def _get_version_of_installed_package(self, name):

        cmd = self._osutils.cmd_get_version_of_installed_package(name)
        version = subprocess.check_output(cmd.split())
        return version

    def _count_haproxy_processes(self, lb_list):
        num = 0
        for lb_id in lb_list:
            if util.is_lb_running(lb_id):
                # optional check if it's still running
                num += 1
        return num

    def _count_udp_listener_processes(self, udp_driver, listener_list):
        num = 0
        for listener_id in listener_list:
            if udp_driver.is_listener_running(listener_id):
                # optional check if it's still running
                num += 1
        return num

    def _get_extend_body_from_udp_driver(self, extend_udp_driver):
        extend_info = extend_udp_driver.get_subscribed_amp_compile_info()
        extend_data = {}
        for extend in extend_info:
            package_version = self._get_version_of_installed_package(extend)
            extend_data['%s_version' % extend] = package_version
        return extend_data

    def _get_meminfo(self):
        re_parser = re.compile(r'^(?P<key>\S*):\s*(?P<value>\d*)\s*kB')
        result = dict()
        with open('/proc/meminfo', 'r') as meminfo:
            for line in meminfo:
                match = re_parser.match(line)
                if not match:
                    continue  # skip lines that don't parse
                key, value = match.groups(['key', 'value'])
                result[key] = int(value)
        return result

    def _cpu(self):
        with open('/proc/stat') as f:
            cpu = f.readline()
            vals = cpu.split(' ')
            return {
                'user': vals[2],
                'nice': vals[3],
                'system': vals[4],
                'idle': vals[5],
                'iowait': vals[6],
                'irq': vals[7],
                'softirq': vals[8],
                'total': sum([int(i) for i in vals[2:]])
            }

    def _load(self):
        with open('/proc/loadavg') as f:
            load = f.readline()
            vals = load.split(' ')
            return vals[:3]

    def _get_networks(self):
        networks = dict()
        with pyroute2.NetNS(consts.AMPHORA_NAMESPACE) as netns:
            for interface in netns.get_links():
                interface_name = None
                for item in interface['attrs']:
                    if (item[0] == 'IFLA_IFNAME' and
                            not item[1].startswith('eth')):
                        break
                    if item[0] == 'IFLA_IFNAME':
                        interface_name = item[1]
                    if item[0] == 'IFLA_STATS64':
                        networks[interface_name] = dict(
                            network_tx=item[1]['tx_bytes'],
                            network_rx=item[1]['rx_bytes'])
        return networks

    def get_interface(self, ip_addr):
        try:
            interface = network_utils.get_interface_name(
                ip_addr, net_ns=consts.AMPHORA_NAMESPACE)
        except exceptions.InvalidIPAddress:
            return webob.Response(json=dict(message="Invalid IP address"),
                                  status=400)
        except exceptions.NotFound:
            return webob.Response(
                json=dict(message="Error interface not found for IP address"),
                status=404)
        return webob.Response(json=dict(message='OK', interface=interface),
                              status=200)
