import sys
import threading
import time

# External modules
from constant import *
from instance import *
from googleapiclient import discovery
from util import *

class GAPI:
    def __init__(self, config_obj, slackbot=None):
        self.abort_all = False
        self.config = config_obj
        self.logger = Util('gapi').logger
        self.all_instance = []
        self.lock = threading.Lock()
        self.slackbot = slackbot
        self.zone_count = len(self.config.ZONE_LIST)

    def _dict_to_instance(self, _dict):
        try:
            has_networkIP = len(_dict['networkInterfaces']) > 0 and 'networkIP' in _dict['networkInterfaces'][0]
            instance = Instance(_dict['name'])
            instance.creation_ts = _dict['creationTimestamp']
            instance.ip = _dict['networkInterfaces'][0]['networkIP'] if has_networkIP else '(None)'
            instance.machine_type = _dict['machineType'].split('/')[-1]
            instance.preemptible = _dict['scheduling']['preemptible']
            instance.status = _dict['status']
            instance.zone = _dict['zone'].split('/')[-1]
            return instance
        except Exception, exception:
            self.log(API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception))

    def _get_all_instance_worker(self, zone):
        locked_acquired = False
        try:
            _instance_list = self.list_instance(zone)
            if _instance_list != None:
                self.lock.acquire()
                locked_acquired = True
                for instance in _instance_list:
                    if self.abort_all:
                        break
                    else:
                        _instance = self._dict_to_instance(instance)
                        instance_excluded = _instance.name in self.config.EXCLUDED_INSTANCE_LIST

                        if not instance_excluded and self._match_name_prefix_list(_instance.name):
                            self.all_instance.append(_instance)
                self.zone_count -= 1
                self.lock.release()
        except Exception, exception:
            self.log(API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception))
            if locked_acquired:
                self.lock.release()

    def _log(self, message):
        self.logger.info(subject)

        if self.slackbot != None and len(self.config.SLACKBOT_API_TOKEN.strip()) > 0:
            self.slackbot.send_message(self.config.SLACKBOT_LOGGING_CHANNEL, subject)

    def _match_name_prefix_list(self, instance_name):
        for prefix in self.config.INSTANCE_NAME_PREFIX_LIST:
            if instance_name.startswith(prefix):
                return True
        return False

    def create_disk_from_snapshot(self, zone, disk_name, retry_count=MAX_API_RETRY_COUNT):
        try:
            config = {
                'name': disk_name,
                'sourceSnapshot': self.config.SNAPSHOT_SOURCE,
                'type': 'projects/%s/zones/%s/diskTypes/%s' % (self.config.PROJECT_ID, zone, self.config.DISK_TYPE)
            }
            compute = discovery.build(API_TYPE, API_VERSION, credentials=self.config.credentials)
            return compute.disks().insert(project=self.config.PROJECT_ID, zone=zone, body=config).execute()
        except Exception, exception:
            if retry_count > 0 and not self.abort_all:
                self.log(API_RETRY_MESSAGE % (sys._getframe().f_code.co_name, exception))
                return self.create_disk_from_snapshot(zone, disk_name, (retry_count - 1))
            else:
                self.log(API_MAX_RETRY_NESSAGE % (sys._getframe().f_code.co_name, MAX_API_RETRY_COUNT, exception))

    def create_instance(self, zone, instance_name, disk_name, preemptible, retry_count=MAX_API_RETRY_COUNT):
        try:
            config = {
                'name': instance_name,
                'machineType': 'projects/%s/zones/%s/machineTypes/%s' % (self.config.PROJECT_ID, zone, self.config.MACHINE_TYPE),
                'tags': {
                    "items": self.config.INSTANCE_TAG_LIST
                },
                'disks': [{
                    'type': 'PERSISTENT',
                    'boot': 'true',
                    'mode': 'READ_WRITE',
                    'autoDelete': 'true',
                    'deviceName': disk_name,
                    'source': 'projects/%s/zones/%s/disks/%s' % (self.config.PROJECT_ID, zone, disk_name)
                }],
                'canIpForward': 'false',
                'networkInterfaces': [{
                    'network': 'projects/%s/global/networks/default' % self.config.PROJECT_ID
                }],
                'scheduling': {
                    'preemptible': str(preemptible).lower(),
                    'onHostMaintenance': 'TERMINATE' if preemptible else 'MIGRATE',
                    'automaticRestart': 'false' if preemptible else 'true'
                },
                "metadata": {
                    "items": [{
                        "key": "fqdn",
                        "value": instance_name
                    }]
                },
                'serviceAccounts': [{
                    'email': 'default',
                    'scopes': [
                        'https://www.googleapis.com/auth/devstorage.read_only',
                        'https://www.googleapis.com/auth/logging.write',
                        'https://www.googleapis.com/auth/monitoring.write',
                        'https://www.googleapis.com/auth/cloud.useraccounts.readonly'
                    ]
                }]
            }

            compute = discovery.build(API_TYPE, API_VERSION, credentials=self.config.credentials)
            return compute.instances().insert(project=self.config.PROJECT_ID, zone=zone, body=config).execute()
        except Exception, exception:
            if retry_count > 0 and not self.abort_all:
                self.log(API_RETRY_MESSAGE % (sys._getframe().f_code.co_name, exception))
                return self.create_instance(zone, instance_name, disk_name, preemptible, (retry_count - 1))
            else:
                self.log(API_MAX_RETRY_NESSAGE % (sys._getframe().f_code.co_name, MAX_API_RETRY_COUNT, exception))

    def create_instance_from_snapshot(self, zone, instance_name, preemptible):
        try:
            try:
                response = self.create_disk_from_snapshot(zone, instance_name)
                self.wait_for_operation(zone, response)
            except:
                self.log(API_FAILURE_MESSAGE % ('create_disk_from_snapshot', 'Skipped'))
            finally:
                return self.create_instance(zone, instance_name, instance_name, preemptible)
        except Exception, exception:
            self.log(API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception))

    def delete_instance(self, zone, instance_name, retry_count=MAX_API_RETRY_COUNT):
        try:
            compute = discovery.build(API_TYPE, API_VERSION, credentials=self.config.credentials)
            return compute.instances().delete(project=self.config.PROJECT_ID, zone=zone, instance=instance_name).execute()
        except Exception, exception:
            if retry_count > 0 and not self.abort_all:
                self.log(API_RETRY_MESSAGE % (sys._getframe().f_code.co_name, exception))
                return self.delete_instance(zone, instance_name, (retry_count - 1))
            else:
                self.log(API_MAX_RETRY_NESSAGE % (sys._getframe().f_code.co_name, MAX_API_RETRY_COUNT, exception))

    def get_all_instance(self, zone_list):
        try:
            # Use a separate thread in getting instance list for each zone
            self.all_instance, self.zone_count = [], len(zone_list)
            for zone in zone_list:
                if self.abort_all:
                    break
                else:
                    threading.Thread(target=self._get_all_instance_worker, args=(zone,)).start()

            # Check for completion of instance(s) retrieval every 100ms
            while self.zone_count > 0 and not self.abort_all:
                time.sleep(0.1)
            return self.all_instance
        except Exception, exception:
            self.log(API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception))

    def list_instance(self, zone, retry_count=MAX_API_RETRY_COUNT):
        try:
            compute = discovery.build(API_TYPE, API_VERSION, credentials=self.config.credentials)
            instances = compute.instances().list(project=self.config.PROJECT_ID, zone=zone).execute()
            if 'items' in instances:
                return instances['items']
            else:
                return []
        except Exception, exception:
            if retry_count > 0 and not self.abort_all:
                self.log(API_RETRY_MESSAGE % (sys._getframe().f_code.co_name, exception))
                return self.list_instance(zone, (retry_count - 1))
            else:
                self.log(API_MAX_RETRY_NESSAGE % (sys._getframe().f_code.co_name, MAX_API_RETRY_COUNT, exception))

    def shutdown(self):
        self.abort_all = True

    def start_instance(self, zone, instance_name, retry_count=MAX_API_RETRY_COUNT):
        try:
            compute = discovery.build(API_TYPE, API_VERSION, credentials=self.config.credentials)
            return compute.instances().start(project=self.config.PROJECT_ID, zone=zone, instance=instance_name).execute()
        except Exception, exception:
            if retry_count > 0 and not self.abort_all:
                self.log(API_RETRY_MESSAGE % (sys._getframe().f_code.co_name, exception))
                return self.start_instance(zone, instance_name, (retry_count - 1))
            else:
                self.log(API_MAX_RETRY_NESSAGE % (sys._getframe().f_code.co_name, MAX_API_RETRY_COUNT, exception))

    def stop_instance(self, zone, instance_name, retry_count=MAX_API_RETRY_COUNT):
        try:
            compute = discovery.build(API_TYPE, API_VERSION, credentials=self.config.credentials)
            return compute.instances().stop(project=self.config.PROJECT_ID, zone=zone, instance=instance_name).execute()
        except Exception, exception:
            if retry_count > 0 and not self.abort_all:
                self.log(API_RETRY_MESSAGE % (sys._getframe().f_code.co_name, exception))
                return self.stop_instance(zone, instance_name, (retry_count - 1))
            else:
                self.log(API_MAX_RETRY_NESSAGE % (sys._getframe().f_code.co_name, MAX_API_RETRY_COUNT, exception))

    def wait_for_operation(self, zone, op_response, retry_count=MAX_API_RETRY_COUNT):
        try:
            while True and op_response is not None:
                compute = discovery.build(API_TYPE, API_VERSION, credentials=self.config.credentials)
                result = compute.zoneOperations().get(project=self.config.PROJECT_ID, zone=zone, operation=op_response['name']).execute()

                if result['status'] == 'DONE' or self.abort_all:
                    return result['status']
                else:
                    time.sleep(1)
        except Exception, exception:
            if retry_count > 0 and not self.abort_all:
                self.log(API_RETRY_MESSAGE % (sys._getframe().f_code.co_name, exception))
                return self.wait_for_operation(zone, op_response, (retry_count - 1))
            else:
                self.log(API_MAX_RETRY_NESSAGE % (sys._getframe().f_code.co_name, MAX_API_RETRY_COUNT, exception))
