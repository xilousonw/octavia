#    Copyright 2014 Rackspace
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import ipaddress
import time

from neutronclient.common import exceptions as neutron_client_exceptions
from novaclient import exceptions as nova_client_exceptions
from oslo_config import cfg
from oslo_log import log as logging
import six
from stevedore import driver as stevedore_driver

from octavia.common import constants
from octavia.common import data_models
from octavia.common import exceptions
from octavia.common import utils as common_utils
from octavia.i18n import _
from octavia.network import base
from octavia.network import data_models as n_data_models
from octavia.network.drivers.neutron import base as neutron_base
from octavia.network.drivers.neutron import utils

LOG = logging.getLogger(__name__)
AAP_EXT_ALIAS = 'allowed-address-pairs'
PROJECT_ID_ALIAS = 'project-id'
OCTAVIA_OWNER = 'Octavia'

CONF = cfg.CONF


class AllowedAddressPairsDriver(neutron_base.BaseNeutronDriver):

    def __init__(self):
        super(AllowedAddressPairsDriver, self).__init__()
        self._check_aap_loaded()
        self.compute = stevedore_driver.DriverManager(
            namespace='octavia.compute.drivers',
            name=CONF.controller_worker.compute_driver,
            invoke_on_load=True
        ).driver

    def _check_aap_loaded(self):
        if not self._check_extension_enabled(AAP_EXT_ALIAS):
            raise base.NetworkException(
                'The {alias} extension is not enabled in neutron.  This '
                'driver cannot be used with the {alias} extension '
                'disabled.'.format(alias=AAP_EXT_ALIAS))

    def _get_interfaces_to_unplug(self, interfaces, network_id,
                                  ip_address=None):
        ret = []
        for interface in interfaces:
            if interface.network_id == network_id:
                if ip_address:
                    for fixed_ip in interface.fixed_ips:
                        if ip_address == fixed_ip.ip_address:
                            ret.append(interface)
                else:
                    ret.append(interface)
        return ret

    def _get_plugged_interface(self, compute_id, network_id, lb_network_ip):
        interfaces = self.get_plugged_networks(compute_id)
        for interface in interfaces:
            is_correct_interface = interface.network_id == network_id
            for ip in interface.fixed_ips:
                if ip.ip_address == lb_network_ip:
                    is_correct_interface = False
            if is_correct_interface:
                return interface
        return None

    def _plug_amphora_vip(self, amphora, subnet):
        # We need a vip port owned by Octavia for Act/Stby and failover
        try:
            port = {constants.PORT: {
                constants.NAME: 'octavia-lb-vrrp-' + amphora.id,
                constants.NETWORK_ID: subnet.network_id,
                constants.FIXED_IPS: [{'subnet_id': subnet.id}],
                constants.ADMIN_STATE_UP: True,
                constants.DEVICE_OWNER: OCTAVIA_OWNER}}
            new_port = self.neutron_client.create_port(port)
            new_port = utils.convert_port_dict_to_model(new_port)

            LOG.debug('Created vip port: %(port_id)s for amphora: %(amp)s',
                      {'port_id': new_port.id, 'amp': amphora.id})

        except Exception:
            message = _('Error creating the base (VRRP) port for the VIP with '
                        'port details: {}').format(port)
            LOG.exception(message)
            raise base.PlugVIPException(message)

        try:
            interface = self.plug_port(amphora, new_port)
        except Exception:
            message = _('Error plugging amphora (compute_id: {compute_id}) '
                        'into vip network {network_id}.').format(
                            compute_id=amphora.compute_id,
                            network_id=subnet.network_id)
            LOG.exception(message)
            try:
                if new_port:
                    self.neutron_client.delete_port(new_port.id)
                    LOG.debug('Deleted base (VRRP) port %s due to plug_port '
                              'failure.', new_port.id)
            except Exception:
                LOG.exception('Failed to delete base (VRRP) port %s after '
                              'plug_port failed. This resource is being '
                              'abandoned and should be manually deleted when '
                              'neutron is functional.', new_port.id)
            raise base.PlugVIPException(message)
        return interface

    def _add_vip_address_pair(self, port_id, vip_address):
        try:
            self._add_allowed_address_pair_to_port(port_id, vip_address)
        except neutron_client_exceptions.PortNotFoundClient as e:
            raise base.PortNotFound(str(e))
        except Exception:
            message = _('Error adding allowed address pair {ip} '
                        'to port {port_id}.').format(ip=vip_address,
                                                     port_id=port_id)
            LOG.exception(message)
            raise base.PlugVIPException(message)

    def _get_lb_security_group(self, load_balancer_id):
        sec_grp_name = common_utils.get_vip_security_group_name(
            load_balancer_id)
        sec_grps = self.neutron_client.list_security_groups(name=sec_grp_name)
        if sec_grps and sec_grps.get(constants.SECURITY_GROUPS):
            return sec_grps.get(constants.SECURITY_GROUPS)[0]
        return None

    def _get_ethertype_for_ip(self, ip):
        address = ipaddress.ip_address(
            ip if isinstance(ip, six.text_type) else six.u(ip))
        return 'IPv6' if address.version == 6 else 'IPv4'

    def _update_security_group_rules(self, load_balancer, sec_grp_id):
        rules = self.neutron_client.list_security_group_rules(
            security_group_id=sec_grp_id)

        updated_ports = []
        for l in load_balancer.listeners:
            if (l.provisioning_status in [constants.PENDING_DELETE,
                                          constants.DELETED]):
                continue

            protocol = constants.PROTOCOL_TCP.lower()
            if l.protocol == constants.PROTOCOL_UDP:
                protocol = constants.PROTOCOL_UDP.lower()

            if l.allowed_cidrs:
                for ac in l.allowed_cidrs:
                    port = (l.protocol_port, protocol, ac.cidr)
                    updated_ports.append(port)
            else:
                port = (l.protocol_port, protocol, None)
                updated_ports.append(port)

            # As the peer port will hold the tcp connection for keepalived and
            # haproxy session synchronization, so here the security group rule
            # should be just related with tcp protocol only.
            updated_ports.append(
                (l.peer_port, constants.PROTOCOL_TCP.lower(), None))

        # Just going to use port_range_max for now because we can assume that
        # port_range_max and min will be the same since this driver is
        # responsible for creating these rules
        old_ports = []
        for rule in rules.get('security_group_rules', []):
            # Don't remove egress rules and don't confuse other protocols with
            # None ports with the egress rules.  VRRP uses protocol 51 and 112
            if (rule.get('direction') == 'egress' or
                rule.get('protocol').upper() not in
                    [constants.PROTOCOL_TCP, constants.PROTOCOL_UDP]):
                continue
            old_ports.append((rule.get('port_range_max'),
                              rule.get('protocol').lower(),
                              rule.get('remote_ip_prefix')))

        add_ports = set(updated_ports) - set(old_ports)
        del_ports = set(old_ports) - set(updated_ports)
        for rule in rules.get('security_group_rules', []):
            if (rule.get('protocol', '') and
                    rule.get('protocol', '').lower() in ['tcp', 'udp'] and
                    (rule.get('port_range_max'), rule.get('protocol'),
                     rule.get('remote_ip_prefix')) in del_ports):
                rule_id = rule.get(constants.ID)
                try:
                    self.neutron_client.delete_security_group_rule(rule_id)
                except neutron_client_exceptions.NotFound:
                    LOG.info("Security group rule %s not found, will assume "
                             "it is already deleted.", rule_id)

        ethertype = self._get_ethertype_for_ip(load_balancer.vip.ip_address)
        for port_protocol in add_ports:
            self._create_security_group_rule(sec_grp_id, port_protocol[1],
                                             port_min=port_protocol[0],
                                             port_max=port_protocol[0],
                                             ethertype=ethertype,
                                             cidr=port_protocol[2])

        # Currently we are using the VIP network for VRRP
        # so we need to open up the protocols for it
        if load_balancer.topology == constants.TOPOLOGY_ACTIVE_STANDBY:
            try:
                self._create_security_group_rule(
                    sec_grp_id,
                    constants.VRRP_PROTOCOL_NUM,
                    direction='ingress',
                    ethertype=ethertype)
            except neutron_client_exceptions.Conflict:
                # It's ok if this rule already exists
                pass
            except Exception as e:
                raise base.PlugVIPException(str(e))

            try:
                self._create_security_group_rule(
                    sec_grp_id, constants.AUTH_HEADER_PROTOCOL_NUMBER,
                    direction='ingress', ethertype=ethertype)
            except neutron_client_exceptions.Conflict:
                # It's ok if this rule already exists
                pass
            except Exception as e:
                raise base.PlugVIPException(str(e))

    def _add_vip_security_group_to_port(self, load_balancer_id, port_id,
                                        sec_grp_id=None):
        sec_grp_id = (sec_grp_id or
                      self._get_lb_security_group(load_balancer_id).get(
                          constants.ID))
        try:
            self._add_security_group_to_port(sec_grp_id, port_id)
        except base.PortNotFound:
            raise
        except base.NetworkException as e:
            raise base.PlugVIPException(str(e))

    def _delete_vip_security_group(self, sec_grp):
        """Deletes a security group in neutron.

        Retries upon an exception because removing a security group from
        a neutron port does not happen immediately.
        """
        attempts = 0
        while attempts <= CONF.networking.max_retries:
            try:
                self.neutron_client.delete_security_group(sec_grp)
                LOG.info("Deleted security group %s", sec_grp)
                return
            except neutron_client_exceptions.NotFound:
                LOG.info("Security group %s not found, will assume it is "
                         "already deleted", sec_grp)
                return
            except Exception:
                LOG.warning("Attempt %(attempt)s to remove security group "
                            "%(sg)s failed.",
                            {'attempt': attempts + 1, 'sg': sec_grp})
            attempts += 1
            time.sleep(CONF.networking.retry_interval)
        message = _("All attempts to remove security group {0} have "
                    "failed.").format(sec_grp)
        LOG.exception(message)
        raise base.DeallocateVIPException(message)

    def _delete_security_group(self, vip, port):
        if self.sec_grp_enabled:
            sec_grp = self._get_lb_security_group(vip.load_balancer.id)
            if sec_grp:
                sec_grp_id = sec_grp.get(constants.ID)
                LOG.info(
                    "Removing security group %(sg)s from port %(port)s",
                    {'sg': sec_grp_id, constants.PORT: vip.port_id})
                raw_port = None
                try:
                    if port:
                        raw_port = self.neutron_client.show_port(port.id)
                except Exception:
                    LOG.warning('Unable to get port information for port '
                                '%s. Continuing to delete the security '
                                'group.', port.id)
                if raw_port:
                    sec_grps = raw_port.get(
                        constants.PORT, {}).get(constants.SECURITY_GROUPS, [])
                    if sec_grp_id in sec_grps:
                        sec_grps.remove(sec_grp_id)
                        port_update = {constants.PORT: {
                            constants.SECURITY_GROUPS: sec_grps}}
                        try:
                            self.neutron_client.update_port(port.id,
                                                            port_update)
                        except neutron_client_exceptions.PortNotFoundClient:
                            LOG.warning('Unable to update port information '
                                        'for port %s. Continuing to delete '
                                        'the security group since port not '
                                        'found', port.id)

                try:
                    self._delete_vip_security_group(sec_grp_id)
                except base.DeallocateVIPException:
                    # Try to delete any leftover ports on this security group.
                    # Because this security group is created and managed by us,
                    # it *should* only return ports that we own / can delete.
                    LOG.warning('Failed to delete security group on first '
                                'pass: %s', sec_grp_id)
                    extra_ports = self._get_ports_by_security_group(sec_grp_id)
                    for extra_port in extra_ports:
                        port_id = extra_port.get(constants.ID)
                        try:
                            LOG.warning('Deleting extra port %s on security '
                                        'group %s...', port_id, sec_grp_id)
                            self.neutron_client.delete_port(port_id)
                        except Exception:
                            LOG.warning('Failed to delete extra port %s on '
                                        'security group %s.',
                                        port_id, sec_grp_id)
                    # Now try it again
                    self._delete_vip_security_group(sec_grp_id)

    def deallocate_vip(self, vip):
        """Delete the vrrp_port (instance port) in case nova didn't

        This can happen if a failover has occurred.
        """
        for amphora in vip.load_balancer.amphorae:
            try:
                self.neutron_client.delete_port(amphora.vrrp_port_id)
            except (neutron_client_exceptions.NotFound,
                    neutron_client_exceptions.PortNotFoundClient):
                LOG.debug('VIP instance port %s already deleted. Skipping.',
                          amphora.vrrp_port_id)

        try:
            port = self.get_port(vip.port_id)
        except base.PortNotFound:
            LOG.warning("Can't deallocate VIP because the vip port {0} "
                        "cannot be found in neutron. "
                        "Continuing cleanup.".format(vip.port_id))
            port = None

        self._delete_security_group(vip, port)

        if port and port.device_owner == OCTAVIA_OWNER:
            try:
                self.neutron_client.delete_port(vip.port_id)
            except (neutron_client_exceptions.NotFound,
                    neutron_client_exceptions.PortNotFoundClient):
                LOG.debug('VIP port %s already deleted. Skipping.',
                          vip.port_id)
            except Exception:
                message = _('Error deleting VIP port_id {port_id} from '
                            'neutron').format(port_id=vip.port_id)
                LOG.exception(message)
                raise base.DeallocateVIPException(message)
        elif port:
            LOG.info("Port %s will not be deleted by Octavia as it was "
                     "not created by Octavia.", vip.port_id)

    def update_vip_sg(self, load_balancer, vip):
        if self.sec_grp_enabled:
            sec_grp = self._get_lb_security_group(load_balancer.id)
            if not sec_grp:
                sec_grp_name = common_utils.get_vip_security_group_name(
                    load_balancer.id)
                sec_grp = self._create_security_group(sec_grp_name)
            self._update_security_group_rules(load_balancer,
                                              sec_grp.get(constants.ID))
            self._add_vip_security_group_to_port(load_balancer.id, vip.port_id,
                                                 sec_grp.get(constants.ID))
            return sec_grp.get(constants.ID)
        return None

    def plug_aap_port(self, load_balancer, vip, amphora, subnet):
        interface = self._get_plugged_interface(
            amphora.compute_id, subnet.network_id, amphora.lb_network_ip)
        if not interface:
            interface = self._plug_amphora_vip(amphora, subnet)

        self._add_vip_address_pair(interface.port_id, vip.ip_address)
        if self.sec_grp_enabled:
            self._add_vip_security_group_to_port(load_balancer.id,
                                                 interface.port_id)
        vrrp_ip = None
        for fixed_ip in interface.fixed_ips:
            is_correct_subnet = fixed_ip.subnet_id == subnet.id
            is_management_ip = fixed_ip.ip_address == amphora.lb_network_ip
            if is_correct_subnet and not is_management_ip:
                vrrp_ip = fixed_ip.ip_address
                break
        return data_models.Amphora(
            id=amphora.id,
            compute_id=amphora.compute_id,
            vrrp_ip=vrrp_ip,
            ha_ip=vip.ip_address,
            vrrp_port_id=interface.port_id,
            ha_port_id=vip.port_id)

    # todo (xgerman): Delete later
    def plug_vip(self, load_balancer, vip):
        self.update_vip_sg(load_balancer, vip)
        plugged_amphorae = []
        subnet = self.get_subnet(vip.subnet_id)
        for amphora in six.moves.filter(
            lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                load_balancer.amphorae):
            plugged_amphorae.append(self.plug_aap_port(load_balancer, vip,
                                                       amphora, subnet))
        return plugged_amphorae

    def _validate_fixed_ip(self, fixed_ips, subnet_id, ip_address):
        """Validate an IP address exists in a fixed_ips dict

        :param fixed_ips: A port fixed_ups dict
        :param subnet_id: The subnet that should contain the IP
        :param ip_address: The IP address to validate
        :returns: True if the ip address is in the dict, False if not
        """
        for fixed_ip in fixed_ips:
            normalized_fixed_ip = ipaddress.ip_address(
                six.text_type(fixed_ip.ip_address)).compressed
            normalized_ip = ipaddress.ip_address(
                six.text_type(ip_address)).compressed
            if (fixed_ip.subnet_id == subnet_id and
                    normalized_fixed_ip == normalized_ip):
                return True
        return False

    @staticmethod
    def _fixed_ips_to_list_of_dicts(fixed_ips):
        list_of_dicts = []
        for fixed_ip in fixed_ips:
            list_of_dicts.append(fixed_ip.to_dict())
        return list_of_dicts

    def allocate_vip(self, load_balancer):
        if load_balancer.vip.port_id:
            try:
                port = self.get_port(load_balancer.vip.port_id)
                fixed_ip_found = self._validate_fixed_ip(
                    port.fixed_ips, load_balancer.vip.subnet_id,
                    load_balancer.vip.ip_address)
                if (port.network_id == load_balancer.vip.network_id and
                        fixed_ip_found):
                    LOG.info('Port %s already exists. Nothing to be done.',
                             load_balancer.vip.port_id)
                    return self._port_to_vip(port, load_balancer)
                LOG.error('Neutron VIP mis-match. Expected ip %s on '
                          'subnet %s in network %s. Neutron has fixed_ips %s '
                          'in network %s. Deleting and recreating the VIP '
                          'port.', load_balancer.vip.ip_address,
                          load_balancer.vip.subnet_id,
                          load_balancer.vip.network_id,
                          self._fixed_ips_to_list_of_dicts(port.fixed_ips),
                          port.network_id)
                if load_balancer.vip.octavia_owned:
                    self.delete_port(load_balancer.vip.port_id)
                else:
                    raise base.AllocateVIPException(
                        'VIP port {0} is broken, but is owned by project {1} '
                        'so will not be recreated. Aborting VIP allocation.'
                        .format(port.id, port.project_id))
            except base.AllocateVIPException as e:
                # Catch this explicitly because otherwise we blame Neutron
                LOG.error(getattr(e, constants.MESSAGE, None))
                raise
            except base.PortNotFound:
                LOG.warning('VIP port %s is missing from neutron. Rebuilding.',
                            load_balancer.vip.port_id)
            except Exception as e:
                message = _('Neutron is failing to service requests due to: '
                            '{}. Aborting.').format(str(e))
                LOG.error(message)
                raise base.AllocateVIPException(
                    message,
                    orig_msg=getattr(e, constants.MESSAGE, None),
                    orig_code=getattr(e, constants.STATUS_CODE, None),)

        fixed_ip = {}
        if load_balancer.vip.subnet_id:
            fixed_ip['subnet_id'] = load_balancer.vip.subnet_id
        if load_balancer.vip.ip_address:
            fixed_ip[constants.IP_ADDRESS] = load_balancer.vip.ip_address

        # Make sure we are backward compatible with older neutron
        if self._check_extension_enabled(PROJECT_ID_ALIAS):
            project_id_key = 'project_id'
        else:
            project_id_key = 'tenant_id'

        # It can be assumed that network_id exists
        port = {constants.PORT: {
            constants.NAME: 'octavia-lb-' + load_balancer.id,
            constants.NETWORK_ID: load_balancer.vip.network_id,
            constants.ADMIN_STATE_UP: False,
            'device_id': 'lb-{0}'.format(load_balancer.id),
            constants.DEVICE_OWNER: OCTAVIA_OWNER,
            project_id_key: load_balancer.project_id}}

        if fixed_ip:
            port[constants.PORT][constants.FIXED_IPS] = [fixed_ip]
        try:
            new_port = self.neutron_client.create_port(port)
        except Exception as e:
            message = _('Error creating neutron port on network '
                        '{network_id} due to {e}.').format(
                network_id=load_balancer.vip.network_id, e=str(e))
            LOG.exception(message)
            raise base.AllocateVIPException(
                message,
                orig_msg=getattr(e, constants.MESSAGE, None),
                orig_code=getattr(e, constants.STATUS_CODE, None),
            )
        new_port = utils.convert_port_dict_to_model(new_port)
        return self._port_to_vip(new_port, load_balancer, octavia_owned=True)

    def unplug_aap_port(self, vip, amphora, subnet):
        interface = self._get_plugged_interface(
            amphora.compute_id, subnet.network_id, amphora.lb_network_ip)
        if not interface:
            # Thought about raising PluggedVIPNotFound exception but
            # then that wouldn't evaluate all amphorae, so just continue
            LOG.debug('Cannot get amphora %s interface, skipped',
                      amphora.compute_id)
            return
        try:
            self.unplug_network(amphora.compute_id, subnet.network_id)
        except Exception:
            pass
        try:
            aap_update = {constants.PORT: {
                constants.ALLOWED_ADDRESS_PAIRS: []
            }}
            self.neutron_client.update_port(interface.port_id,
                                            aap_update)
        except Exception:
            message = _('Error unplugging VIP. Could not clear '
                        'allowed address pairs from port '
                        '{port_id}.').format(port_id=vip.port_id)
            LOG.exception(message)
            raise base.UnplugVIPException(message)

        # Delete the VRRP port if we created it
        try:
            port = self.get_port(amphora.vrrp_port_id)
            if port.name.startswith('octavia-lb-vrrp-'):
                self.neutron_client.delete_port(amphora.vrrp_port_id)
        except (neutron_client_exceptions.NotFound,
                neutron_client_exceptions.PortNotFoundClient):
            pass
        except Exception as e:
            LOG.error('Failed to delete port.  Resources may still be in '
                      'use for port: %(port)s due to error: %(except)s',
                      {constants.PORT: amphora.vrrp_port_id, 'except': e})

    def unplug_vip(self, load_balancer, vip):
        try:
            subnet = self.get_subnet(vip.subnet_id)
        except base.SubnetNotFound:
            msg = ("Can't unplug vip because vip subnet {0} was not "
                   "found").format(vip.subnet_id)
            LOG.exception(msg)
            raise base.PluggedVIPNotFound(msg)
        for amphora in six.moves.filter(
                lambda amp: amp.status == constants.AMPHORA_ALLOCATED,
                load_balancer.amphorae):
            self.unplug_aap_port(vip, amphora, subnet)

    def plug_network(self, compute_id, network_id, ip_address=None):
        try:
            interface = self.compute.attach_network_or_port(
                compute_id=compute_id, network_id=network_id,
                ip_address=ip_address)
        except exceptions.NotFound as e:
            if 'Instance' in str(e):
                raise base.AmphoraNotFound(str(e))
            if 'Network' in str(e):
                raise base.NetworkNotFound(str(e))
            raise base.PlugNetworkException(str(e))
        except Exception:
            message = _('Error plugging amphora (compute_id: {compute_id}) '
                        'into network {network_id}.').format(
                            compute_id=compute_id,
                            network_id=network_id)
            LOG.exception(message)
            raise base.PlugNetworkException(message)

        return self._nova_interface_to_octavia_interface(compute_id, interface)

    def unplug_network(self, compute_id, network_id, ip_address=None):
        interfaces = self.get_plugged_networks(compute_id)
        if not interfaces:
            msg = ('Amphora with compute id {compute_id} does not have any '
                   'plugged networks').format(compute_id=compute_id)
            raise base.NetworkNotFound(msg)

        unpluggers = self._get_interfaces_to_unplug(interfaces, network_id,
                                                    ip_address=ip_address)
        for index, unplugger in enumerate(unpluggers):
            self.compute.detach_port(
                compute_id=compute_id, port_id=unplugger.port_id)

    def update_vip(self, load_balancer, for_delete=False):
        sec_grp = self._get_lb_security_group(load_balancer.id)
        if sec_grp:
            self._update_security_group_rules(load_balancer,
                                              sec_grp.get(constants.ID))
        elif not for_delete:
            raise exceptions.MissingVIPSecurityGroup(lb_id=load_balancer.id)
        else:
            LOG.warning('VIP security group missing when updating the VIP for '
                        'delete on load balancer: {lb_id}. Skipping update '
                        'because this is for delete.'.format(
                            lb_id=load_balancer.id))

    def failover_preparation(self, amphora):
        if self.dns_integration_enabled:
            self._failover_preparation(amphora)

    def _failover_preparation(self, amphora):
        interfaces = self.get_plugged_networks(compute_id=amphora.compute_id)

        ports = []
        for interface_ in interfaces:
            port = self.get_port(port_id=interface_.port_id)
            ips = port.fixed_ips
            lb_network = False
            for ip in ips:
                if ip.ip_address == amphora.lb_network_ip:
                    lb_network = True
            if not lb_network:
                ports.append(port)

        for port in ports:
            try:
                self.neutron_client.update_port(
                    port.id, {constants.PORT: {'dns_name': ''}})

            except (neutron_client_exceptions.NotFound,
                    neutron_client_exceptions.PortNotFoundClient):
                raise base.PortNotFound()

    def plug_port(self, amphora, port):
        try:
            interface = self.compute.attach_network_or_port(
                compute_id=amphora.compute_id, network_id=None,
                ip_address=None, port_id=port.id)
            plugged_interface = self._nova_interface_to_octavia_interface(
                amphora.compute_id, interface)
        except exceptions.NotFound as e:
            if 'Instance' in str(e):
                raise base.AmphoraNotFound(str(e))
            if 'Network' in str(e):
                raise base.NetworkNotFound(str(e))
            raise base.PlugNetworkException(str(e))
        except nova_client_exceptions.Conflict:
            LOG.info('Port %(portid)s is already plugged, '
                     'skipping', {'portid': port.id})
            plugged_interface = n_data_models.Interface(
                compute_id=amphora.compute_id,
                network_id=port.network_id,
                port_id=port.id,
                fixed_ips=port.fixed_ips)
        except Exception:
            message = _('Error plugging amphora (compute_id: '
                        '{compute_id}) into port '
                        '{port_id}.').format(
                            compute_id=amphora.compute_id,
                            port_id=port.id)
            LOG.exception(message)
            raise base.PlugNetworkException(message)

        return plugged_interface

    def _get_amp_net_configs(self, amp, amp_configs, vip_subnet, vip_port):
        if amp.status != constants.DELETED:
            LOG.debug("Retrieving network details for amphora %s", amp.id)
            vrrp_port = self.get_port(amp.vrrp_port_id)
            vrrp_subnet = self.get_subnet(
                vrrp_port.get_subnet_id(amp.vrrp_ip))
            vrrp_port.network = self.get_network(vrrp_port.network_id)
            ha_port = self.get_port(amp.ha_port_id)
            ha_subnet = self.get_subnet(
                ha_port.get_subnet_id(amp.ha_ip))

            amp_configs[amp.id] = n_data_models.AmphoraNetworkConfig(
                amphora=amp,
                vip_subnet=vip_subnet,
                vip_port=vip_port,
                vrrp_subnet=vrrp_subnet,
                vrrp_port=vrrp_port,
                ha_subnet=ha_subnet,
                ha_port=ha_port
            )

    def get_network_configs(self, loadbalancer, amphora=None):
        vip_subnet = self.get_subnet(loadbalancer.vip.subnet_id)
        vip_port = self.get_port(loadbalancer.vip.port_id)
        amp_configs = {}
        if amphora:
            self._get_amp_net_configs(amphora, amp_configs,
                                      vip_subnet, vip_port)
        else:
            for amp in loadbalancer.amphorae:
                try:
                    self._get_amp_net_configs(amp, amp_configs,
                                              vip_subnet, vip_port)
                except Exception as e:
                    LOG.warning('Getting network configurations for amphora '
                                '%(amp)s failed due to %(err)s.',
                                {'amp': amp.id, 'err': str(e)})
        return amp_configs

    # TODO(johnsom) This may be dead code now. Remove in failover for v2 patch
    def wait_for_port_detach(self, amphora):
        """Waits for the amphora ports device_id to be unset.

        This method waits for the ports on an amphora device_id
        parameter to be '' or None which signifies that nova has
        finished detaching the port from the instance.

        :param amphora: Amphora to wait for ports to detach.
        :returns: None
        :raises TimeoutException: Port did not detach in interval.
        :raises PortNotFound: Port was not found by neutron.
        """
        interfaces = self.get_plugged_networks(compute_id=amphora.compute_id)

        ports = []
        port_detach_timeout = CONF.networking.port_detach_timeout
        for interface_ in interfaces:
            port = self.get_port(port_id=interface_.port_id)
            ips = port.fixed_ips
            lb_network = False
            for ip in ips:
                if ip.ip_address == amphora.lb_network_ip:
                    lb_network = True
            if not lb_network:
                ports.append(port)

        for port in ports:
            try:
                neutron_port = self.neutron_client.show_port(
                    port.id).get(constants.PORT)
                device_id = neutron_port['device_id']
                start = int(time.time())

                while device_id:
                    time.sleep(CONF.networking.retry_interval)
                    neutron_port = self.neutron_client.show_port(
                        port.id).get(constants.PORT)
                    device_id = neutron_port['device_id']

                    timed_out = int(time.time()) - start >= port_detach_timeout

                    if device_id and timed_out:
                        message = ('Port %s failed to detach (device_id %s) '
                                   'within the required time (%s s).' %
                                   (port.id, device_id, port_detach_timeout))
                        raise base.TimeoutException(message)

            except (neutron_client_exceptions.NotFound,
                    neutron_client_exceptions.PortNotFoundClient):
                pass

    def delete_port(self, port_id):
        """delete a neutron port.

        :param port_id: The port ID to delete.
        :returns: None
        """
        try:
            self.neutron_client.delete_port(port_id)
        except (neutron_client_exceptions.NotFound,
                neutron_client_exceptions.PortNotFoundClient):
            LOG.debug('VIP instance port %s already deleted. Skipping.',
                      port_id)
        except Exception as e:
            raise exceptions.NetworkServiceError(net_error=str(e))

    def set_port_admin_state_up(self, port_id, state):
        """Set the admin state of a port. True is up, False is down.

        :param port_id: The port ID to update.
        :param state: True for up, False for down.
        :returns: None
        """
        try:
            self.neutron_client.update_port(
                port_id, {constants.PORT: {constants.ADMIN_STATE_UP: state}})
        except (neutron_client_exceptions.NotFound,
                neutron_client_exceptions.PortNotFoundClient) as e:
            raise base.PortNotFound(str(e))
        except Exception as e:
            raise exceptions.NetworkServiceError(net_error=str(e))

    def create_port(self, network_id, name=None, fixed_ips=(),
                    secondary_ips=(), security_group_ids=(),
                    admin_state_up=True, qos_policy_id=None):
        """Creates a network port.

        fixed_ips = [{'subnet_id': <id>, ('ip_addrss': <IP>')},]
        ip_address is optional in the fixed_ips dictionary.

        :param network_id: The network the port should be created on.
        :param name: The name to apply to the port.
        :param fixed_ips: A list of fixed IP dicts.
        :param secondary_ips: A list of secondary IPs to add to the port.
        :param security_group_ids: A list of security group IDs for the port.
        :param qos_policy_id: The QoS policy ID to apply to the port.
        :returns port: A port data model object.
        """
        try:
            aap_list = []
            for ip in secondary_ips:
                aap_list.append({constants.IP_ADDRESS: ip})
            port = {constants.NETWORK_ID: network_id,
                    constants.ADMIN_STATE_UP: admin_state_up,
                    constants.DEVICE_OWNER: OCTAVIA_OWNER}
            if aap_list:
                port[constants.ALLOWED_ADDRESS_PAIRS] = aap_list
            if fixed_ips:
                port[constants.FIXED_IPS] = fixed_ips
            if name:
                port[constants.NAME] = name
            if qos_policy_id:
                port[constants.QOS_POLICY_ID] = qos_policy_id
            if security_group_ids:
                port[constants.SECURITY_GROUPS] = security_group_ids

            new_port = self.neutron_client.create_port({constants.PORT: port})

            LOG.debug('Created port: %(port)s', {constants.PORT: new_port})

            return utils.convert_port_dict_to_model(new_port)
        except Exception as e:
            message = _('Error creating a port on network '
                        '{network_id} due to {error}.').format(
                network_id=network_id, error=str(e))
            LOG.exception(message)
            raise base.CreatePortException(message)

    def get_security_group(self, sg_name):
        """Retrieves the security group by it's name.

        :param sg_name: The security group name.
        :return: octavia.network.data_models.SecurityGroup, None if not enabled
        :raises: NetworkException, SecurityGroupNotFound
        """
        try:
            if self.sec_grp_enabled and sg_name:
                sec_grps = self.neutron_client.list_security_groups(
                    name=sg_name)
                if sec_grps and sec_grps.get(constants.SECURITY_GROUPS):
                    sg_dict = sec_grps.get(constants.SECURITY_GROUPS)[0]
                    return utils.convert_security_group_dict_to_model(sg_dict)
                message = _('Security group {name} not found.').format(
                    name=sg_name)
                raise base.SecurityGroupNotFound(message)
            return None
        except base.SecurityGroupNotFound:
            raise
        except Exception as e:
            message = _('Error when getting security group {name} due to '
                        '{error}').format(name=sg_name, error=str(e))
            LOG.exception(message)
            raise base.NetworkException(message)
