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
#

from cryptography import fernet
from oslo_config import cfg
from oslo_log import log as logging
from stevedore import driver as stevedore_driver
from taskflow import task
from taskflow.types import failure

from octavia.amphorae.backends.agent import agent_jinja_cfg
from octavia.amphorae.driver_exceptions import exceptions as driver_except
from octavia.common import constants
from octavia.common import utils
from octavia.controller.worker import task_utils as task_utilities
from octavia.db import api as db_apis
from octavia.db import repositories as repo

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BaseAmphoraTask(task.Task):
    """Base task to load drivers common to the tasks."""

    def __init__(self, **kwargs):
        super(BaseAmphoraTask, self).__init__(**kwargs)
        self.amphora_driver = stevedore_driver.DriverManager(
            namespace='octavia.amphora.drivers',
            name=CONF.controller_worker.amphora_driver,
            invoke_on_load=True
        ).driver
        self.amphora_repo = repo.AmphoraRepository()
        self.listener_repo = repo.ListenerRepository()
        self.loadbalancer_repo = repo.LoadBalancerRepository()
        self.task_utils = task_utilities.TaskUtils()


class AmpListenersUpdate(BaseAmphoraTask):
    """Task to update the listeners on one amphora."""

    def execute(self, loadbalancer, amphora, timeout_dict=None):
        # Note, we don't want this to cause a revert as it may be used
        # in a failover flow with both amps failing. Skip it and let
        # health manager fix it.
        try:
            # Make sure we have a fresh load balancer object
            loadbalancer = self.loadbalancer_repo.get(db_apis.get_session(),
                                                      id=loadbalancer.id)
            self.amphora_driver.update_amphora_listeners(
                loadbalancer, amphora, timeout_dict)
        except Exception as e:
            LOG.error('Failed to update listeners on amphora %s. Skipping '
                      'this amphora as it is failing to update due to: %s',
                      amphora.id, str(e))
            self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                     status=constants.ERROR)


class AmphoraIndexListenerUpdate(BaseAmphoraTask):
    """Task to update the listeners on one amphora."""

    def execute(self, loadbalancer, amphora_index, amphorae,
                timeout_dict=None):
        # Note, we don't want this to cause a revert as it may be used
        # in a failover flow with both amps failing. Skip it and let
        # health manager fix it.
        try:
            # Make sure we have a fresh load balancer object
            loadbalancer = self.loadbalancer_repo.get(db_apis.get_session(),
                                                      id=loadbalancer.id)
            self.amphora_driver.update_amphora_listeners(
                loadbalancer, amphorae[amphora_index], timeout_dict)
        except Exception as e:
            amphora_id = amphorae[amphora_index].id
            LOG.error('Failed to update listeners on amphora %s. Skipping '
                      'this amphora as it is failing to update due to: %s',
                      amphora_id, str(e))
            self.amphora_repo.update(db_apis.get_session(), amphora_id,
                                     status=constants.ERROR)


class ListenersUpdate(BaseAmphoraTask):
    """Task to update amphora with all specified listeners' configurations."""

    def execute(self, loadbalancer):
        """Execute updates per listener for an amphora."""
        self.amphora_driver.update(loadbalancer)

    def revert(self, loadbalancer, *args, **kwargs):
        """Handle failed listeners updates."""

        LOG.warning("Reverting listeners updates.")

        for listener in loadbalancer.listeners:
            self.task_utils.mark_listener_prov_status_error(listener.id)


class ListenersStart(BaseAmphoraTask):
    """Task to start all listeners on the vip."""

    def execute(self, loadbalancer, amphora=None):
        """Execute listener start routines for listeners on an amphora."""
        if loadbalancer.listeners:
            self.amphora_driver.start(loadbalancer, amphora)
            LOG.debug("Started the listeners on the vip")

    def revert(self, loadbalancer, *args, **kwargs):
        """Handle failed listeners starts."""

        LOG.warning("Reverting listeners starts.")
        for listener in loadbalancer.listeners:
            self.task_utils.mark_listener_prov_status_error(listener.id)


