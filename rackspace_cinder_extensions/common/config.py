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

from oslo_config import cfg


CONF = cfg.CONF

global_opts = [
    cfg.StrOpt('rsapi_volume_ext_list',
               default=[],
               help='Specify list of extensions to load when using osapi_'
                    'volume_extension option with rackspace_cinder_extensions.'
                    'select_extensions'),
]

CONF.register_opts(global_opts)
