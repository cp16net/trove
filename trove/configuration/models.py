import eventlet
from eventlet import greenthread
import netaddr

from trove.common import cfg
from trove.db import models as dbmodels
from trove.openstack.common import log as logging
from trove.taskmanager import api as task_api


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Configurations(object):
    _data_fields = ['id', 'name', 'description']

    @staticmethod
    def load(context):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument is not defined.")

        """ TODO(jrodom): Pagination support required! """
        db_info = DBConfiguration.find_all(tenant_id=context.tenant)

        if db_info is None:
            LOG.debug("No configuration found for tenant % s" % context.tenant)

        return db_info


class Configuration(object):

    DEFAULT_LIMIT = CONF.instances_page_size

    @property
    def instances(self):
        return self.instances

    @property
    def items(self):
        return self.items

    @staticmethod
    def create(name, description, tenant_id, values):
        configurationGroup = DBConfiguration.create(name=name,
                                                    description=description,
                                                    tenant_id=tenant_id,
                                                    items=values)
        return configurationGroup

    @staticmethod
    def delete(id):
        DBConfiguration.delete(id=id)

    @staticmethod
    def load(context, id):
        config_infos = DBConfiguration.find_by(id=id, tenant_id=context.tenant)
        # TODO(cp16net): Need to add pagination OR make this a separate call
        # limit = int(context.limit or Configuration.DEFAULT_LIMIT)
        # if limit > Configuration.DEFAULT_LIMIT:
        #     limit = Configuration.DEFAULT_LIMIT
        # data_view = DBConfiguration.find_by_pagination('dbconfiguration',
        #                                                config_infos,
        #                                                "foo",
        #                                                limit=limit,
        #                                                marker=context.marker)
        # next_marker = data_view.next_page_marker
        # ret = data_view.collection

        # return ret, next_marker
        return config_infos

    @staticmethod
    def save(context, configuration):
        DBConfiguration.save(configuration)

        for instance in configuration.instances:

            overrides = {}
            for i in configuration.items:
                overrides[i.configuration_key] = i.configuration_value

            task_api.API(context).update_overrides(instance.id, overrides)


class DBConfiguration(dbmodels.DatabaseModelBase):
    _data_fields = ['name', 'description', 'tenant_id', 'items', 'instances']


class ConfigurationItem(dbmodels.DatabaseModelBase):
    _data_fields = ['configuration_key', 'configuration_value']

    def __hash__(self):
        return self.configuration_key.__hash__()


def persisted_models():
    return {
        'configuration': DBConfiguration,
        'configuration_item': ConfigurationItem
    }
