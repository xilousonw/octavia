from dptechnologylb.common import constants
from eventlet import greenthread
from neutron.agent.linux import utils
from neutron.common import rpc as n_rpc
from neutron.extensions import agent as ext_agent
from neutron_lib.utils import helpers
from oslo_config import cfg
from oslo_log import log as loging
from oslo_serialization import jsonutils
from oslo_utils import encodeutils
import oslo_messaging
import socket


LOG = loging.getLogger(__name__)


def get_configuration_dict(agent_db):
    try:
        conf = jsonutils.loads(agent_db.configuration)
    except Exception:
        msg = 'Configuration for agent %(agent_type)s on ' + 'host %(host)s is invalid.'
        LOG.warn(msg, {'agent_type':agent_db.agent_type,
                       'host': agent_db.host})
        conf = {}
    return conf


def make_agent_dict(agent, fields=None):
    pass


