# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
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

from trove.common import exception
from trove.common import wsgi
from trove.extensions.scheduled_tasks import models
from trove.extensions.scheduled_tasks import views
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)


class ScheduledTasksController(wsgi.Controller):
    """Controller for Scheduled Tasks functionality"""

    def index(self, req, tenant_id, instance_id, detailed=False):
        """Return all task types."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing a task types for tenant '%s'") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        task_types = models.ScheduledTask.list(context)
        LOG.debug("task_types: %s" % task_types)
        return wsgi.Result(views.ScheduledTaskViews(task_types).data(), 200)

    def show(self, req, tenant_id, instance_id):
        """Return a task type."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a task type for tenant '%s'") % tenant_id)
        LOG.info(_("instance_id : '%s'\n\n") % instance_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        task_type = models.ScheduledTask.get_by_id(context, instance_id)
        return wsgi.Result(views.ScheduledTaskView(task_type).data(), 200)

    def create(self, req, body, tenant_id, instance_id):
        LOG.debug("Creating a Scheduled Task for tenant '%s'" % tenant_id)

        context = req.environ[wsgi.CONTEXT_KEY]
        self._validate_create_body(body)

        scheduled_task = models.ScheduledTask.create_scheduled_task(
            context,
            instance_id,
            body['scheduled_task']['name'],
            body['scheduled_task']['description'],
            body['scheduled_task']['type'])
        LOG.debug("scheduled_task: %s" % scheduled_task.__dict__)
        resultView = views.ScheduledTaskView(scheduled_task).data()
        return wsgi.Result(resultView, 201)

    def _validate_create_body(self, body):
        try:
            body['scheduled_task']
            body['scheduled_task']['name']
            body['scheduled_task']['description']
            body['scheduled_task']['type']
        except KeyError as e:
            LOG.error(_("Creating a Scheduled Task Required field(s) "
                        "- %s") % e)
            raise exception.ScheduledTaskCreationError(
                "Required element/key - %s was not specified" % e)