class AmphoraIndexListenersReload(BaseAmphoraTask):
    """Task to reload all listeners on an amphora."""

    def execute(self, loadbalancer, amphora_index, amphorae,
                timeout_dict=None):
        """Execute listener reload routines for listeners on an amphora."""
        if loadbalancer.listeners:
            try:
                self.amphora_driver.reload(
                    loadbalancer, amphorae[amphora_index], timeout_dict)
            except Exception as e:
                amphora_id = amphorae[amphora_index].id
                LOG.warning('Failed to reload listeners on amphora %s. '
                            'Skipping this amphora as it is failing to '
                            'reload due to: %s', amphora_id, str(e))
                self.amphora_repo.update(db_apis.get_session(), amphora_id,
                                         status=constants.ERROR)


class ListenerDelete(BaseAmphoraTask):
    """Task to delete the listener on the vip."""

    def execute(self, listener):
        """Execute listener delete routines for an amphora."""
        # TODO(rm_work): This is only relevant because of UDP listeners now.
        self.amphora_driver.delete(listener)
        LOG.debug("Deleted the listener on the vip")

    def revert(self, listener, *args, **kwargs):
        """Handle a failed listener delete."""

        LOG.warning("Reverting listener delete.")

        self.task_utils.mark_listener_prov_status_error(listener.id)


class AmphoraGetInfo(BaseAmphoraTask):
    """Task to get information on an amphora."""

    def execute(self, amphora):
        """Execute get_info routine for an amphora."""
        self.amphora_driver.get_info(amphora)


class AmphoraGetDiagnostics(BaseAmphoraTask):
    """Task to get diagnostics on the amphora and the loadbalancers."""

    def execute(self, amphora):
        """Execute get_diagnostic routine for an amphora."""
        self.amphora_driver.get_diagnostics(amphora)


class AmphoraFinalize(BaseAmphoraTask):
    """Task to finalize the amphora before any listeners are configured."""

    def execute(self, amphora):
        """Execute finalize_amphora routine."""
        self.amphora_driver.finalize_amphora(amphora)
        LOG.debug("Finalized the amphora.")

    def revert(self, result, amphora, *args, **kwargs):
        """Handle a failed amphora finalize."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning("Reverting amphora finalize.")
        self.task_utils.mark_amphora_status_error(amphora.id)


class AmphoraPostNetworkPlug(BaseAmphoraTask):
    """Task to notify the amphora post network plug."""

    def execute(self, amphora, ports):
        """Execute post_network_plug routine."""
        for port in ports:
            self.amphora_driver.post_network_plug(amphora, port)
            LOG.debug("post_network_plug called on compute instance "
                      "%(compute_id)s for port %(port_id)s",
                      {"compute_id": amphora.compute_id, "port_id": port.id})

    def revert(self, result, amphora, *args, **kwargs):
        """Handle a failed post network plug."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning("Reverting post network plug.")
        self.task_utils.mark_amphora_status_error(amphora.id)


class AmphoraePostNetworkPlug(BaseAmphoraTask):
    """Task to notify the amphorae post network plug."""

    def execute(self, loadbalancer, added_ports):
        """Execute post_network_plug routine."""
        amp_post_plug = AmphoraPostNetworkPlug()
        # We need to make sure we have the fresh list of amphora
        amphorae = self.amphora_repo.get_all(
            db_apis.get_session(), load_balancer_id=loadbalancer.id,
            status=constants.AMPHORA_ALLOCATED)[0]
        for amphora in amphorae:
            if amphora.id in added_ports:
                amp_post_plug.execute(amphora, added_ports[amphora.id])

    def revert(self, result, loadbalancer, added_ports, *args, **kwargs):
        """Handle a failed post network plug."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning("Reverting post network plug.")

        amphorae = self.amphora_repo.get_all(
            db_apis.get_session(), load_balancer_id=loadbalancer.id,
            status=constants.AMPHORA_ALLOCATED)[0]
        for amphora in amphorae:
            self.task_utils.mark_amphora_status_error(amphora.id)


class AmphoraPostVIPPlug(BaseAmphoraTask):
    """Task to notify the amphora post VIP plug."""

    def execute(self, amphora, loadbalancer, amphorae_network_config):
        """Execute post_vip_routine."""
        self.amphora_driver.post_vip_plug(
            amphora, loadbalancer, amphorae_network_config)
        LOG.debug("Notified amphora of vip plug")

    def revert(self, result, amphora, loadbalancer, *args, **kwargs):
        """Handle a failed amphora vip plug notification."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning("Reverting post vip plug.")
        self.task_utils.mark_amphora_status_error(amphora.id)
        self.task_utils.mark_loadbalancer_prov_status_error(loadbalancer.id)


