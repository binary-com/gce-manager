#!/usr/bin/python

import signal
import sys
import time
from copy import deepcopy
from datetime import datetime
from pprint import pprint

# External modules
from lib.cloud import *
from lib.config import *
from lib.constant import *
from lib.gapi import *
from lib.logviewer import *
from lib.util import *
from lib.HTML import *


class GCE_Manager:
    def __init__(self, config_file):
        self.abort_all = False
        self.email_queue = []
        self.instance_recovering = 0
        self.config = Config(config_file)
        self.util = Util(GCEM_LOGGER_NAME)
        self.logger = self.util.logger
        self.logviewer = logviewer()
        self.logviewer.hook_logger(GCEM_LOGGER_NAME)

        self.engine = GAPI(self.config)
        self.cloud = Cloud(self.engine.get_all_instance(self.config.ZONE_LIST))
        self.cloud_cache, self.instance_event_list = self.load_cached_cloud(), []
        self.termination_rate_threshold = float(1) / self.config.NON_PREEMPTIBLE_INSTANCE_MIN_ALIVE_HOUR
        self.unstable_zone_threshold = float(len(self.config.ZONE_LIST)) * self.config.PREEMPTIBLE_HIGH_DEMAND_ZONE_THRESHOLD

    def flush_cloud_cache(self):
        # Flush to filesystem only when no pending instance recovery operation
        if self.instance_recovering == 0:
            self.util.save_object(self.config.PROJECT_ID, self.cloud_cache)

    def flush_email_queue(self):
        while len(self.email_queue) > 0:
            body, recipient, subject = self.email_queue.pop(0)
            self.util.send_email(body, recipient, subject)

    def get_cached_cloud(self, instance_name, zone_name):
        cached_instance = self.cloud_cache.get_instance(instance_name)
        cached_zone = self.cloud_cache.get_zone(zone_name)
        return cached_instance, cached_zone

    def get_config_summary_table(self):
        config_record = []

        for key, value in self.config.get_raw_string_list():
            config_record.append([key, value])

        return str(table(config_record))

    def get_cooldown_time(self, start_time, max_cooldown=1):
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        cooldown_time = 0 if elapsed_time > max_cooldown else (max_cooldown - elapsed_time)
        return cooldown_time

    def get_event_message_param(self, instance, include_uptime_hour=False):
        instance_type = GCE_PREEMPTIBLE if instance.preemptible else GCE_NON_PREEMPTIBLE
        if include_uptime_hour:
            return (instance_type, instance.name, instance.zone, round(instance.uptime_hour, UPTIME_DECIMAL))
        else:
            return (instance_type, instance.name, instance.zone)

    def get_instance_sorted_zone_table(self, exclude_low_preemptible_supply_zone=False):
        unsorted_zone_table, sorted_zone_table = [], []
        zone_instance_count_table = self.get_zone_instance_count_table()

        for zone in self.cloud_cache.get_zone_list():
            if not self.low_preemptible_supply(zone.name) or not exclude_low_preemptible_supply_zone:
                instance_count = zone_instance_count_table[zone.name] if zone.name in zone_instance_count_table else 0
                unsorted_zone_table.append([instance_count, zone.name])

        def get_key(item):
            return item[0]

        for instance_count, zone_name in sorted(unsorted_zone_table, key=get_key):
            termination_rate = self.cloud_cache.get_zone(zone_name).termination_rate
            sorted_zone_table.append((zone_name, instance_count, termination_rate))

        return sorted_zone_table

    def get_instance_summary_table(self):
        instance_record = [TABLE_TITLE_INSTANCE]

        for instance in self.cloud_cache.get_instance_list():
            date_time, fraction = instance.creation_ts.split('.')

            instance_record.append([
                instance.name,
                instance.machine_type,
                instance.zone,
                instance.ip,
                str(instance.preemptible),
                date_time,
                str(round(instance.uptime_hour, UPTIME_DECIMAL)),
                instance.flag,
                instance.status.lower()])

        return str(table(instance_record))

    def get_summary_report(self):
        log_buffer = self.logviewer.get_log_buffer(REPORT_LOG_COUNT)
        params = (  HTML_LINE_BREAK_TAG.join(log_buffer),
                    self.get_zone_summary_table(),
                    self.get_instance_summary_table(),
                    self.get_config_summary_table(),
                    DEFAULT_EMAIL_FOOTER   )

        return REPORT_TEMPLATE % params

    def get_termination_rate_sorted_zone_table(self, exclude_low_preemptible_supply_zone=False):
        unsorted_zone_table, sorted_zone_table = [], []
        zone_instance_count_table = self.get_zone_instance_count_table()

        for zone in self.cloud_cache.get_zone_list():
            if not self.low_preemptible_supply(zone.name) or not exclude_low_preemptible_supply_zone:
                unsorted_zone_table.append([zone.termination_rate, zone.name])

        def get_key(item):
            return item[0]

        for termination_rate, zone_name in sorted(unsorted_zone_table, key=get_key):
            instance_count = zone_instance_count_table[zone_name] if zone_name in zone_instance_count_table else 0
            sorted_zone_table.append((zone_name, instance_count, termination_rate))

        return sorted_zone_table

    def get_zone_candidate(self, instance):
        # Pick zone(s) with lower instance count to prioritize zone spread balance followed by termination rate
        zone_candidate_table, unique_instance_count_list = [], []
        for zone_name, instance_count, termination_rate in self.get_instance_sorted_zone_table(True):

            # Pick zone(s) with unique instance count up to the number of minimum zone spread
            if len(unique_instance_count_list) < self.config.MIN_ZONE_SPREAD_COUNT:
                zone_candidate_table.append([zone_name, instance_count, termination_rate])
                if not instance_count in unique_instance_count_list:
                    unique_instance_count_list.append(instance_count)

        # Pick the zone with lowest termination rate from zone_candidate_table
        _zone_name, _instance_count, _termination_rate = None, 0, 0
        for zone_name, instance_count, termination_rate in zone_candidate_table:
            # Pick zone record with lower instance termination rate
            if _zone_name == None or _termination_rate > termination_rate:
                _zone_name, _instance_count, _termination_rate = zone_name, instance_count, termination_rate
            # When zone record having same termination rate, pick the one with lower instance count
            elif _termination_rate == termination_rate:
                if _instance_count > instance_count:
                    _zone_name, _instance_count, _termination_rate = zone_name, instance_count, termination_rate

        return _zone_name

    def get_zone_info_list(self):
        zone_info_list, zone_instance_count_table = [], self.get_zone_instance_count_table()

        for zone in self.config.ZONE_LIST:
            cached_zone = self.cloud_cache.get_zone(zone)
            tt_count = cached_zone.total_termination_count
            termination_rate = (float(tt_count) / cached_zone.total_uptime_hour) if cached_zone.total_uptime_hour > 0 else 0.0
            instance_count = zone_instance_count_table[zone] if zone in zone_instance_count_table else 0
            zone_info_list.append((zone, instance_count, cached_zone.total_uptime_hour, tt_count, termination_rate))

        return zone_info_list

    def get_zone_instance_count_table(self):
        zone_instance_count_dict = {}

        for instance in self.cloud.get_instance_list():
            if instance.zone not in zone_instance_count_dict:
                zone_instance_count_dict[instance.zone] = 1
            else:
                zone_instance_count_dict[instance.zone] += 1
        return zone_instance_count_dict

    def get_zone_summary_table(self):
        zone_configured = [TABLE_TITLE_ZONE]

        for zone_info in self.get_zone_info_list():
            zone_name, instance_count, zone_total_uptime_hour, termination_count, termination_rate = zone_info
            zone_configured.append([
                zone_name,
                str(instance_count),
                str(round(zone_total_uptime_hour, UPTIME_DECIMAL)),
                str(termination_count),
                str(termination_rate)])

        return str(table(zone_configured))

    def instance_event_engine(self):
        while not self.abort_all:
            start_time = datetime.utcnow()
            self.instance_event_generator()
            self.update_cloud_metric()
            self.flush_cloud_cache()
            threading.Thread(target=self.flush_email_queue).start()
            time.sleep(self.get_cooldown_time(start_time))

    def instance_event_generator(self):
        while len(self.instance_event_list) > 0:
            _target, _instance = self.instance_event_list.pop(0)
            threading.Thread(target=_target, args=(_instance,)).start()

    def instance_matured(self, instance):
        pe_matured = (instance.flag == INSTANCE_FLAG_NEW and instance.uptime_hour >= INSTANCE_MATURITY_HOUR)
        npe_matured = instance.uptime_hour > self.config.NON_PREEMPTIBLE_INSTANCE_MIN_ALIVE_HOUR
        return pe_matured if instance.preemptible else npe_matured

    # TODO: Future enhancement
    # Auto-create instance from snapshot if instance count drop below self.config.MIN_INSTANCE_COUNT
    # Instance placement shall observed self.config.MIN_ZONE_SPREAD_COUNT
    def instance_restructure_engine(self):
        while not self.abort_all:
            start_time = datetime.utcnow()

            # IMPLEMENTATION HERE

            time.sleep(self.get_cooldown_time(start_time))

    def instance_status_updater(self):
        while not self.abort_all:
            start_time = datetime.utcnow()
            self.cloud = Cloud(self.engine.get_all_instance(self.config.ZONE_LIST))
            time.sleep(self.get_cooldown_time(start_time, max_cooldown=5))

    def load_cached_cloud(self):
        cloud_cache = self.util.load_object(self.config.PROJECT_ID)
        cloud_cache = Cloud() if cloud_cache == None else cloud_cache

        # Add any newly configured zone into local cache
        for zone_name in self.config.ZONE_LIST:
            if not cloud_cache.has_zone(zone_name):
                cloud_cache.add_zone(Zone(zone_name))
        return cloud_cache

    # TODO: Remove hardcoded email
    def log_and_email(self, subject, email=None):
        email = ['teo@binary.com']
        self.logger.info(subject)
        recipient = self.config.EMAIL_RECIPIENT_LIST if email == None else email
        self.email_queue.append((self.get_summary_report(), recipient, subject))

    def low_preemptible_supply(self, zone_name=None):
        unstable_zone_count = 0

        if zone_name != None:
            termination_rate = self.cloud_cache.get_zone(zone_name).termination_rate
            return termination_rate > self.termination_rate_threshold
        else:
            # Get zone(s) with available preemptible instance supply sorted by termination rate
            available_zone_count = len(self.get_termination_rate_sorted_zone_table(True))

            # Return overall zone count availability if the minimum zone spread with preemptible instance supply is met
            if available_zone_count > 0 and available_zone_count >= self.config.MIN_ZONE_SPREAD_COUNT:
                for zone_info in self.get_zone_info_list():
                    zone_name, instance_count, zone_total_uptime_hour, termination_count, termination_rate = zone_info
                    unstable_zone_count += 1 if (termination_rate > self.termination_rate_threshold) else 0
                return unstable_zone_count < self.unstable_zone_threshold
            else:
                return True

    def on_instance_created_notification(self, created_instance):
        self.logger.info(MESSAGE_CREATED % self.get_event_message_param(created_instance))

    def on_instance_deleted_notification(self, deleted_instance):
        self.logger.info(MESSAGE_DELETED % self.get_event_message_param(deleted_instance, True))

    def on_instance_running_notification(self, running_instance):
        # Only enabled when debugging issues
        # self.logger.info(MESSAGE_RUNNING % self.get_event_message_param(running_instance, True))
        return

    def on_instance_started_notification(self, started_instance):
        self.log_and_email(MESSAGE_STARTED % self.get_event_message_param(started_instance))

    def on_instance_terminated(self, terminated_instance):
        self.instance_recovering += 1

        # Wait until terminated instance is fully stopped
        while self.cloud.get_instance(terminated_instance.name).status != GCE_STATUS_TERMINATED:
            time.sleep(1)

        # Convert non-preemptible instance to preemptible instance
        if not terminated_instance.preemptible:
            self.recover_instance(terminated_instance, True)
        else:
            # Strategy 1: Recycling instance
            if terminated_instance.flag in [INSTANCE_FLAG_NEW, INSTANCE_FLAG_MATURED]:
                self.recover_instance(terminated_instance, True)
            else:
                if not self.low_preemptible_supply():
                    zone_candidate = self.get_zone_candidate(terminated_instance)

                    # Forward to Strategy 3 when best zone candidate is same with the instance terminated zone
                    if zone_candidate == terminated_instance.zone:
                        # Strategy 3: Convert instance to non-preemptible instance
                        self.recover_instance(terminated_instance, False)
                    else:
                        # Strategy 2: Relocate instance to different zone
                        self.recover_instance(terminated_instance, True, zone_candidate)
                else:
                    # Pick zone with the least instance count which is the first entry
                    zone_name, instance_count, termination_rate = self.get_instance_sorted_zone_table()[0]

                    # Strategy 3: Convert instance to non-preemptible instance
                    self.recover_instance(terminated_instance, False, zone_name)
        self.instance_recovering -= 1

    def on_instance_terminated_notification(self, terminated_instance):
        params = self.get_event_message_param(terminated_instance, True)
        self.log_and_email(MESSAGE_TERMINATED % params)

        # Convert non-preemptible instance to preemptible instance
        if not terminated_instance.preemptible:
            self.log_and_email(MESSAGE_CONVERT_PE % params)
        else:
            # Strategy 1: Recycling instance
            if terminated_instance.flag in [INSTANCE_FLAG_NEW, INSTANCE_FLAG_MATURED]:
                self.log_and_email(MESSAGE_RECYCLE % params)
            else:
                if not self.low_preemptible_supply():
                    zone_candidate = self.get_zone_candidate(terminated_instance)

                    # Forward to Strategy 3 when best zone candidate is same with the instance terminated zone
                    if zone_candidate == terminated_instance.zone:
                        # Strategy 3: Convert instance to non-preemptible instance
                        self.logger.info(MESSAGE_PE_HIGH_DEMAND)
                        self.log_and_email(MESSAGE_CONVERT_NPE % params)
                    else:
                        # Strategy 2: Relocate instance to different zone
                        self.log_and_email(MESSAGE_RELOCATE % params)
                else:
                    # Strategy 3: Convert instance to non-preemptible instance
                    self.logger.info(MESSAGE_PE_HIGH_DEMAND)
                    self.log_and_email(MESSAGE_CONVERT_NPE % params)

    def recover_instance(self, instance, preemptible, new_zone=None):
        target_zone = new_zone if new_zone != None else instance.zone

        # Start back the same instance if same preemptibility type and zone
        if instance.preemptible == preemptible and instance.zone == target_zone:
            self.engine.start_instance(target_zone, instance.name)
        else:
            # The 'preemptible' option cannot be changed after instance creation, hence recreate instance
            response = self.engine.delete_instance(instance.zone, instance.name)
            self.engine.wait_for_operation(instance.zone, response)
            self.engine.create_instance_from_snapshot(target_zone, instance.name, preemptible)

    def shutdown(self, message=None):
        if not self.abort_all:
            if message is not None:
                self.logger.info(message)
            self.abort_all = True
            self.engine.shutdown()

    def start(self):
        self.update_cloud_metric()
        self.log_and_email(STARTUP_MESSAGE % self.config.PROJECT_ID)

        if self.validate_rules():
            # Start polling instances status in all zones for any changes
            threading.Thread(target=self.instance_status_updater).start()

            # Start generating instances event such as creation, deletion, startup and termination
            threading.Thread(target=self.instance_event_engine).start()

            # Start waiting for jobs to increase/decrease instances if required
            threading.Thread(target=self.instance_restructure_engine).start()

            # Exit whenever shutdown signal triggered
            while not self.abort_all: time.sleep(1)
        self.shutdown()

    def update_cloud_metric(self):
        for cached_instance in self.cloud_cache.get_instance_list():
            # Instance deleted event
            if not self.cloud.has_instance(cached_instance.name):
                self.cloud_cache.delete_instance(cached_instance.name)
                self.instance_event_list.append((self.on_instance_deleted_notification, cached_instance))

        for live_instance in self.cloud.get_instance_list():
            # Instance created event
            if not self.cloud_cache.has_instance(live_instance.name):
                self.cloud_cache.add_instance(Instance(live_instance.name))
                self.instance_event_list.append((self.on_instance_created_notification, live_instance))

            # Load instance and zone previous state from cache
            cached_instance, cached_zone = self.get_cached_cloud(live_instance.name, live_instance.zone)
            live_instance.flag, live_instance.uptime_hour = cached_instance.flag, cached_instance.uptime_hour

            # Instance started event
            if cached_instance.status != GCE_STATUS_RUNNING and live_instance.status == GCE_STATUS_RUNNING:
                live_instance = self.update_started_instance_metric(live_instance)
            # Instance running event
            elif cached_instance.status == GCE_STATUS_RUNNING and live_instance.status == GCE_STATUS_RUNNING:
                cached_zone, live_instance = self.update_running_instance_metric(cached_zone, live_instance)
            # Instance terminated event
            elif cached_instance.status == GCE_STATUS_RUNNING and live_instance.status != GCE_STATUS_RUNNING:
                cached_zone, live_instance = self.update_terminated_instance_metric(cached_instance, cached_zone, live_instance)

            self.cloud_cache.update_instance(live_instance)
            self.cloud_cache.update_zone(cached_zone)

    def update_running_instance_metric(self, cached_zone, live_instance):
        # Update instance uptime_hour, zone total_uptime_hour and instance maturity status
        live_instance.uptime_hour += HOUR_PER_SECOND
        cached_zone.total_uptime_hour += HOUR_PER_SECOND
        live_instance.flag = INSTANCE_FLAG_MATURED if self.instance_matured(live_instance) else live_instance.flag

        # Trigger stop if instance is non-preemptible and matured, else continue running
        non_preemptible_matured = (not live_instance.preemptible and live_instance.flag == INSTANCE_FLAG_MATURED)
        target_event = self.stop_instance if non_preemptible_matured else self.on_instance_running_notification
        params = (live_instance.zone, live_instance.name) if non_preemptible_matured else live_instance
        self.instance_event_list.append((target_event, params))

        return cached_zone, live_instance

    def update_started_instance_metric(self, live_instance):
        # Reset instance uptime_hour when it is started
        live_instance.uptime_hour = 0
        self.instance_event_list.append((self.on_instance_started_notification, live_instance))

        return live_instance

    def update_terminated_instance_metric(self, cached_instance, cached_zone, live_instance):
        # Increment zone total termination count if instance gets terminated before maturity
        cached_zone.total_termination_count += 1 if live_instance.flag != INSTANCE_FLAG_MATURED else 0

        # Update cached instance with current instance status to reflect correctly in instance list
        cached_instance.status = live_instance.status
        self.cloud_cache.update_instance(cached_instance)

        # Trigger notification synchronously to show flag before update and trigger actual event with threaded execution
        live_instance_copy = deepcopy(live_instance)
        self.on_instance_terminated_notification(live_instance_copy)
        self.instance_event_list.append((self.on_instance_terminated, live_instance_copy))

        # Update to proper flag after an instance termination
        pe_instance_flag = INSTANCE_FLAG_RECYCLED if live_instance.flag == INSTANCE_FLAG_NEW else INSTANCE_FLAG_NEW
        live_instance.flag = pe_instance_flag if live_instance.preemptible else INSTANCE_FLAG_NEW

        return cached_zone, live_instance

    def validate_rules(self):
        if self.config.MIN_INSTANCE_COUNT < self.config.MIN_ZONE_SPREAD_COUNT:
            self.logger.error(ERR_INSTANCE_LESSER_THAN_ZONE_SPREAD)
            return False
        elif len(self.config.ZONE_LIST) < self.config.MIN_ZONE_SPREAD_COUNT:
            self.logger.error(ERR_ZONES_LESSER_THAN_ZONE_SPREAD)
            return False
        else:
            return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print USAGE_MESSAGE
    else:
        try:
            def signal_handler(signal, frame):
                gcem.shutdown(SHUTDOWN_MESSAGE)

            signal.signal(signal.SIGHUP, signal_handler)
            gcem = GCE_Manager(sys.argv[1])
            gcem.start()
        except KeyboardInterrupt:
            gcem.shutdown('Exiting...')
