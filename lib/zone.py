from pprint import *
from constant import *

class Zone:
    def __init__(self, name=None):
        self.name = name
        self.pe_uptime_hour = 0
        self.npe_uptime_hour = 0
        self.total_termination_count = 0
        self.total_uptime_hour = self.pe_uptime_hour + self.npe_uptime_hour
        self.termination_rate = (float(self.total_termination_count) / self.total_uptime_hour) if self.total_uptime_hour > 0 else 0.0

    def __repr__(self):
        return pformat(vars(self), indent=PRETTY_PRINT_INDENT, width=PRETTY_PRINT_WIDTH)
