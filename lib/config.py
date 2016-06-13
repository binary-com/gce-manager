import os
import yaml
from pprint import *

from constant import *
from oauth2client.client import GoogleCredentials

class Config:
    def __init__(self, config_file):
        self.config = yaml.load(open(config_file, 'r').read())
        self.PROJECT_ID                                 = self.config['GCE_PROJECT_ID']
        self.GOOGLE_APPLICATION_CREDENTIALS             = self.config['GCE_GOOGLE_APPLICATION_CREDENTIALS']
        self.SNAPSHOT_SOURCE                            = self.config['GCE_SNAPSHOT_SOURCE']
        self.MACHINE_TYPE                               = self.config['GCE_MACHINE_TYPE']
        self.DISK_TYPE                                  = self.config['GCE_DISK_TYPE']
        self.ZONE_LIST                                  = self.config['GCE_ZONE_LIST'].split(' ')
        self.MIN_INSTANCE_COUNT                         = self.config['GCE_MIN_INSTANCE_COUNT']
        self.MIN_ZONE_SPREAD_COUNT                      = self.config['GCE_MIN_ZONE_SPREAD_COUNT']
        self.NON_PREEMPTIBLE_INSTANCE_MIN_ALIVE_HOUR    = self.config['GCE_NON_PREEMPTIBLE_INSTANCE_MIN_ALIVE_HOUR']
        self.PREEMPTIBLE_HIGH_DEMAND_ZONE_THRESHOLD     = self.config['GCE_PREEMPTIBLE_HIGH_DEMAND_ZONE_THRESHOLD']
        self.EXCLUDED_INSTANCE_LIST                     = self.config['GCE_EXCLUDED_INSTANCE_LIST'].split(' ')
        self.INSTANCE_NAME_PREFIX_LIST                  = self.config['GCE_INSTANCE_NAME_PREFIX_LIST'].split(' ')
        self.INSTANCE_TAG_LIST                          = self.config['GCE_INSTANCE_TAG_LIST'].split(' ')
        self.EMAIL_RECIPIENT_LIST                       = self.config['GCEM_EMAIL_RECIPIENT_LIST'].split(' ')

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.GOOGLE_APPLICATION_CREDENTIALS
        self.credentials = GoogleCredentials.get_application_default()

    def get_raw_string_list(self):
        raw_output = []
        for key in self.config:
            raw_output.append((key, self.config[key]))
        return raw_output

    def __repr__(self):
        return pformat(vars(self), indent=PRETTY_PRINT_INDENT, width=PRETTY_PRINT_WIDTH)