class AmphoraePostVIPPlug(BaseAmphoraTask):
    """Task to notify the amphorae post VIP plug."""

    def execute(self, loadbalancer, amphorae_network_config):
        """Execute post_vip_plug across the amphorae."""
        amp_post_vip_plug = AmphoraPostVIPPlug()
        for amphora in loadbalancer.amphorae:
            amp_post_vip_plug.execute(amphora,
                                      loadbalancer,
                                      amphorae_network_config)

    def revert(self, result, loadbalancer, *args, **kwargs):
        """Handle a failed amphora vip plug notification."""
        if isinstance(result, failure.Failure):
            return
        LOG.warning("Reverting amphorae post vip plug.")
        self.task_utils.mark_loadbalancer_prov_status_error(loadbalancer.id)


class AmphoraCertUpload(BaseAmphoraTask):
    """Upload a certificate to the amphora."""

    def execute(self, amphora, server_pem):
        """Execute cert_update_amphora routine."""
        LOG.debug("Upload cert in amphora REST driver")
        key = utils.get_six_compatible_server_certs_key_passphrase()
        fer = fernet.Fernet(key)
        self.amphora_driver.upload_cert_amp(amphora, fer.decrypt(server_pem))


class AmphoraUpdateVRRPInterface(BaseAmphoraTask):
    """Task to get and update the VRRP interface device name from amphora."""

    def execute(self, amphora, timeout_dict=None):
        try:
            interface = self.amphora_driver.get_interface_from_ip(
                amphora, amphora.vrrp_ip, timeout_dict=timeout_dict)
        except Exception as e:
            # This can occur when an active/standby LB has no listener
            LOG.error('Failed to get amphora VRRP interface on amphora '
                      '%s. Skipping this amphora as it is failing due to: '
                      '%s', amphora.id, str(e))
            self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                     status=constants.ERROR)
            return None

        self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                 vrrp_interface=interface)
        return interface


class AmphoraIndexUpdateVRRPInterface(BaseAmphoraTask):
    """Task to get and update the VRRP interface device name from amphora."""

    def execute(self, amphora_index, amphorae, timeout_dict=None):
        amphora_id = amphorae[amphora_index].id
        try:
            interface = self.amphora_driver.get_interface_from_ip(
                amphorae[amphora_index], amphorae[amphora_index].vrrp_ip,
                timeout_dict=timeout_dict)
        except Exception as e:
            # This can occur when an active/standby LB has no listener
            LOG.error('Failed to get amphora VRRP interface on amphora '
                      '%s. Skipping this amphora as it is failing due to: '
                      '%s', amphora_id, str(e))
            self.amphora_repo.update(db_apis.get_session(), amphora_id,
                                     status=constants.ERROR)
            return None

        self.amphora_repo.update(db_apis.get_session(), amphora_id,
                                 vrrp_interface=interface)
        return interface


class AmphoraVRRPUpdate(BaseAmphoraTask):
    """Task to update the VRRP configuration of an amphora."""

    def execute(self, loadbalancer_id, amphorae_network_config, amphora,
                amp_vrrp_int, timeout_dict=None):
        """Execute update_vrrp_conf."""
        loadbalancer = self.loadbalancer_repo.get(db_apis.get_session(),
                                                  id=loadbalancer_id)
        # Note, we don't want this to cause a revert as it may be used
        # in a failover flow with both amps failing. Skip it and let
        # health manager fix it.
        amphora.vrrp_interface = amp_vrrp_int
        try:
            self.amphora_driver.update_vrrp_conf(
                loadbalancer, amphorae_network_config, amphora, timeout_dict)
        except Exception as e:
            LOG.error('Failed to update VRRP configuration amphora %s. '
                      'Skipping this amphora as it is failing to update due '
                      'to: %s', amphora.id, str(e))
            self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                     status=constants.ERROR)

        LOG.debug("Uploaded VRRP configuration of amphora %s.", amphora.id)


