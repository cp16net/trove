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

from trove.openstack.common import log as logging

from trove.common import extensions
from trove.common import wsgi
from trove.common import cfg
from trove.extensions.scheduled_tasks import service


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


# The Extensions module from openstack common expects the classname of the
# extension to be loaded to be the exact same as the filename, except with
# a capital first letter. That's the reason this class has such a funky name.
class Scheduled_task(extensions.ExtensionsDescriptor):

    def get_name(self):
        return "ScheduledTask"

    def get_description(self):
        return "Scheduled Task related operations."

    def get_alias(self):
        return "ScheduledTask"

    def get_namespace(self):
        return "http://TBD"

    def get_updated(self):
        return "2013-08-27T17:41:00-06:00"

    def get_resources(self):
        resources = []
        serializer = wsgi.TroveResponseSerializer(
            body_serializers={'application/xml':
                              wsgi.TroveXMLDictSerializer()})

        collection_url = '{tenant_id}/instances'
        resource = extensions.ResourceExtension(
            'scheduledtasks',
            service.ScheduledTasksController(),
            parent={'member_name': 'instance',
                    'collection_name': collection_url},
            deserializer=wsgi.TroveRequestDeserializer(),
            serializer=serializer)
        resources.append(resource)

        return resources
