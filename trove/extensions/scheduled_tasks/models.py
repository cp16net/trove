# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
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
#

"""
Model classes for Scheduled Tasks on instances.
"""
from trove.common import cfg
from trove.common import exception
from trove.db.models import DatabaseModelBase
from trove.openstack.common import log as logging

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ScheduledTask(object):

    @classmethod
    def create_scheduled_task(cls, context, instance_id, name, description,
                              task_type):
        try:
            db_info = ScheduledTaskDBModel.create(name=name,
                                                  description=description,
                                                  tenant_id=context.tenant,
                                                  instance_id=instance_id,
                                                  task_type=task_type,
                                                  enabled=True)
        except exception.InvalidModelError as ex:
                LOG.exception("Unable to create Scheuduled Task record:")
                raise exception.ScheduledTaskCreationError(str(ex))

        return db_info

    @classmethod
    def get_by_id(cls, context, scheduled_task_id, deleted=False):
        """
        get the scheduled task for that id
        :param cls:
        :param scheduled_task_id: Id of the scheduled task to return
        :param deleted: Return deleted scheduled task
        :return:
        """
        try:
            db_info = ScheduledTaskDBModel.find_by(context=context,
                                                   id=scheduled_task_id,
                                                   deleted=deleted)
            return db_info
        except exception.NotFound:
            raise exception.NotFound(uuid=scheduled_task_id)

    @classmethod
    def list(cls, context):
        """
        list all scheduled tasks belong to given tenant
        :param cls:
        :param context: tenant_id included
        :return:
        """
        db_info = ScheduledTaskDBModel.find_all(tenant_id=context.tenant,
                                                deleted=False)
        return db_info

    @classmethod
    def list_for_instance(cls, context, instance_id):
        """
        list all scheduled tasks associated with given instance
        :param cls:
        :param instance_id:
        :return:
        """
        db_info = ScheduledTaskDBModel.find_all(tenant_id=context.tenant,
                                                instance_id=instance_id,
                                                deleted=False)
        return db_info


def persisted_models():
    return {'scheduled_tasks': ScheduledTaskDBModel}


class ScheduledTaskDBModel(DatabaseModelBase):
    _data_fields = ['id', 'name', 'description', 'tenant_id', 'instance_id',
                    'task_type', 'enabled',
                    'created', 'updated', 'deleted', 'deleted_at']
                    # 'frequency', 'time_window', 'retention_period',
