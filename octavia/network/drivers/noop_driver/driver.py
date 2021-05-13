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
# under the License.

from oslo_log import log as logging
from oslo_utils import uuidutils

from octavia.common import data_models
from octavia.network import base as driver_base
from octavia.network import data_models as network_models

LOG = logging.getLogger(__name__)


class NoopManager(object):
    def __init__(self):
        super(NoopManager, self).__init__()
        self.networkconfigconfig = {}
        self._qos_extension_enabled = True

    def allocate_vip(self, loadbalancer):
        LOG.debug("Network %s no-op, allocate_vip loadbalancer %s",
                  self.__class__.__name__, loadbalancer)
        self.networkconfigconfig[loadbalancer.id] = (
            loadbalancer, 'allocate_vip')
        subnet_id = uuidutils.generate_uuid()
        network_id = uuidutils.generate_uuid()
        port_id = uuidutils.generate_uuid()
        ip_address = '198.51.100.1'
        if loadbalancer.vip:
            subnet_id = loadbalancer.vip.subnet_id or subnet_id
            network_id = loadbalancer.vip.network_id or network_id
            port_id = loadbalancer.vip.port_id or port_id
            ip_address = loadbalancer.vip.ip_address or ip_address
        return data_models.Vip(ip_address=ip_address,
                               subnet_id=subnet_id,
                               network_id=network_id,
                               port_id=port_id,
                               load_balancer_id=loadbalancer.id)

    def deallocate_vip(self, vip):
        LOG.debug("Network %s no-op, deallocate_vip vip %s",
                  self.__class__.__name__, vip.ip_address)
        self.networkconfigconfig[vip.ip_address] = (vip,
                                                    'deallocate_vip')

    def plug_vip(self, loadbalancer, vip):
        LOG.debug("Network %s no-op, plug_vip loadbalancer %s, vip %s",
                  self.__class__.__name__,
                  loadbalancer.id, vip.ip_address)
        self.update_vip_sg(loadbalancer, vip)
        amps = []
        for amphora in loadbalancer.amphorae:
            amps.append(self.plug_aap_port(loadbalancer, vip, amphora, None))
        self.networkconfigconfig[(loadbalancer.id,
                                  vip.ip_address)] = (loadbalancer, vip,
                                                      'plug_vip')
        return amps

    def update_vip_sg(self, load_balancer, vip):
        LOG.debug("Network %s no-op, update_vip_sg loadbalancer %s, vip %s",
                  self.__class__.__name__,
                  load_balancer.id, vip.ip_address)
        self.networkconfigconfig[(load_balancer.id,
                                  vip.ip_address)] = (load_balancer, vip,
                                                      'update_vip_sg')

    def plug_aap_port(self, load_balancer, vip, amphora, subnet):
        LOG.debug("Network %s no-op, plug_aap_port loadbalancer %s, vip %s,"
                  " amphora %s, subnet %s",
                  self.__class__.__name__,
                  load_balancer.id, vip.ip_address, amphora, subnet)
        self.networkconfigconfig[(amphora.id,
                                  vip.ip_address)] = (
            load_balancer, vip, amphora, subnet,
            'plug_aap_port')
        return data_models.Amphora(
            id=amphora.id,
            compute_id=amphora.compute_id,
            vrrp_ip='198.51.100.1',
            ha_ip='198.51.100.1',
            vrrp_port_id=uuidutils.generate_uuid(),
            ha_port_id=uuidutils.generate_uuid()
        )

    def unplug_vip(self, loadbalancer, vip):
        LOG.debug("Network %s no-op, unplug_vip loadbalancer %s, vip %s",
                  self.__class__.__name__,
                  loadbalancer.id, vip.ip_address)
        self.networkconfigconfig[(loadbalancer.id,
                                  vip.ip_address)] = (loadbalancer, vip,
                                                      'unplug_vip')

    def unplug_aap_port(self, vip, amphora, subnet):
        LOG.debug("Network %s no-op, unplug_aap_port vip %s amp: %s "
                  "subnet: %s",
                  self.__class__.__name__,
                  vip.ip_address, amphora.id, subnet.id)
        self.networkconfigconfig[(amphora.id,
                                  vip.ip_address)] = (vip, amphora, subnet,
                                                      'unplug_aap_port')

    def plug_network(self, compute_id, network_id, ip_address=None):
        LOG.debug("Network %s no-op, plug_network compute_id %s, network_id "
                  "%s, ip_address %s", self.__class__.__name__, compute_id,
                  network_id, ip_address)
        self.networkconfigconfig[(compute_id, network_id, ip_address)] = (
            compute_id, network_id, ip_address, 'plug_network')
        return network_models.Interface(
            id=uuidutils.generate_uuid(),
            compute_id=compute_id,
            network_id=network_id,
            fixed_ips=[],
            port_id=uuidutils.generate_uuid()
        )

    def unplug_network(self, compute_id, network_id, ip_address=None):
        LOG.debug("Network %s no-op, unplug_network compute_id %s, "
                  "network_id %s",
                  self.__class__.__name__, compute_id, network_id)
        self.networkconfigconfig[(compute_id, network_id, ip_address)] = (
            compute_id, network_id, ip_address, 'unplug_network')

    def get_plugged_networks(self, compute_id):
        LOG.debug("Network %s no-op, get_plugged_networks amphora_id %s",
                  self.__class__.__name__, compute_id)
        self.networkconfigconfig[compute_id] = (
            compute_id, 'get_plugged_networks')
        return []

    def update_vip(self, loadbalancer, for_delete=False):
        LOG.debug("Network %s no-op, update_vip loadbalancer %s "
                  "with for delete %s",
                  self.__class__.__name__, loadbalancer, for_delete)
        self.networkconfigconfig[loadbalancer.id] = (
            loadbalancer, for_delete, 'update_vip')

    def get_network(self, network_id):
        LOG.debug("Network %s no-op, get_network network_id %s",
                  self.__class__.__name__, network_id)
        self.networkconfigconfig[network_id] = (network_id, 'get_network')
        network = network_models.Network(id=uuidutils.generate_uuid(),
                                         port_security_enabled=True)

        class ItIsInsideMe(object):
            def __contains__(self, item):
                return True

            def __iter__(self):
                yield uuidutils.generate_uuid()

        network.subnets = ItIsInsideMe()
        return network

    def get_subnet(self, subnet_id):
        LOG.debug("Subnet %s no-op, get_subnet subnet_id %s",
                  self.__class__.__name__, subnet_id)
        self.networkconfigconfig[subnet_id] = (subnet_id, 'get_subnet')
        return network_models.Subnet(id=uuidutils.generate_uuid())

    def get_port(self, port_id):
        LOG.debug("Port %s no-op, get_port port_id %s",
                  self.__class__.__name__, port_id)
        self.networkconfigconfig[port_id] = (port_id, 'get_port')
        return network_models.Port(id=uuidutils.generate_uuid())

    def get_network_by_name(self, network_name):
        LOG.debug("Network %s no-op, get_network_by_name network_name %s",
                  self.__class__.__name__, network_name)
        self.networkconfigconfig[network_name] = (network_name,
                                                  'get_network_by_name')
        return network_models.Network(id=uuidutils.generate_uuid(),
                                      port_security_enabled=True)

    def get_subnet_by_name(self, subnet_name):
        LOG.debug("Subnet %s no-op, get_subnet_by_name subnet_name %s",
                  self.__class__.__name__, subnet_name)
        self.networkconfigconfig[subnet_name] = (subnet_name,
                                                 'get_subnet_by_name')
        return network_models.Subnet(id=uuidutils.generate_uuid())

    def get_port_by_name(self, port_name):
        LOG.debug("Port %s no-op, get_port_by_name port_name %s",
                  self.__class__.__name__, port_name)
        self.networkconfigconfig[port_name] = (port_name, 'get_port_by_name')
        return network_models.Port(id=uuidutils.generate_uuid())

    def get_port_by_net_id_device_id(self, network_id, device_id):
        LOG.debug("Port %s no-op, get_port_by_net_id_device_id network_id %s"
                  " device_id %s",
                  self.__class__.__name__, network_id, device_id)
        self.networkconfigconfig[(network_id, device_id)] = (
            network_id, device_id, 'get_port_by_net_id_device_id')
        return network_models.Port(id=uuidutils.generate_uuid())

    def get_security_group(self, sg_name):
        LOG.debug("Network %s no-op, get_security_group name %s",
                  self.__class__.__name__, sg_name)
        self.networkconfigconfig[(sg_name)] = (sg_name, 'get_security_group')
        return network_models.SecurityGroup(id=uuidutils.generate_uuid())

    def failover_preparation(self, amphora):
        LOG.debug("failover %s no-op, failover_preparation, amphora id %s",
                  self.__class__.__name__, amphora.id)

    def plug_port(self, amphora, port):
        LOG.debug("Network %s no-op, plug_port amphora.id %s, port_id "
                  "%s", self.__class__.__name__, amphora.id, port.id)
        self.networkconfigconfig[(amphora.id, port.id)] = (
            amphora, port, 'plug_port')

    def _get_amp_net_configs(self, amp, amp_configs, vip_subnet, vip_port):
        vrrp_port = self.get_port(amp.vrrp_port_id)
        ha_port = self.get_port(amp.ha_port_id)
        amp_configs[amp.id] = network_models.AmphoraNetworkConfig(
            amphora=amp,
            vrrp_subnet=self.get_subnet(
                vrrp_port.get_subnet_id(amp.vrrp_ip)),
            vrrp_port=vrrp_port,
            ha_subnet=self.get_subnet(
                ha_port.get_subnet_id(amp.ha_ip)),
            ha_port=ha_port)

    def get_network_configs(self, loadbalancer, amphora=None):
        amphora_id = amphora.id if amphora else None
        LOG.debug("Network %s no-op, get_network_configs loadbalancer id "
                  "%s amphora id: %s", self.__class__.__name__,
                  loadbalancer.id, amphora_id)
        self.networkconfigconfig[(loadbalancer.id)] = (
            loadbalancer, 'get_network_configs')
        vip_subnet = self.get_subnet(loadbalancer.vip.subnet_id)
        vip_port = self.get_port(loadbalancer.vip.port_id)

        amp_configs = {}
        if amphora:
            self._get_amp_net_configs(amphora, amp_configs,
                                      vip_subnet, vip_port)
        else:
            for amp in loadbalancer.amphorae:
                self._get_amp_net_configs(amp, amp_configs,
                                          vip_subnet, vip_port)

        return amp_configs

    def wait_for_port_detach(self, amphora):
        LOG.debug("failover %s no-op, wait_for_port_detach, amphora id %s",
                  self.__class__.__name__, amphora.id)

    def get_qos_policy(self, qos_policy_id):
        LOG.debug("Qos Policy %s no-op, get_qos_policy qos_policy_id %s",
                  self.__class__.__name__, qos_policy_id)
        self.networkconfigconfig[qos_policy_id] = (qos_policy_id,
                                                   'get_qos_policy')
        return qos_policy_id

    def apply_qos_on_port(self, qos_id, port_id):
        LOG.debug("Network %s no-op, apply_qos_on_port qos_id %s, port_id "
                  "%s", self.__class__.__name__, qos_id, port_id)
        self.networkconfigconfig[(qos_id, port_id)] = (
            qos_id, port_id, 'apply_qos_on_port')

    def qos_enabled(self):
        return self._qos_extension_enabled

    def get_network_ip_availability(self, network):
        LOG.debug("Network %s no-op, network_ip_availability network_id %s",
                  self.__class__.__name__, network.id)
        self.networkconfigconfig[(network.id, 'ip_availability')] = (
            network.id, 'get_network_ip_availability')
        ip_avail = network_models.Network_IP_Availability(
            network_id=network.id)
        subnet_ip_availability = []
        network.subnets = list(network.subnets)
        for subnet_id in network.subnets:
            subnet_ip_availability.append({'subnet_id': subnet_id,
                                          'used_ips': 0, 'total_ips': 254})
        ip_avail.subnet_ip_availability = subnet_ip_availability
        return ip_avail

    def delete_port(self, port_id):
        LOG.debug("Network %s no-op, delete_port port_id %s",
                  self.__class__.__name__, port_id)
        self.networkconfigconfig[port_id] = (port_id, 'delete_port')

    def set_port_admin_state_up(self, port_id, state):
        LOG.debug("Network %s no-op, set_port_admin_state_up port_id %s, "
                  "state %s", self.__class__.__name__, port_id, state)
        self.networkconfigconfig[(port_id, state)] = (port_id, state,
                                                      'admin_down_port')

    def create_port(self, network_id, name=None, fixed_ips=(),
                    secondary_ips=(), security_group_ids=(),
                    admin_state_up=True, qos_policy_id=None):
        LOG.debug("Network %s no-op, create_port network_id %s",
                  self.__class__.__name__, network_id)
        if not name:
            name = 'no-op-port'
        port_id = uuidutils.generate_uuid()
        project_id = uuidutils.generate_uuid()

        fixed_ip_obj_list = []
        for fixed_ip in fixed_ips:
            if fixed_ip and not fixed_ip.get('ip_address'):
                fixed_ip_obj_list.append(
                    network_models.FixedIP(subnet_id=fixed_ip.get('subnet_id'),
                                           ip_address='198.51.100.56'))
            else:
                fixed_ip_obj_list.append(
                    network_models.FixedIP(
                        subnet_id=fixed_ip.get('subnet_id'),
                        ip_address=fixed_ip.get('ip_address')))
        if not fixed_ip_obj_list:
            fixed_ip_obj_list = [network_models.FixedIP(
                subnet_id=uuidutils.generate_uuid(),
                ip_address='198.51.100.56')]

        self.networkconfigconfig[(network_id, 'create_port')] = (
            network_id, name, fixed_ip_obj_list, secondary_ips,
            security_group_ids, admin_state_up, qos_policy_id)
        return network_models.Port(
            id=port_id, name=name, device_id='no-op-device-id',
            device_owner='Octavia', mac_address='00:00:5E:00:53:05',
            network_id=network_id, status='UP', project_id=project_id,
            admin_state_up=admin_state_up, fixed_ips=fixed_ip_obj_list,
            qos_policy_id=qos_policy_id, security_group_ids=security_group_ids)


