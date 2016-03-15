#  Copyright 2013-2016 Rackspace US, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

try:
    from oslo_config import cfg
except ImportError:
    from oslo.config import cfg
try:
    from oslo_log import log as logging
except ImportError:
    from cinder.openstack.common import log as logging

from cinder.api import extensions
import os

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

def rax_extensions(ext_mgr):
    """ Load any extensions where this package resides """

    # Walk through all the modules in our directory...
    our_dir = __path__[0]
    for dirpath, dirnames, filenames in os.walk(our_dir):
        # Compute the relative package name from the dirpath
        relpath = os.path.relpath(dirpath, our_dir)
        if relpath == '.':
            relpkg = ''
        else:
            relpkg = '.%s' % '.'.join(relpath.split(os.sep))

        # Now, consider each file in turn, only considering .py files
        for fname in filenames:
            root, ext = os.path.splitext(fname)
            # Skip test directory
            if dirpath.endswith('test'):
                continue
            # Skip __init__ and anything that's not .py
            if ext != '.py' or root == '__init__':
                continue

            # Try loading it
            classname = "%s%s" % (root[0].upper(), root[1:])
            classpath = ("%s%s.%s.%s" %
                         (__package__, relpkg, root, classname))

            try:
                ext_mgr.load_extension(classpath)
            except Exception as exc:
                LOG.warn(_('Failed to load extension %(classpath)s: '
                              '%(exc)s'),
                            {'classpath': classpath, 'exc': exc})
