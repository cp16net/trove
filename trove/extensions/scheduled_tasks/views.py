# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack LLC.
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


class ScheduledTaskView(object):

    def __init__(self, scheduled_task):
        self.scheduled_task = scheduled_task

    def data(self):
        return {
        "scheduled_task": {
            "id": self.scheduled_task.id,
            "name": self.scheduled_task.name,
            "description": self.scheduled_task.description,
            "instance_id": self.scheduled_task.instance_id,
            "type": self.scheduled_task.task_type,
            "enabled": self.scheduled_task.enabled,
            "created": self.scheduled_task.created,
            "updated": self.scheduled_task.updated
            }
        }


class ScheduledTaskViews(object):

    def __init__(self, scheduled_tasks):
        self.scheduled_tasks = scheduled_tasks

    def data(self):
        scheduled_tasks = []

        for task in self.scheduled_tasks:
            scheduled_task = ScheduledTaskView(task).data()["scheduled_task"]
            scheduled_tasks.append(scheduled_task)
        return {"scheduled_tasks": scheduled_tasks}