class AmphoraIndexVRRPUpdate(BaseAmphoraTask):
    """Task to update the VRRP configuration of an amphora."""

    def execute(self, loadbalancer_id, amphorae_network_config, amphora_index,
                amphorae, amp_vrrp_int, timeout_dict=None):
        """Execute update_vrrp_conf."""
        loadbalancer = self.loadbalancer_repo.get(db_apis.get_session(),
                                                  id=loadbalancer_id)
        # Note, we don't want this to cause a revert as it may be used
        # in a failover flow with both amps failing. Skip it and let
        # health manager fix it.
        amphora_id = amphorae[amphora_index].id
        amphorae[amphora_index].vrrp_interface = amp_vrrp_int
        try:
            self.amphora_driver.update_vrrp_conf(
                loadbalancer, amphorae_network_config, amphorae[amphora_index],
                timeout_dict)
        except Exception as e:
            LOG.error('Failed to update VRRP configuration amphora %s. '
                      'Skipping this amphora as it is failing to update due '
                      'to: %s', amphora_id, str(e))
            self.amphora_repo.update(db_apis.get_session(), amphora_id,
                                     status=constants.ERROR)
            return
        LOG.debug("Uploaded VRRP configuration of amphora %s.", amphora_id)


class AmphoraVRRPStop(BaseAmphoraTask):
    """Task to stop keepalived of all amphorae of a LB."""

    def execute(self, loadbalancer):
        self.amphora_driver.stop_vrrp_service(loadbalancer)
        LOG.debug("Stopped VRRP of loadbalancer %s amphorae",
                  loadbalancer.id)


class AmphoraVRRPStart(BaseAmphoraTask):
    """Task to start keepalived on an amphora.

    This will reload keepalived if it is already running.
    """

    def execute(self, amphora, timeout_dict=None):
        self.amphora_driver.start_vrrp_service(amphora, timeout_dict)
        LOG.debug("Started VRRP on amphora %s.", amphora.id)


class AmphoraIndexVRRPStart(BaseAmphoraTask):
    """Task to start keepalived on an amphora.

    This will reload keepalived if it is already running.
    """

    def execute(self, amphora_index, amphorae, timeout_dict=None):
        amphora_id = amphorae[amphora_index].id
        try:
            self.amphora_driver.start_vrrp_service(amphorae[amphora_index],
                                                   timeout_dict)
        except Exception as e:
            LOG.error('Failed to start VRRP on amphora %s. '
                      'Skipping this amphora as it is failing to start due '
                      'to: %s', amphora_id, str(e))
            self.amphora_repo.update(db_apis.get_session(), amphora_id,
                                     status=constants.ERROR)
            return
        LOG.debug("Started VRRP on amphora %s.", amphorae[amphora_index].id)


class AmphoraComputeConnectivityWait(BaseAmphoraTask):
    """Task to wait for the compute instance to be up."""

    def execute(self, amphora):
        """Execute get_info routine for an amphora until it responds."""
        try:
            amp_info = self.amphora_driver.get_info(amphora)
            LOG.debug('Successfuly connected to amphora %s: %s',
                      amphora.id, amp_info)
        except driver_except.TimeOutException:
            LOG.error("Amphora compute instance failed to become reachable. "
                      "This either means the compute driver failed to fully "
                      "boot the instance inside the timeout interval or the "
                      "instance is not reachable via the lb-mgmt-net.")
            self.amphora_repo.update(db_apis.get_session(), amphora.id,
                                     status=constants.ERROR)
            raise


class AmphoraConfigUpdate(BaseAmphoraTask):
    """Task to push a new amphora agent configuration to the amphroa."""

    def execute(self, amphora, flavor):
        # Extract any flavor based settings
        if flavor:
            topology = flavor.get(constants.LOADBALANCER_TOPOLOGY,
                                  CONF.controller_worker.loadbalancer_topology)
        else:
            topology = CONF.controller_worker.loadbalancer_topology

        # Build the amphora agent config
        agent_cfg_tmpl = agent_jinja_cfg.AgentJinjaTemplater()
        agent_config = agent_cfg_tmpl.build_agent_config(amphora.id, topology)

        # Push the new configuration to the amphroa
        try:
            self.amphora_driver.update_amphora_agent_config(amphora,
                                                            agent_config)
        except driver_except.AmpDriverNotImplementedError:
            LOG.error('Amphora {} does not support agent configuration '
                      'update. Please update the amphora image for this '
                      'amphora. Skipping.'.format(amphora.id))
