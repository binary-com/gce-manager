from pprint import *
from constant import *

class Instance:
    def __init__(self, name=None):
        self.name = name
        self.creation_ts = None
        self.ip = None
        self.machine_type = None
        self.preemptible = None
        self.status = None
        self.zone = None

        self.flag = INSTANCE_FLAG_NEW
        self.uptime_hour = 0

    def __repr__(self):
        return pformat(vars(self), indent=PRETTY_PRINT_INDENT, width=PRETTY_PRINT_WIDTH)
