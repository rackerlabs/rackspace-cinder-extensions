#  Copyright 2013-2016 Rackspace US, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License. You may obtain
#  a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#  WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#  License for the specific language governing permissions and limitations
#  under the License.

import os

from cinder import test


class TestCase(test.TestCase):

    def setUp(self):
        super(TestCase, self).setUp()
        self.flags(
            osapi_volume_extension=[
                'rackspace_cinder_extensions.api.contrib.standard_extensions'])

        policy = 'rackspace_cinder_extensions/tests/unit/policy.json'
        self.override_config('policy_file',
                             os.path.join(
                                 os.path.abspath(
                                     os.path.join(
                                         os.path.dirname(__file__),
                                         '..',
                                     )
                                 ),
                                 policy),
                             group='oslo_policy')
