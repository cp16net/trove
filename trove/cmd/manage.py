#!/usr/bin/env python

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

import gettext
import inspect
import sys
import os

from oslo.config import cfg

gettext.install('trove', unicode=1)

from trove import version
# from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.db import get_db_api
from trove.openstack.common import log as logging
from trove.datastore import models as datastore_models

from trove.db import migration

CONF = cfg.CONF


# Decorators for actions
def args(*args, **kwargs):
    def _decorator(func):
        func.__dict__.setdefault('args', []).insert(0, (args, kwargs))
        return func
    return _decorator


class Commands(object):

    def __init__(self):
        self.db_api = get_db_api()

    def db_sync(self, repo_path=None):
        self.db_api.db_sync(CONF, repo_path=repo_path)

    def db_upgrade(self, version=None, repo_path=None):
        self.db_api.db_upgrade(CONF, version, repo_path=None)

    def db_downgrade(self, version, repo_path=None):
        self.db_api.db_downgrade(CONF, version, repo_path=None)

    def execute(self):
        exec_method = getattr(self, CONF.action.name)
        args = inspect.getargspec(exec_method)
        args.args.remove('self')
        kwargs = {}
        for arg in args.args:
            kwargs[arg] = getattr(CONF.action, arg)
        exec_method(**kwargs)

    def datastore_update(self, datastore_name, default_version):
        try:
            datastore_models.update_datastore(datastore_name,
                                              default_version)
            print("Datastore '%s' updated." % datastore_name)
        except exception.DatastoreVersionNotFound as e:
            print(e)

    def datastore_version_update(self, datastore, version_name, manager,
                                 image_id, packages, active):
        try:
            datastore_models.update_datastore_version(datastore,
                                                      version_name,
                                                      manager,
                                                      image_id,
                                                      packages, active)
            print("Datastore version '%s' updated." % version_name)
        except exception.DatastoreNotFound as e:
            print(e)

    def db_wipe(self, repo_path):
        """Drops the database and recreates it."""
        self.db_api.drop_db(CONF)
        self.db_sync()

    def params_of(self, command_name):
        if Commands.has(command_name):
            return utils.MethodInspector(getattr(self, command_name))

class DbCommands(object):
    """Class for managing the database."""

    def __init__(self):
        self.db_api = get_db_api()

    @args('repo_path', nargs='?', default=None,
          help='Repository Path')
    def sync(self, repo_path=None):
        """Sync the database up to the most recent version."""
        # return migration.db_sync(version)
        self.db_api.db_sync(CONF, repo_path=repo_path)

    @args('version', nargs='?', default=None,
          help='Database version')
    @args('repo_path', nargs='?', default=None,
          help='Repository Path')
    def upgrade(self, version=None, repo_path=None):
        self.db_api.db_upgrade(CONF, version, repo_path=repo_path)

    @args('repo_path', nargs='?', default=None,
          help='Repository Path')
    def wipe(self, repo_path):
        """Drops the database and recreates it."""
        self.db_api.drop_db(CONF)
        self.db_sync()


class DatastoreCommands(object):
    """Class for managing datastores."""

    @args('datastore_name', nargs='?', default=None,
          help='Datastore Name')
    @args('default_version', nargs='?', default=None,
          help='Default Version to set the Datastore to')
    def update(self, datastore_name, default_version):
        try:
            datastore_models.update_datastore(datastore_name,
                                              default_version)
            print("Datastore '%s' updated." % datastore_name)
        except exception.DatastoreVersionNotFound as e:
            print(e)

    @args('datastore', nargs='?', default=None,
          help='Datastore Name')
    @args('version_name', nargs='?', default=None,
          help='Friendly Version name to call the Datastore Version')
    @args('manager', nargs='?', default=None,
          help='Manager name to set the Datastore Version to')
    @args('image_id', nargs='?', default=None,
          help='Image id to set the Datastore Version to')
    @args('packages', nargs='?', default=None,
          help='Packages needed for the Datastore Version')
    @args('active', nargs='?', default=None,
          help='Set the Datastore Version active or not')
    def version_update(self, datastore, version_name, manager,
                                 image_id, packages, active):
        try:
            datastore_models.update_datastore_version(datastore,
                                                      version_name,
                                                      manager,
                                                      image_id,
                                                      packages, active)
            print("Datastore version '%s' updated." % version_name)
        except exception.DatastoreNotFound as e:
            print(e)


CATEGORIES = {
    'db': DbCommands,
    # 'version': VersionCommands,
    'datastore': DatastoreCommands,
}


def methods_of(obj):
    """Get all callable methods of an object that don't start with underscore
    returns a list of tuples of the form (method_name, method)
    """
    result = []
    for i in dir(obj):
        if callable(getattr(obj, i)) and not i.startswith('_'):
            result.append((i, getattr(obj, i)))
    return result


def add_command_parsers(subparsers):
    for category in CATEGORIES:
        command_object = CATEGORIES[category]()

        parser = subparsers.add_parser(category)
        parser.set_defaults(command_object=command_object)

        category_subparsers = parser.add_subparsers(dest='action')

        for (action, action_fn) in methods_of(command_object):
            parser = category_subparsers.add_parser(action)

            action_kwargs = []
            for args, kwargs in getattr(action_fn, 'args', []):
                parser.add_argument(*args, **kwargs)

            parser.set_defaults(action_fn=action_fn)
            parser.set_defaults(action_kwargs=action_kwargs)


category_opt = cfg.SubCommandOpt('category',
                                 title='Command categories',
                                 handler=add_command_parsers)


def get_arg_string(args):
    arg = None
    if args[0] == '-':
    # (Note)zhiteng: args starts with FLAGS.oparser.prefix_chars
    # is optional args. Notice that cfg module takes care of
    # actual ArgParser so prefix_chars is always '-'.
        if args[1] == '-':
            # This is long optional arg
            arg = args[2:]
        else:
            arg = args[3:]
    else:
        arg = args

    return arg


def fetch_func_args(func):
    fn_args = []
    for args, kwargs in getattr(func, 'args', []):
        arg = get_arg_string(args[0])
        fn_args.append(getattr(CONF.category, arg))

    return fn_args


def main():
    """Parse options and call the appropriate class/method."""
    CONF.register_cli_opt(category_opt)
    script_name = sys.argv[0]
    if len(sys.argv) < 2:
        print(_("\nOpenStack Trove version: %(version)s\n") %
              {'version': version.version_string()})
        print(script_name + " category action [<args>]")
        print(_("Available categories:"))
        for category in CATEGORIES:
            print(_("\t%s") % category)
        sys.exit(2)

    try:
        CONF(sys.argv[1:], project='trove',
             version=version.version_string())
        logging.setup("trove")
    except cfg.ConfigFilesNotFoundError:
        cfgfile = CONF.config_file[-1] if CONF.config_file else None
        if cfgfile and not os.access(cfgfile, os.R_OK):
            st = os.stat(cfgfile)
            print(_("Could not read %s. Re-running with sudo") % cfgfile)
            try:
                os.execvp('sudo', ['sudo', '-u', '#%s' % st.st_uid] + sys.argv)
            except Exception:
                print(_('sudo failed, continuing as if nothing happened'))

        print(_('Please re-run trove-manage as root.'))
        sys.exit(2)

    fn = CONF.category.action_fn

    fn_args = fetch_func_args(fn)
    fn(*fn_args)
