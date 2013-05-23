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

import ConfigParser
import io
import jinja2

ENV = jinja2.Environment(loader=jinja2.ChoiceLoader([
    jinja2.FileSystemLoader("/etc/trove/templates"),
    jinja2.PackageLoader("trove", "templates")
]))


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
        cfg = ConfigParser.ConfigParser(allow_no_value=True)
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
