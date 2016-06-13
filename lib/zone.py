from pprint import *
from constant import *

class Zone:
    def __init__(self, name=None):
        self.name = name
        self.total_termination_count = 0
        self.total_uptime_hour = 0

    def __repr__(self):
        return pformat(vars(self), indent=PRETTY_PRINT_INDENT, width=PRETTY_PRINT_WIDTH)
