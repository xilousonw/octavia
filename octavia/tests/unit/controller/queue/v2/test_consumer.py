# Copyright 2014 Rackspace
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

import mock
from oslo_config import cfg
from oslo_config import fixture as oslo_fixture
import oslo_messaging as messaging

from octavia.common import constants
from octavia.controller.queue.v2 import consumer
from octavia.controller.queue.v2 import endpoints
from octavia.tests.unit import base


class TestConsumer(base.TestRpc):

    def setUp(self):
        super(TestConsumer, self).setUp()
        conf = self.useFixture(oslo_fixture.Config(cfg.CONF))
        conf.config(host='test-hostname')
        self.conf = conf.conf

    @mock.patch.object(messaging, 'Target')
    @mock.patch.object(endpoints, 'Endpoints')
    @mock.patch.object(messaging, 'get_rpc_server')
    def test_consumer_run(self, mock_rpc_server, mock_endpoint, mock_target):
        mock_rpc_server_rv = mock.Mock()
        mock_rpc_server.return_value = mock_rpc_server_rv
        mock_endpoint_rv = mock.Mock()
        mock_endpoint.return_value = mock_endpoint_rv
        mock_target_rv = mock.Mock()
        mock_target.return_value = mock_target_rv

        consumer.ConsumerService(1, self.conf).run()

        mock_target.assert_called_once_with(topic=constants.TOPIC_AMPHORA_V2,
                                            server='test-hostname',
                                            fanout=False)
        mock_endpoint.assert_called_once_with()

    @mock.patch.object(messaging, 'get_rpc_server')
    def test_consumer_terminate(self, mock_rpc_server):
        mock_rpc_server_rv = mock.Mock()
        mock_rpc_server.return_value = mock_rpc_server_rv

        cons = consumer.ConsumerService(1, self.conf)
        cons.run()
        cons.terminate()
        mock_rpc_server_rv.stop.assert_called_once_with()
        mock_rpc_server_rv.wait.assert_called_once_with()
