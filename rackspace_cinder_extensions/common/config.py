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
