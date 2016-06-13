from pprint import *
from constant import *
from instance import *
from zone import *

class Cloud:
    def __init__(self, instance_list=None):
        self.zone_list = []
        if instance_list is None:
            self.instance_list = []
        else:
            self.instance_list = instance_list
            for instance in self.instance_list:
                self.add_zone(Zone(instance.zone))

    def add_instance(self, instance):
        self.instance_list.append(instance)

    def add_zone(self, zone):
        self.zone_list.append(zone)

    def delete_instance(self, instance_name):
        for instance in self.instance_list:
            if instance.name == instance_name:
                self.instance_list.remove(instance)
                break

    def delete_zone(self, zone_name):
        for zone in self.zone_list:
            if zone.name == zone_name:
                self.zone_list.remove(zone)
                break

    def get_instance(self, instance_name):
        for instance in self.instance_list:
            if instance.name == instance_name:
                return instance
        return Instance(instance_name)

    def get_instance_list(self, zone_name=None):
        if zone_name is None:
            return self.instance_list
        else:
            instance_list = []
            for instance in self.instance_list:
                if instance.zone == zone_name:
                    instance_list.append(instance)
            return instance_list

    def get_zone(self, zone_name):
        for zone in self.zone_list:
            if zone.name == zone_name:
                return zone
        return Zone(zone_name)

    def get_zone_list(self):
        return self.zone_list

    def has_instance(self, instance_name):
        for instance in self.instance_list:
            if instance.name == instance_name:
                return True
        return False

    def has_zone(self, zone_name):
        for zone in self.zone_list:
            if zone.name == zone_name:
                return True
        return False

    def update_instance(self, instance):
        current_instance = self.get_instance(instance.name)
        current_instance.creation_ts = instance.creation_ts
        current_instance.ip = instance.ip
        current_instance.machine_type = instance.machine_type
        current_instance.preemptible = instance.preemptible
        current_instance.status = instance.status
        current_instance.zone = instance.zone
        current_instance.flag = instance.flag
        current_instance.uptime_hour = instance.uptime_hour

    def update_zone(self, zone):
        current_zone = self.get_zone(zone.name)
        current_zone.total_termination_count = zone.total_termination_count
        current_zone.total_uptime_hour = zone.total_uptime_hour

    def __repr__(self):
        return pformat(vars(self), indent=PRETTY_PRINT_INDENT, width=PRETTY_PRINT_WIDTH)
