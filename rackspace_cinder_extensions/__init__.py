
from oslo.config import cfg
from cinder.api import extensions
from cinder.openstack.common import log as logging
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
