#    Copyright 2012 OpenStack Foundation
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

import io
import jinja2

ENV = jinja2.Environment(loader=jinja2.ChoiceLoader([
    jinja2.FileSystemLoader("/etc/trove/templates"),
    jinja2.PackageLoader("trove", "templates")
]))


from ConfigParser import *


class MyConfigParser(SafeConfigParser):
    def _read(self, fp, fpname):
        """
          Parse a sectioned setup file.

          The sections in setup file contains a title line at the top,
          indicated by a name in square brackets (`[]'), plus key/value
          options lines, indicated by `name: value' format lines.
          Continuations are represented by an embedded newline then
          leading whitespace.  Blank lines, lines beginning with a '#',
          and just about everything else are ignored.
        """

        cursect = None                            # None, or a dictionary
        optname = None
        lineno = 0
        e = None                                  # None, or an exception
        while True:
            line = fp.readline()
            if not line:
                break
            lineno = lineno + 1
            # comment or blank line?
            if line.strip() == '' or line[0] in '#;':
                continue
            if line.split(None, 1)[0].lower() == 'rem' and line[0] in "rR":
                # no leading whitespace
                continue
            # continuation line?
            if line[0].isspace() and cursect is not None and optname:
                value = line.strip()
                if value:
                    cursect[optname] = "%s\n%s" % (cursect[optname], value)
            # a section header or option header?
            else:
                # is it a section header?
                mo = self.SECTCRE.match(line)
                if mo:
                    sectname = mo.group('header')
                    if sectname in self._sections:
                        cursect = self._sections[sectname]
                    elif sectname == DEFAULTSECT:
                        cursect = self._defaults
                    else:
                        cursect = self._dict()
                        cursect['__name__'] = sectname
                        self._sections[sectname] = cursect
                    # So sections can't start with a continuation line
                    optname = None
                # no section header in the file?
                elif cursect is None:
                    raise MissingSectionHeaderError(fpname, lineno, line)
                # an option line?
                else:
                    mo = self.OPTCRE.match(line)
                    if mo:
                        optname, vi, optval = mo.group('option', 'vi', 'value')
                        if vi in ('=', ':') and ';' in optval:
                            # ';' is a comment delimiter only if it follows
                            # a spacing character
                            pos = optval.find(';')
                            if pos != -1 and optval[pos-1].isspace():
                                optval = optval[:pos]
                        optval = optval.strip()
                        # allow empty values
                        if optval == '""':
                            optval = ''
                        optname = self.optionxform(optname.rstrip())
                        cursect[optname] = optval
                    elif line:
                        # (cp16net) changed this to support a line without a
                        # key value pair.
                        # example in my.cnf:
                        # [mysqld]
                        # skip-external-locking
                        optname = line.strip()
                        cursect[optname] = None
                    else:
                        # a non-fatal parsing error occurred.  set up the
                        # exception but keep going. the exception will be
                        # raised at the end of the file and will contain a
                        # list of all bogus lines
                        if not e:
                            e = ParsingError(fpname)
                        e.append(lineno, repr(line))
        # if any parsing errors occurred, raise an exception
        if e:
            raise e


class SingleInstanceConfigTemplate(object):
    """ This class selects a single configuration file by database type for
    rendering on the guest """
    def __init__(self, service_type, flavor_dict, instance_id,
                 overrides=False):
        """ Constructor

        :param service_type: The database type.
        :type name: str.
        :param flavor_dict: dict containing flavor details for use in jinja.
        :type flavor_dict: dict.
        :param instance_id: trove instance id
        :type: instance_id: str

        """
        self.flavor_dict = flavor_dict
        if overrides:
            template_filename = "%s.override.config.template" % service_type
        else:
            template_filename = "%s.config.template" % service_type
        self.template = ENV.get_template(template_filename)
        self.instance_id = instance_id

    def render(self, **kwargs):
        """ Renders the jinja template

        :returns: str -- The rendered configuration file

        """
        server_id = self._calculate_unique_id()
        self.config_contents = self.template.render(
            flavor=self.flavor_dict, server_id=server_id, **kwargs)
        return self.config_contents

    def render_dict(self):
        config = self.render()
        cfg = MyConfigParser()
        # convert unicode to ascii because config parse was not happy
        cfgstr = str(config)
        good_cfg = self._remove_commented_lines(cfgstr)

        cfg.readfp(io.BytesIO(str(good_cfg)))
        return cfg.items("mysqld")

    def _remove_commented_lines(self, config_str):
        ret = []
        for line in config_str.splitlines():
            if line.startswith('#'):
                continue
            elif line.startswith('!'):
                continue
            elif line.startswith(':'):
                continue
            else:
                ret.append(line)
        rendered = "\n".join(ret)
        return rendered

    def _calculate_unique_id(self):
        """
        Returns a positive unique id based off of the instance id

        :return: a positive integer
        """
        return abs(hash(self.instance_id) % (2 ** 31))


class HeatTemplate(object):
    template_contents = """HeatTemplateFormatVersion: '2012-12-12'
Description: Instance creation
Parameters:
  KeyName: {Type: String}
  Flavor: {Type: String}
  VolumeSize: {Type: Number}
  ServiceType: {Type: String}
  InstanceId: {Type: String}
  AvailabilityZone : {Type: String}
Resources:
  BaseInstance:
    Type: AWS::EC2::Instance
    Metadata:
      AWS::CloudFormation::Init:
        config:
          files:
            /etc/guest_info:
              content:
                Fn::Join:
                - ''
                - ["[DEFAULT]\\nguest_id=", {Ref: InstanceId},
                  "\\nservice_type=", {Ref: ServiceType}]
              mode: '000644'
              owner: root
              group: root
    Properties:
      ImageId:
        Fn::Join:
        - ''
        - ["ubuntu_", {Ref: ServiceType}]
      InstanceType: {Ref: Flavor}
      KeyName: {Ref: KeyName}
      AvailabilityZone: {Ref: AvailabilityZone}
      UserData:
        Fn::Base64:
          Fn::Join:
          - ''
          - ["#!/bin/bash -v\\n",
              "/opt/aws/bin/cfn-init\\n",
              "sudo service trove-guest start\\n"]
  DataVolume:
    Type: AWS::EC2::Volume
    Properties:
      Size: {Ref: VolumeSize}
      AvailabilityZone: {Ref: AvailabilityZone}
      Tags:
      - {Key: Usage, Value: Test}
  MountPoint:
    Type: AWS::EC2::VolumeAttachment
    Properties:
      InstanceId: {Ref: BaseInstance}
      VolumeId: {Ref: DataVolume}
      Device: /dev/vdb"""

    def template(self):
        return self.template_contents
