import os

from cinder import test


class TestCase(test.TestCase):

    def setUp(self):
        super(TestCase, self).setUp()
        self.flags(
            osapi_volume_extension=[
                'rackspace_cinder_extensions.rax_extensions'])

        self.override_config('policy_file',
                             os.path.join(
                                 os.path.abspath(
                                     os.path.join(
                                         os.path.dirname(__file__),
                                         '..',
                                     )
                                 ),
                                 'rackspace_cinder_extensions/tests/unit/policy.json'),
                             group='oslo_policy')
