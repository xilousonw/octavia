from oslo_config import cfg
from oslo_log import log as logging

from octavia.api.drivers.amphora_driver.v2 import driver
from octavia.common import constants as consts
from octavia.db import api as db_apis
from dptech_octavia.utils import driver_utils