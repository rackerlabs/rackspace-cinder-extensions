import os

from cinder import test


class TestCase(test.TestCase):

    def setUp(self):
        super(TestCase, self).setUp()
        self.flags(
            osapi_volume_extension=[
                'rackspace_cinder_extensions.rax_extensions'])

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
