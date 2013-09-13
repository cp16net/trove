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

import webob.exc

from trove.common import cfg
from trove.common import exception
from trove.common import pagination
from trove.common import utils
from trove.common import wsgi
from trove.common.exception import ModelNotFoundError
from trove.configuration.models import Configuration
from trove.extensions.mysql.common import populate_validated_databases
from trove.extensions.mysql.common import populate_users
from trove.instance import models, views
from trove.backup.models import Backup as backup_model
from trove.backup import views as backup_views
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
import trove.common.apischema as apischema


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class InstanceController(wsgi.Controller):
    """Controller for instance functionality"""
    schemas = apischema.instance.copy()
    if not CONF.trove_volume_support:
        # see instance.models.create for further validation around this
        LOG.info("Removing volume attributes from schema")
        schemas['create']['properties']['instance']['required'].pop()

    @classmethod
    def get_action_schema(cls, body, action_schema):
        action_type = body.keys()[0]
        action_schema = action_schema.get(action_type, {})
        if action_type == 'resize':
            # volume or flavorRef
            resize_action = body[action_type].keys()[0]
            action_schema = action_schema.get(resize_action, {})
        return action_schema

    @classmethod
    def get_schema(cls, action, body):
        action_schema = super(InstanceController, cls).get_schema(action, body)
        if action == 'action':
            # resize or restart
            action_schema = cls.get_action_schema(body, action_schema)
        return action_schema

    def action(self, req, body, tenant_id, id):
        """
        Handles requests that modify existing instances in some manner. Actions
        could include 'resize', 'restart', 'reset_password'
        :param req: http request object
        :param body: deserialized body of the request as a dict
        :param tenant_id: the tenant id for whom owns the instance
        :param id: ???
        """
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Comitting an ACTION again instance %s for tenant '%s'"
                 % (id, tenant_id))
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        _actions = {
            'restart': self._action_restart,
            'resize': self._action_resize,
            'reset_password': self._action_reset_password
        }
        selected_action = None
        for key in body:
            if key in _actions:
                selected_action = _actions[key]
        return selected_action(instance, body)

    def _action_restart(self, instance, body):
        instance.restart()
        return wsgi.Result(None, 202)

    def _action_resize(self, instance, body):
        """
        Handles 2 cases
        1. resize volume
            body only contains {volume: {size: x}}
        2. resize instance
            body only contains {flavorRef: http.../2}

        If the body has both we will throw back an error.
        """
        options = {
            'volume': self._action_resize_volume,
            'flavorRef': self._action_resize_flavor
        }
        selected_option = None
        args = None
        for key in options:
            if key in body['resize']:
                selected_option = options[key]
                args = body['resize'][key]
                break
        return selected_option(instance, args)

    def _action_resize_volume(self, instance, volume):
        instance.resize_volume(volume['size'])
        return wsgi.Result(None, 202)

    def _action_resize_flavor(self, instance, flavorRef):
        new_flavor_id = utils.get_id_from_href(flavorRef)
        instance.resize_flavor(new_flavor_id)
        return wsgi.Result(None, 202)

    def _action_reset_password(self, instance, body):
        raise webob.exc.HTTPNotImplemented()

    def index(self, req, tenant_id):
        """Return all instances."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing a database instance for tenant '%s'") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        servers, marker = models.Instances.load(context)
        view = views.InstancesView(servers, req=req)
        paged = pagination.SimplePaginatedDataView(req.url, 'instances', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def backups(self, req, tenant_id, id):
        """Return all backups for the specified instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing backups for instance '%s'") %
                 id)

        backups = backup_model.list_for_instance(id)
        return wsgi.Result(backup_views.BackupViews(backups).data(), 200)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        server = models.load_instance_with_guest(models.DetailInstance,
                                                 context, id)
        return wsgi.Result(views.InstanceDetailView(server,
                                                    req=req).data(), 200)

    def delete(self, req, tenant_id, id):
        """Delete a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Deleting a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)
        # TODO(hub-cap): turn this into middleware
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.load_any_instance(context, id)
        instance.delete()
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(None, 202)

    def create(self, req, body, tenant_id):
        # TODO(hub-cap): turn this into middleware
        LOG.info(_("Creating a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("body : '%s'\n\n") % body)
        context = req.environ[wsgi.CONTEXT_KEY]
        # Set the service type to mysql if its not in the request
        service_type = (body['instance'].get('service_type') or
                        CONF.service_type)
        service = models.ServiceImage.find_by(service_name=service_type)
        image_id = service['image_id']
        name = body['instance']['name']
        flavor_ref = body['instance']['flavorRef']
        flavor_id = utils.get_id_from_href(flavor_ref)

        if 'configuration_ref' in body['instance']:
            configuration_ref = body['instance']['configuration_ref']
            configuration_id = utils.get_id_from_href(configuration_ref)

            # ensure a valid configuration has been passed in and that it
            # belongs to the user requesting it.
            try:
                Configuration.load(context, configuration_id)
            except ModelNotFoundError:
                raise exception.NotFound(
                    message='Configuration group %s could not be found'
                    % configuration_id)
        else:
            configuration_id = None

        databases = populate_validated_databases(
            body['instance'].get('databases', []))
        users = None
        try:
            users = populate_users(body['instance'].get('users', []))
        except ValueError as ve:
            raise exception.BadRequest(msg=ve)

        if 'volume' in body['instance']:
            volume_size = int(body['instance']['volume']['size'])
        else:
            volume_size = None

        if 'restorePoint' in body['instance']:
            backupRef = body['instance']['restorePoint']['backupRef']
            backup_id = utils.get_id_from_href(backupRef)
        else:
            backup_id = None

        instance = models.Instance.create(context, name, flavor_id,
                                          image_id, databases, users,
                                          service_type, volume_size,
                                          backup_id, configuration_id)

        view = views.InstanceDetailView(instance, req=req)
        return wsgi.Result(view.data(), 200)

    def update(self, req, id, body, tenant_id):
        ## TODO(jodom): add support for updating config grp.
        LOG.info(_("Updating instance for tenant id %s" % tenant_id))
        LOG.info(_("req: %s" % req))
        LOG.info(_("body: %s" % body))
        context = req.environ[wsgi.CONTEXT_KEY]

        instance = models.Instance.load(context, id)

        # update name, if supplied
        if 'name' in body["instance"]:
            models.Instance.update_db(instance, name=body["instance"]["name"])

        # if configuration_ref is set, then we will update the instance to use
        # the new configuration.  If configuration_ref is empty, we want to
        # disassociate the instance from the configuration group and remove the
        # active overrides file.
        if 'configuration_ref' in body["instance"]:
            configuration_ref = body["instance"]["configuration_ref"]

            if configuration_ref:
                configuration_id = utils.get_id_from_href(
                    body["instance"]["configuration_ref"])

                configuration = models.Configuration.load(
                    context, configuration_id)

                overrides = {}
                for i in configuration.items:
                    overrides[i.configuration_key] = i.configuration_value

                LOG.info(overrides)

                instance.update_overrides(overrides)
                models.Instance.update_db(instance,
                                          configuration_id=configuration_id)
            else:
                instance.update_overrides({})
                models.Instance.update_db(instance, configuration_id=None)

        return wsgi.Result(None, 202)

    @staticmethod
    def _validate_body_not_empty(body):
        """Check that the body is not empty"""
        if not body:
            msg = "The request contains an empty body"
            raise exception.TroveError(msg)

    @staticmethod
    def _validate_resize_volume(volume):
        """
        We are going to check that volume resizing data is present.
        """
        if 'size' not in volume:
            raise exception.BadRequest(
                "Missing 'size' property of 'volume' in request body.")
        InstanceController._validate_volume_size(volume['size'])

    @staticmethod
    def _validate_volume_size(size):
        """Validate the various possible errors for volume size"""
        try:
            volume_size = float(size)
        except (ValueError, TypeError) as err:
            LOG.error(err)
            msg = ("Required element/key - instance volume 'size' was not "
                   "specified as a number (value was %s)." % size)
            raise exception.TroveError(msg)
        if int(volume_size) != volume_size or int(volume_size) < 1:
            msg = ("Volume 'size' needs to be a positive "
                   "integer value, %s cannot be accepted."
                   % volume_size)
            raise exception.TroveError(msg)

    @staticmethod
    def _validate(body):
        """Validate that the request has all the required parameters"""
        InstanceController._validate_body_not_empty(body)

        try:
            body['instance']
            body['instance']['flavorRef']
            name = body['instance'].get('name', '').strip()
            if not name:
                raise exception.MissingKey(key='name')
            if CONF.trove_volume_support:
                if body['instance'].get('volume', None):
                    if body['instance']['volume'].get('size', None):
                        volume_size = body['instance']['volume']['size']
                        InstanceController._validate_volume_size(volume_size)
                    else:
                        raise exception.MissingKey(key="size")
                else:
                    raise exception.MissingKey(key="volume")

        except KeyError as e:
            LOG.error(_("Create Instance Required field(s) - %s") % e)
            raise exception.TroveError("Required element/key - %s "
                                          "was not specified" % e)
