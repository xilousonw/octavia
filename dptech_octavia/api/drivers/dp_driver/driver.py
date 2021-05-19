from oslo_config import cfg
from oslo_log import log as logging

from octavia.api.drivers.amphora_driver.v2 import driver
from octavia.common import constants as consts
from octavia.db import api as db_apis
from dptech_octavia.utils import driver_utils
from octavia_lib.api.drivers import data_models as driver_dm
from octavia_lib.api.drivers import exceptions

CONF = cfg.CONF
CONF.import_group('oslo_messaging', 'octavia.common.config')
LOG = logging.getLogger(__name__)


class DPtechProviderDriver(driver.AmphoraProviderDriver):
    def __init__(self):
        super(DPtechProviderDriver,self).__init__()

    def _get_server(self, loadbalancer_id):
        """
        Get scheduled host of the loadbalancer
        :param loadbalancer_id:
        :return: scheduled host
        """
        loadbalancer = self.repositories.load_balancer.get(db_apis.get_session(), id=loadbalancer_id)
        if loadbalancer.server_group_id:
            return loadbalancer.server_group_id
        else:
            # fetch scheduled server from VIP port
            network_driver = driver_utils.get_network_driver()
            return network_driver.get_scheduled_host(loadbalancer.vip_port_id)

    def loadbalancer_create(self, loadbalancer):
        if loadbalancer.flavor == driver_dm.Unset:
            loadbalancer.flavor = None

        network_driver = driver_utils.get_network_driver()
        host = network_driver.get_scheduled_host(loadbalancer.vip_port_id)

        LOG.info("Scheduling loadbalancer %s to %s", loadbalancer.loadbalancer_id, host)
        payload = {
            consts.LOAD_BALANCER_ID: loadbalancer.loadbalancer_id,
            consts.FLAVOR: loadbalancer.flavor
        }
        client = self.client.prepare(server=host)
        client.cast({}, 'create_load_balancer', **payload)

    def loadbalancer_delete(self, loadbalancer, cascade=False):
        loadbalancer_id = loadbalancer.loadbalancer_id
        payload = {
            consts.LOAD_BALANCER_ID: loadbalancer_id,
            'cascade': cascade
        }
        client =  self.client.prepare(server=self._get_server(loadbalancer_id))
        client.cast({}, 'delete_load_balancer', **payload)

    def loadbalancer_failover(self, loadbalancer_id):
        payload = {
            consts.LOAD_BALANCER_ID: loadbalancer_id,
        }
        client = self.client.prepare(server=self._get_server(loadbalancer_id))
        client.cast({}, 'faileover_load_balancer', **payload)

    def loadbalancer_update(self, old_loadbalancer, new_loadbalancer):
        lb_id = new_loadbalancer.loadbalancer_id
        payload = {
            consts.LOAD_BALANCER_ID: lb_id,
            consts.LOAD_BALANCER_UPDATES: {}
        }
        client = self.client.prepare(server=self._get_server(lb_id))
        client.cast({}, 'update_load_balancer', **payload)

    def loadbalancer_migrate(self, loadbalancer_id, target_host):
        payload = {
            consts.LOAD_BALANCER_ID: loadbalancer_id,
            'target_host': target_host
        }
        client = self.client.prepare(server=self._get_server(loadbalancer_id))
        client.cast({}, 'migrate_load_balancer', **payload)

    def loadbalancers_migrate(self, source_host, target_host):
        payload = {
            'source_host': source_host,
            'target_host': target_host
        }
        client = self.client.prepare(server=source_host)
        client.cast({}, 'migrate_load_balancers', **payload)

    #listener
    def listener_create(self, listener):
        pass

    def listener_delete(self, listener):
        pass

    def listener_update(self, old_listener, new_listener):
        pass

    #pool
    def pool_create(self, pool):
        pass

    def pool_delete(self, pool):
        pass

    def pool_update(self, old_pool, new_pool):
        pass

    #member
    def member_create(self, member):
        pass

    def member_delete(self, member):
        pass

    def member_update(self, old_member, new_member):
        pass

    def member_batch_update(self, members):
        pass

    #health monitor
    def health_monitor_create(self, healthmonitor):
        pass

    def health_monitor_delete(self, healthmonitor):
        pass

    def health_monitor_update(self, old_healthmonitor, new_healthmonitor):
        pass

    #l7 policy
    def l7policy_create(self, l7policy):
        pass

    def l7policy_delete(self, l7policy):
        pass

    def l7policy_update(self, old_l7policy, new_l7policy):
        pass

    #l7rule
    def l7rule_create(self, l7rule):
        pass

    def l7rule_delete(self, l7rule):
        pass

    def l7rule_update(self, old_l7rule, new_l7rule):
        pass

    def create_vip_port(self, loadbalancer_id, project_id, vip_dictionary):
        # let octavia create the port
        raise  exceptions.NotImplementedError()

    def loadbalancer_failover(self, loadbalancer_id):
        raise exceptions.NotImplementedError()

    def get_supported_availability_zone_metadata(self):
        raise exceptions.NotImplementedError()

    def validate_flavor(self, flavor_dict):
        """
        Validates if driver can support flavor as defined in flavor_metadata.
        :param flavor_dict:
        :return: nothing if the flavor is valid and supported
        :raises NotImplementedError: The driver does not support flavors.
        """
        raise exceptions.NotImplementedError()