class NoopNetworkDriver(driver_base.AbstractNetworkDriver):
    def __init__(self):
        super(NoopNetworkDriver, self).__init__()
        self.driver = NoopManager()

    def allocate_vip(self, loadbalancer):
        return self.driver.allocate_vip(loadbalancer)

    def deallocate_vip(self, vip):
        self.driver.deallocate_vip(vip)

    def plug_vip(self, loadbalancer, vip):
        return self.driver.plug_vip(loadbalancer, vip)

    def unplug_vip(self, loadbalancer, vip):
        self.driver.unplug_vip(loadbalancer, vip)

    def plug_network(self, amphora_id, network_id, ip_address=None):
        return self.driver.plug_network(amphora_id, network_id, ip_address)

    def unplug_network(self, amphora_id, network_id, ip_address=None):
        self.driver.unplug_network(amphora_id, network_id,
                                   ip_address=ip_address)

    def get_plugged_networks(self, amphora_id):
        return self.driver.get_plugged_networks(amphora_id)

    def update_vip(self, loadbalancer, for_delete=False):
        self.driver.update_vip(loadbalancer, for_delete)

    def get_network(self, network_id, context=None):
        return self.driver.get_network(network_id)

    def get_subnet(self, subnet_id, context=None):
        return self.driver.get_subnet(subnet_id)

    def get_port(self, port_id, context=None):
        return self.driver.get_port(port_id)

    def get_qos_policy(self, qos_policy_id):
        return self.driver.get_qos_policy(qos_policy_id)

    def get_network_by_name(self, network_name):
        return self.driver.get_network_by_name(network_name)

    def get_subnet_by_name(self, subnet_name):
        return self.driver.get_subnet_by_name(subnet_name)

    def get_port_by_name(self, port_name):
        return self.driver.get_port_by_name(port_name)

    def get_port_by_net_id_device_id(self, network_id, device_id):
        return self.driver.get_port_by_net_id_device_id(network_id, device_id)

    def get_security_group(self, sg_name):
        return self.driver.get_security_group(sg_name)

    def failover_preparation(self, amphora):
        self.driver.failover_preparation(amphora)

    def plug_port(self, amphora, port):
        return self.driver.plug_port(amphora, port)

    def get_network_configs(self, loadbalancer, amphora=None):
        return self.driver.get_network_configs(loadbalancer, amphora)

    def wait_for_port_detach(self, amphora):
        self.driver.wait_for_port_detach(amphora)

    def apply_qos_on_port(self, qos_id, port_id):
        self.driver.apply_qos_on_port(qos_id, port_id)

    def update_vip_sg(self, load_balancer, vip):
        self.driver.update_vip_sg(load_balancer, vip)

    def plug_aap_port(self, load_balancer, vip, amphora, subnet):
        return self.driver.plug_aap_port(load_balancer, vip, amphora, subnet)

    def unplug_aap_port(self, vip, amphora, subnet):
        self.driver.unplug_aap_port(vip, amphora, subnet)

    def qos_enabled(self):
        return self.driver.qos_enabled()

    def get_network_ip_availability(self, network):
        return self.driver.get_network_ip_availability(network)

    def delete_port(self, port_id):
        self.driver.delete_port(port_id)

    def set_port_admin_state_up(self, port_id, state):
        self.driver.set_port_admin_state_up(port_id, state)

    def create_port(self, network_id, name=None, fixed_ips=(),
                    secondary_ips=(), security_group_ids=(),
                    admin_state_up=True, qos_policy_id=None):
        return self.driver.create_port(
            network_id, name, fixed_ips, secondary_ips, security_group_ids,
            admin_state_up, qos_policy_id)
