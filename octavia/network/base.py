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

import abc

import six

from octavia.common import exceptions


class NetworkException(exceptions.OctaviaException):
    pass


class PlugVIPException(NetworkException):
    pass


class UnplugVIPException(NetworkException):
    pass


class AllocateVIPException(NetworkException):
    pass


class DeallocateVIPException(NetworkException):
    pass


class PlugNetworkException(NetworkException):
    pass


class UnplugNetworkException(NetworkException):
    pass


class VIPInUseException(NetworkException):
    pass


class PortNotFound(NetworkException):
    pass


class NetworkNotFound(NetworkException):
    pass


class SubnetNotFound(NetworkException):
    pass


class AmphoraNotFound(NetworkException):
    pass


class PluggedVIPNotFound(NetworkException):
    pass


class TimeoutException(NetworkException):
    pass


class QosPolicyNotFound(NetworkException):
    pass


class SecurityGroupNotFound(NetworkException):
    pass


class CreatePortException(NetworkException):
    pass


@six.add_metaclass(abc.ABCMeta)
class AbstractNetworkDriver(object):
    """This class defines the methods for a fully functional network driver.

    Implementations of this interface can expect a rollback to occur if any of
    the non-nullipotent methods raise an exception.
    """

    @abc.abstractmethod
    def allocate_vip(self, load_balancer):
        """Allocates a virtual ip.

        Reserves it for later use as the frontend connection of a load
        balancer.

        :param load_balancer: octavia.common.data_models.LoadBalancer instance
        :return: octavia.common.data_models.VIP
        :raises: AllocateVIPException, PortNotFound, SubnetNotFound
        """

    @abc.abstractmethod
    def create_port(self, network_id, name=None, fixed_ips=(),
                    secondary_ips=(), security_group_ids=(),
                    admin_state_up=True, qos_policy_id=None):
        """Creates a network port.

        fixed_ips = [{'subnet_id': <id>, ('ip_address': <IP>')},]
        ip_address is optional in the fixed_ips dictionary.

        :param network_id: The network the port should be created on.
        :param name: The name to apply to the port.
        :param fixed_ips: A list of fixed IP dicts.
        :param secondary_ips: A list of secondary IPs to add to the port.
        :param security_group_ids: A list of security group IDs for the port.
        :param qos_policy_id: The QoS policy ID to apply to the port.
        :returns port: A port data model object.
        """

    @abc.abstractmethod
    def deallocate_vip(self, vip):
        """Removes any resources that reserved this virtual ip.

        :param vip: octavia.common.data_models.VIP instance
        :return: None
        :raises: DeallocateVIPException, VIPInUseException,
                 VIPConfiigurationNotFound
        """

    @abc.abstractmethod
    def delete_port(self, port_id):
        """Delete a network port.

        :param port_id: The port ID to delete.
        :returns: None
        """

    @abc.abstractmethod
    def plug_vip(self, load_balancer, vip):
        """Plugs a virtual ip as the frontend connection of a load balancer.

        Sets up the routing of traffic from the vip to the load balancer
        and its amphorae.

        :param load_balancer: octavia.common.data_models.LoadBalancer instance
        :param vip: octavia.common.data_models.VIP instance
        :return: dict consisting of amphora_id as key and bind_ip as value.
                 bind_ip is the ip that the amphora should listen on to
                 receive traffic to load balance.
        :raises: PlugVIPException, PortNotFound
        """

    @abc.abstractmethod
    def unplug_vip(self, load_balancer, vip):
        """Unplugs a virtual ip as the frontend connection of a load balancer.

        Removes the routing of traffic from the vip to the load balancer
        and its amphorae.

        :param load_balancer: octavia.common.data_models.LoadBalancer instance
        :param vip: octavia.common.data_models.VIP instance
        :return: octavia.common.data_models.VIP instance
        :raises: UnplugVIPException, PluggedVIPNotFound
        """

    @abc.abstractmethod
    def plug_network(self, compute_id, network_id, ip_address=None):
        """Connects an existing amphora to an existing network.

        :param compute_id: id of an amphora in the compute service
        :param network_id: id of a network
        :param ip_address: ip address to attempt to be assigned to interface
        :return: octavia.network.data_models.Interface instance
        :raises: PlugNetworkException, AmphoraNotFound, NetworkNotFound
        """

    @abc.abstractmethod
    def unplug_network(self, compute_id, network_id, ip_address=None):
        """Disconnects an existing amphora from an existing network.

        If ip_address is not specificed, all the interfaces plugged on
        network_id should be unplugged.

        :param compute_id: id of an amphora in the compute service
        :param network_id: id of a network
        :param ip_address: specific ip_address to unplug
        :return: None
        :raises: UnplugNetworkException, AmphoraNotFound, NetworkNotFound,
                 NetworkException
        """

    @abc.abstractmethod
    def get_plugged_networks(self, compute_id):
        """Retrieves the current plugged networking configuration.

        :param compute_id: id of an amphora in the compute service
        :return: [octavia.network.data_models.Instance]
        """

    def update_vip(self, load_balancer, for_delete):
        """Hook for the driver to update the VIP information.

        This method will be called upon the change of a load_balancer
        configuration. It is an optional method to be implemented by drivers.
        It allows the driver to update any VIP information based on the
        state of the passed in load_balancer.

        :param load_balancer: octavia.common.data_models.LoadBalancer instance
        :param for_delete: Boolean indicating if this update is for a delete
        :raises: MissingVIPSecurityGroup
        :return: None
        """

    @abc.abstractmethod
    def get_network(self, network_id, context=None):
        """Retrieves network from network id.

        :param network_id: id of an network to retrieve
        :param context: A request context
        :return: octavia.network.data_models.Network
        :raises: NetworkException, NetworkNotFound
        """

    @abc.abstractmethod
    def get_subnet(self, subnet_id, context=None):
        """Retrieves subnet from subnet id.

        :param subnet_id: id of a subnet to retrieve
        :param context: A request context
        :return: octavia.network.data_models.Subnet
        :raises: NetworkException, SubnetNotFound
        """

    @abc.abstractmethod
    def get_port(self, port_id, context=None):
        """Retrieves port from port id.

        :param port_id: id of a port to retrieve
        :param context: A request context
        :return: octavia.network.data_models.Port
        :raises: NetworkException, PortNotFound
        """

    @abc.abstractmethod
    def get_network_by_name(self, network_name):
        """Retrieves network from network name.

        :param network_name: name of a network to retrieve
        :return: octavia.network.data_models.Network
        :raises: NetworkException, NetworkNotFound
        """

    @abc.abstractmethod
    def get_subnet_by_name(self, subnet_name):
        """Retrieves subnet from subnet name.

        :param subnet_name: name of a subnet to retrieve
        :return: octavia.network.data_models.Subnet
        :raises: NetworkException, SubnetNotFound
        """

    @abc.abstractmethod
    def get_port_by_name(self, port_name):
        """Retrieves port from port name.

        :param port_name: name of a port to retrieve
        :return: octavia.network.data_models.Port
        :raises: NetworkException, PortNotFound
        """

    @abc.abstractmethod
    def get_port_by_net_id_device_id(self, network_id, device_id):
        """Retrieves port from network id and device id.

        :param network_id: id of a network to filter by
        :param device_id: id of a network device to filter by
        :return: octavia.network.data_models.Port
        :raises: NetworkException, PortNotFound
        """

    @abc.abstractmethod
    def get_security_group(self, sg_name):
        """Retrieves the security group by it's name.

        :param sg_name: The security group name.
        :return: octavia.network.data_models.SecurityGroup, None if not enabled
        :raises: NetworkException, SecurityGroupNotFound
        """

    @abc.abstractmethod
    def failover_preparation(self, amphora):
        """Prepare an amphora for failover.

        :param amphora: amphora object to failover
        :return: None
        :raises: PortNotFound
        """

    @abc.abstractmethod
    def plug_port(self, amphora, port):
        """Plug a neutron port in to a compute instance

        :param amphora: amphora object to plug the port into
        :param port: port to plug into the compute instance
        :return: None
        :raises: PlugNetworkException, AmphoraNotFound, NetworkNotFound
        """

    @abc.abstractmethod
    def get_network_configs(self, load_balancer, amphora=None):
        """Retrieve network configurations

        This method assumes that a dictionary of AmphoraNetworkConfigs keyed
        off of the related amphora id are returned.
        The configs contain data pertaining to each amphora that is later
        used for finalization of the entire load balancer configuration.
        The data provided to these configs is left up to the driver, this
        means the driver is responsible for providing data that is appropriate
        for the amphora network configurations.

        Example return: {<amphora.id>: <AmphoraNetworkConfig>}

        :param load_balancer: The load_balancer configuration
        :param amphora: Optional amphora to only query.
        :return: dict of octavia.network.data_models.AmphoraNetworkConfig
                 keyed off of the amphora id the config is associated with.
        :raises: NotFound, NetworkNotFound, SubnetNotFound, PortNotFound
        """

    @abc.abstractmethod
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

    @abc.abstractmethod
    def update_vip_sg(self, load_balancer, vip):
        """Updates the security group for a VIP

        :param load_balancer: Load Balancer to rpepare the VIP for
        :param vip: The VIP to plug
        """

    @abc.abstractmethod
    def plug_aap_port(self, load_balancer, vip, amphora, subnet):
        """Plugs the AAP port to the amp

        :param load_balancer: Load Balancer to prepare the VIP for
        :param vip: The VIP to plug
        :param amphora: The amphora to plug the VIP into
        :param subnet: The subnet to plug the aap into
        """

    @abc.abstractmethod
    def unplug_aap_port(self, vip, amphora, subnet):
        """Unplugs the AAP port to the amp

        :param vip: The VIP to plug
        :param amphora: The amphora to plug the VIP into
        :param subnet: The subnet to plug the aap into
        """

    @abc.abstractmethod
    def qos_enabled(self):
        """Whether QoS is enabled

        :return: Boolean
        """

    @abc.abstractmethod
    def get_network_ip_availability(self, network):
        """Retrieves network IP availability.

        :param network: octavia.network.data_models.Network
        :return: octavia.network.data_models.Network_IP_Availability
        :raises: NetworkException, NetworkNotFound
        """

    @abc.abstractmethod
    def set_port_admin_state_up(self, port_id, state):
        """Set the admin state of a port. True is up, False is down.

        :param port_id: The port ID to update.
        :param state: True for up, False for down.
        :returns: None
        """
