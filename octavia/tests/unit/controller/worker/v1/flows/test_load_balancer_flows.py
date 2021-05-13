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

import mock
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
from oslo_utils import uuidutils
from taskflow.patterns import linear_flow as flow

from octavia.common import constants
from octavia.common import exceptions
from octavia.controller.worker.v1.flows import load_balancer_flows
import octavia.tests.unit.base as base


# NOTE: We patch the get_network_driver for all the calls so we don't
# inadvertently make real calls.
@mock.patch('octavia.common.utils.get_network_driver')
class TestLoadBalancerFlows(base.TestCase):

    def setUp(self):
        super(TestLoadBalancerFlows, self).setUp()
        self.conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        self.conf.config(
            group="controller_worker",
            amphora_driver='amphora_haproxy_rest_driver')
        self.conf.config(group="nova", enable_anti_affinity=False)
        self.LBFlow = load_balancer_flows.LoadBalancerFlows()

    def test_get_create_load_balancer_flow(self, mock_get_net_driver):
        amp_flow = self.LBFlow.get_create_load_balancer_flow(
            constants.TOPOLOGY_SINGLE)
        self.assertIsInstance(amp_flow, flow.Flow)
        self.assertIn(constants.LOADBALANCER_ID, amp_flow.requires)
        self.assertIn(constants.AMPHORA, amp_flow.provides)
        self.assertIn(constants.AMPHORA_ID, amp_flow.provides)
        self.assertIn(constants.COMPUTE_ID, amp_flow.provides)
        self.assertIn(constants.COMPUTE_OBJ, amp_flow.provides)

    def test_get_create_active_standby_load_balancer_flow(
            self, mock_get_net_driver):
        amp_flow = self.LBFlow.get_create_load_balancer_flow(
            constants.TOPOLOGY_ACTIVE_STANDBY)
        self.assertIsInstance(amp_flow, flow.Flow)
        self.assertIn(constants.LOADBALANCER_ID, amp_flow.requires)
        self.assertIn(constants.AMPHORA, amp_flow.provides)
        self.assertIn(constants.AMPHORA_ID, amp_flow.provides)
        self.assertIn(constants.COMPUTE_ID, amp_flow.provides)
        self.assertIn(constants.COMPUTE_OBJ, amp_flow.provides)

    def test_get_create_anti_affinity_active_standby_load_balancer_flow(
            self, mock_get_net_driver):
        self.conf.config(group="nova", enable_anti_affinity=True)

        self._LBFlow = load_balancer_flows.LoadBalancerFlows()
        amp_flow = self._LBFlow.get_create_load_balancer_flow(
            constants.TOPOLOGY_ACTIVE_STANDBY)
        self.assertIsInstance(amp_flow, flow.Flow)
        self.assertIn(constants.LOADBALANCER_ID, amp_flow.requires)
        self.assertIn(constants.SERVER_GROUP_ID, amp_flow.provides)
        self.assertIn(constants.AMPHORA, amp_flow.provides)
        self.assertIn(constants.AMPHORA_ID, amp_flow.provides)
        self.assertIn(constants.COMPUTE_ID, amp_flow.provides)
        self.assertIn(constants.COMPUTE_OBJ, amp_flow.provides)
        self.conf.config(group="nova", enable_anti_affinity=False)

    def test_get_create_bogus_topology_load_balancer_flow(
            self, mock_get_net_driver):
        self.assertRaises(exceptions.InvalidTopology,
                          self.LBFlow.get_create_load_balancer_flow,
                          'BOGUS')

    def test_get_delete_load_balancer_flow(self, mock_get_net_driver):
        lb_mock = mock.Mock()
        listener_mock = mock.Mock()
        listener_mock.id = '123'
        lb_mock.listeners = [listener_mock]

        lb_flow, store = self.LBFlow.get_delete_load_balancer_flow(lb_mock)

        self.assertIsInstance(lb_flow, flow.Flow)

        self.assertIn(constants.LOADBALANCER, lb_flow.requires)
        self.assertIn(constants.SERVER_GROUP_ID, lb_flow.requires)

        self.assertEqual(0, len(lb_flow.provides))
        self.assertEqual(2, len(lb_flow.requires))

    def test_get_delete_load_balancer_flow_cascade(self, mock_get_net_driver):
        lb_mock = mock.Mock()
        listener_mock = mock.Mock()
        listener_mock.id = '123'
        lb_mock.listeners = [listener_mock]
        pool_mock = mock.Mock()
        pool_mock.id = '345'
        lb_mock.pools = [pool_mock]
        l7_mock = mock.Mock()
        l7_mock.id = '678'
        listener_mock.l7policies = [l7_mock]

        lb_flow, store = self.LBFlow.get_cascade_delete_load_balancer_flow(
            lb_mock)

        self.assertIsInstance(lb_flow, flow.Flow)
        self.assertEqual({'listener_123': listener_mock,
                          'pool345': pool_mock}, store)

        self.assertIn(constants.LOADBALANCER, lb_flow.requires)

        self.assertEqual(1, len(lb_flow.provides))
        self.assertEqual(4, len(lb_flow.requires))

    def test_get_update_load_balancer_flow(self, mock_get_net_driver):

        lb_flow = self.LBFlow.get_update_load_balancer_flow()

        self.assertIsInstance(lb_flow, flow.Flow)

        self.assertIn(constants.LOADBALANCER, lb_flow.requires)
        self.assertIn(constants.UPDATE_DICT, lb_flow.requires)

        self.assertEqual(0, len(lb_flow.provides))
        self.assertEqual(2, len(lb_flow.requires))

    def test_get_post_lb_amp_association_flow(self, mock_get_net_driver):
        amp_flow = self.LBFlow.get_post_lb_amp_association_flow(
            '123', constants.TOPOLOGY_SINGLE)

        self.assertIsInstance(amp_flow, flow.Flow)

        self.assertIn(constants.LOADBALANCER_ID, amp_flow.requires)
        self.assertIn(constants.UPDATE_DICT, amp_flow.requires)
        self.assertIn(constants.LOADBALANCER, amp_flow.provides)

        self.assertEqual(1, len(amp_flow.provides))
        self.assertEqual(2, len(amp_flow.requires))

        # Test Active/Standby path
        amp_flow = self.LBFlow.get_post_lb_amp_association_flow(
            '123', constants.TOPOLOGY_ACTIVE_STANDBY)

        self.assertIsInstance(amp_flow, flow.Flow)

        self.assertIn(constants.LOADBALANCER_ID, amp_flow.requires)
        self.assertIn(constants.UPDATE_DICT, amp_flow.requires)
        self.assertIn(constants.LOADBALANCER, amp_flow.provides)

        self.assertEqual(4, len(amp_flow.provides))
        self.assertEqual(2, len(amp_flow.requires))

        # Test mark_active=False
        amp_flow = self.LBFlow.get_post_lb_amp_association_flow(
            '123', constants.TOPOLOGY_ACTIVE_STANDBY)

        self.assertIsInstance(amp_flow, flow.Flow)

        self.assertIn(constants.LOADBALANCER_ID, amp_flow.requires)
        self.assertIn(constants.UPDATE_DICT, amp_flow.requires)
        self.assertIn(constants.LOADBALANCER, amp_flow.provides)

        self.assertEqual(4, len(amp_flow.provides))
        self.assertEqual(2, len(amp_flow.requires))

    def test_get_create_load_balancer_flows_single_listeners(
            self, mock_get_net_driver):
        create_flow = (
            self.LBFlow.get_create_load_balancer_flow(
                constants.TOPOLOGY_SINGLE, True
            )
        )
        self.assertIsInstance(create_flow, flow.Flow)
        self.assertIn(constants.LOADBALANCER_ID, create_flow.requires)
        self.assertIn(constants.UPDATE_DICT, create_flow.requires)

        self.assertIn(constants.LISTENERS, create_flow.provides)
        self.assertIn(constants.AMPHORA, create_flow.provides)
        self.assertIn(constants.AMPHORA_ID, create_flow.provides)
        self.assertIn(constants.COMPUTE_ID, create_flow.provides)
        self.assertIn(constants.COMPUTE_OBJ, create_flow.provides)
        self.assertIn(constants.LOADBALANCER, create_flow.provides)
        self.assertIn(constants.DELTAS, create_flow.provides)
        self.assertIn(constants.ADDED_PORTS, create_flow.provides)
        self.assertIn(constants.VIP, create_flow.provides)
        self.assertIn(constants.AMP_DATA, create_flow.provides)
        self.assertIn(constants.AMPHORA_NETWORK_CONFIG, create_flow.provides)

        self.assertEqual(5, len(create_flow.requires))
        self.assertEqual(13, len(create_flow.provides),
                         create_flow.provides)

    def test_get_create_load_balancer_flows_active_standby_listeners(
            self, mock_get_net_driver):
        create_flow = (
            self.LBFlow.get_create_load_balancer_flow(
                constants.TOPOLOGY_ACTIVE_STANDBY, True
            )
        )
        self.assertIsInstance(create_flow, flow.Flow)
        self.assertIn(constants.LOADBALANCER_ID, create_flow.requires)
        self.assertIn(constants.UPDATE_DICT, create_flow.requires)

        self.assertIn(constants.LISTENERS, create_flow.provides)
        self.assertIn(constants.AMPHORA, create_flow.provides)
        self.assertIn(constants.AMPHORA_ID, create_flow.provides)
        self.assertIn(constants.COMPUTE_ID, create_flow.provides)
        self.assertIn(constants.COMPUTE_OBJ, create_flow.provides)
        self.assertIn(constants.LOADBALANCER, create_flow.provides)
        self.assertIn(constants.DELTAS, create_flow.provides)
        self.assertIn(constants.ADDED_PORTS, create_flow.provides)
        self.assertIn(constants.VIP, create_flow.provides)
        self.assertIn(constants.AMP_DATA, create_flow.provides)
        self.assertIn(constants.AMPHORAE_NETWORK_CONFIG,
                      create_flow.provides)

        self.assertEqual(5, len(create_flow.requires))
        self.assertEqual(16, len(create_flow.provides),
                         create_flow.provides)

    def _test_get_failover_LB_flow_single(self, amphorae):
        lb_mock = mock.MagicMock()
        lb_mock.id = uuidutils.generate_uuid()
        lb_mock.topology = constants.TOPOLOGY_SINGLE

        failover_flow = self.LBFlow.get_failover_LB_flow(amphorae, lb_mock)

        self.assertIsInstance(failover_flow, flow.Flow)

        self.assertIn(constants.BUILD_TYPE_PRIORITY, failover_flow.requires)
        self.assertIn(constants.FLAVOR, failover_flow.requires)
        self.assertIn(constants.LOADBALANCER, failover_flow.requires)
        self.assertIn(constants.LOADBALANCER_ID, failover_flow.requires)

        self.assertIn(constants.ADDED_PORTS, failover_flow.provides)
        self.assertIn(constants.AMPHORA, failover_flow.provides)
        self.assertIn(constants.AMPHORA_ID, failover_flow.provides)
        self.assertIn(constants.AMPHORAE_NETWORK_CONFIG,
                      failover_flow.provides)
        self.assertIn(constants.BASE_PORT, failover_flow.provides)
        self.assertIn(constants.COMPUTE_ID, failover_flow.provides)
        self.assertIn(constants.COMPUTE_OBJ, failover_flow.provides)
        self.assertIn(constants.DELTA, failover_flow.provides)
        self.assertIn(constants.LOADBALANCER, failover_flow.provides)
        self.assertIn(constants.SERVER_PEM, failover_flow.provides)
        self.assertIn(constants.VIP, failover_flow.provides)
        self.assertIn(constants.VIP_SG_ID, failover_flow.provides)

        self.assertEqual(5, len(failover_flow.requires),
                         failover_flow.requires)
        self.assertEqual(12, len(failover_flow.provides),
                         failover_flow.provides)

    def test_get_failover_LB_flow_no_amps_single(self, mock_get_net_driver):
        self._test_get_failover_LB_flow_single([])

    def test_get_failover_LB_flow_one_amp_single(self, mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = constants.ROLE_STANDALONE
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = None
        amphora_mock.vrrp_ip = None

        self._test_get_failover_LB_flow_single([amphora_mock])

    def test_get_failover_LB_flow_one_spare_amp_single(self,
                                                       mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = None
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = None
        amphora_mock.vrrp_ip = None

        self._test_get_failover_LB_flow_single([amphora_mock])

    def test_get_failover_LB_flow_one_bogus_amp_single(self,
                                                       mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = 'bogus'
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = None
        amphora_mock.vrrp_ip = None

        self._test_get_failover_LB_flow_single([amphora_mock])

    def test_get_failover_LB_flow_two_amp_single(self, mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora2_mock = mock.MagicMock()
        amphora2_mock.role = constants.ROLE_STANDALONE
        amphora2_mock.lb_network_id = uuidutils.generate_uuid()
        amphora2_mock.compute_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_port_id = None
        amphora2_mock.vrrp_ip = None

        self._test_get_failover_LB_flow_single([amphora_mock, amphora2_mock])

    def _test_get_failover_LB_flow_no_amps_act_stdby(self, amphorae):
        lb_mock = mock.MagicMock()
        lb_mock.id = uuidutils.generate_uuid()
        lb_mock.topology = constants.TOPOLOGY_ACTIVE_STANDBY

        failover_flow = self.LBFlow.get_failover_LB_flow(amphorae, lb_mock)

        self.assertIsInstance(failover_flow, flow.Flow)

        self.assertIn(constants.BUILD_TYPE_PRIORITY, failover_flow.requires)
        self.assertIn(constants.FLAVOR, failover_flow.requires)
        self.assertIn(constants.LOADBALANCER, failover_flow.requires)
        self.assertIn(constants.LOADBALANCER_ID, failover_flow.requires)

        self.assertIn(constants.ADDED_PORTS, failover_flow.provides)
        self.assertIn(constants.AMP_VRRP_INT, failover_flow.provides)
        self.assertIn(constants.AMPHORA, failover_flow.provides)
        self.assertIn(constants.AMPHORA_ID, failover_flow.provides)
        self.assertIn(constants.AMPHORAE, failover_flow.provides)
        self.assertIn(constants.AMPHORAE_NETWORK_CONFIG,
                      failover_flow.provides)
        self.assertIn(constants.BASE_PORT, failover_flow.provides)
        self.assertIn(constants.COMPUTE_ID, failover_flow.provides)
        self.assertIn(constants.COMPUTE_OBJ, failover_flow.provides)
        self.assertIn(constants.DELTA, failover_flow.provides)
        self.assertIn(constants.FIRST_AMP_NETWORK_CONFIGS,
                      failover_flow.provides)
        self.assertIn(constants.FIRST_AMP_VRRP_INTERFACE,
                      failover_flow.provides)
        self.assertIn(constants.LOADBALANCER, failover_flow.provides)
        self.assertIn(constants.SERVER_PEM, failover_flow.provides)
        self.assertIn(constants.VIP, failover_flow.provides)
        self.assertIn(constants.VIP_SG_ID, failover_flow.provides)

        self.assertEqual(5, len(failover_flow.requires),
                         failover_flow.requires)
        self.assertEqual(16, len(failover_flow.provides),
                         failover_flow.provides)

    def test_get_failover_LB_flow_no_amps_act_stdby(self, mock_get_net_driver):
        self._test_get_failover_LB_flow_no_amps_act_stdby([])

    def test_get_failover_LB_flow_one_amps_act_stdby(self, amphorae):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = constants.ROLE_MASTER
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = None
        amphora_mock.vrrp_ip = None

        self._test_get_failover_LB_flow_no_amps_act_stdby([amphora_mock])

    def test_get_failover_LB_flow_two_amps_act_stdby(self,
                                                     mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = constants.ROLE_MASTER
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_ip = '192.0.2.46'
        amphora2_mock = mock.MagicMock()
        amphora2_mock.role = constants.ROLE_BACKUP
        amphora2_mock.lb_network_id = uuidutils.generate_uuid()
        amphora2_mock.compute_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_ip = '2001:db8::46'

        self._test_get_failover_LB_flow_no_amps_act_stdby([amphora_mock,
                                                           amphora2_mock])

    def test_get_failover_LB_flow_three_amps_act_stdby(self,
                                                       mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = constants.ROLE_MASTER
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_ip = '192.0.2.46'
        amphora2_mock = mock.MagicMock()
        amphora2_mock.role = constants.ROLE_BACKUP
        amphora2_mock.lb_network_id = uuidutils.generate_uuid()
        amphora2_mock.compute_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_ip = '2001:db8::46'
        amphora3_mock = mock.MagicMock()
        amphora3_mock.vrrp_ip = None

        self._test_get_failover_LB_flow_no_amps_act_stdby(
            [amphora_mock, amphora2_mock, amphora3_mock])

    def test_get_failover_LB_flow_two_amps_bogus_act_stdby(
            self, mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = 'bogus'
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_ip = '192.0.2.46'
        amphora2_mock = mock.MagicMock()
        amphora2_mock.role = constants.ROLE_MASTER
        amphora2_mock.lb_network_id = uuidutils.generate_uuid()
        amphora2_mock.compute_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_ip = '2001:db8::46'

        self._test_get_failover_LB_flow_no_amps_act_stdby([amphora_mock,
                                                           amphora2_mock])

    def test_get_failover_LB_flow_two_amps_spare_act_stdby(
            self, mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = None
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_ip = '192.0.2.46'
        amphora2_mock = mock.MagicMock()
        amphora2_mock.role = constants.ROLE_MASTER
        amphora2_mock.lb_network_id = uuidutils.generate_uuid()
        amphora2_mock.compute_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_ip = '2001:db8::46'

        self._test_get_failover_LB_flow_no_amps_act_stdby([amphora_mock,
                                                           amphora2_mock])

    def test_get_failover_LB_flow_two_amps_standalone_act_stdby(
            self, mock_get_net_driver):
        amphora_mock = mock.MagicMock()
        amphora_mock.role = constants.ROLE_STANDALONE
        amphora_mock.lb_network_id = uuidutils.generate_uuid()
        amphora_mock.compute_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora_mock.vrrp_ip = '192.0.2.46'
        amphora2_mock = mock.MagicMock()
        amphora2_mock.role = constants.ROLE_MASTER
        amphora2_mock.lb_network_id = uuidutils.generate_uuid()
        amphora2_mock.compute_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_port_id = uuidutils.generate_uuid()
        amphora2_mock.vrrp_ip = '2001:db8::46'

        self._test_get_failover_LB_flow_no_amps_act_stdby([amphora_mock,
                                                           amphora2_mock])
