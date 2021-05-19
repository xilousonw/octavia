from stevedore import driver
from oslo_config import cfg
from oslo_log import log as logging

from dptech_octavia.common import constants
from octavia_lib.api.drivers import data_models

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


def pending_delete(obj):
    return obj.provisioning_status == constants.PENDING_DELETE


def get_network_driver():
    CONF.import_group('controller_worker', 'octavia.common.config')
    return driver.DriverManager(
        namespace='octavia.network.drivers',
        name=CONF.controller_worker.network_driver,
        invoke_on_load=True
    ).driver


def lb_to_vip_obj(lb):
    vip_obj = data_models.VIP()
    if lb.vip_address:
        vip_obj.ip_address = lb.vip_address
    if lb.vip_network_id:
        vip_obj.network_id = lb.vip_netwrok_id
    if lb.vip_port_id:
        vip_obj.port_id = lb.vip_port_id
    if lb.vip_subnet_id:
        vip_obj.vip_subnet_id = lb.vip_subnet_id
    if lb.vip_qos_policy_id:
        vip_obj.vip_qos_policy_id = lb.vip_qos_policy_id
    vip_obj.load_balancer = lb
    return vip_obj

