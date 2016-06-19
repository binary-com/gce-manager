#!/usr/bin/python

import signal
import socket
import sys
import threading
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
from lib.slackbot import *
from lib.util import *
from lib.HTML import *

class GCE_Manager:
    def __init__(self, config_file):
        self.abort_all = False
        self.email_queue = []
        self.instance_event_list = []
        self.instance_recovering = 0
        self.logviewer = logviewer()
        self.logviewer.hook_logger(DEFAULT_LOGGER_NAME)

        self.config = Config(config_file)
        self.slackbot = Slackbot(self.config)
        self.engine = GAPI(self.config, self.slackbot)
        self.util = Util(DEFAULT_LOGGER_NAME)

        all_instance = self.engine.get_all_instance(self.config.ZONE_LIST)
        self.cloud, self.cloud_cache = Cloud(all_instance), self.load_cached_cloud()
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

    def get_config_summary_table(self, html=False):
        config_record = []

        for key, value in self.config.get_raw_string_list():
            if key == 'GCE_SLACKBOT_API_TOKEN':
                config_record.append([key, len(value) * '*'])
            else:
                config_record.append([key, str(value)])

        return str(table(config_record)) if html else config_record

    def get_cooldown_time(self, start_time, max_cooldown=1):
        elapsed_time = (datetime.utcnow() - start_time).total_seconds()
        cooldown_time = 0 if elapsed_time > max_cooldown else (max_cooldown - elapsed_time)
        return cooldown_time

    def get_cost_summary_table(self, html=False):
        cost_record = [TABLE_TITLE_COST]
        npe_hour, pe_hour = 0, 0

        for zone_name in self.config.ZONE_LIST:
            cached_zone = self.cloud_cache.get_zone(zone_name)
            npe_hour += cached_zone.npe_uptime_hour
            pe_hour += cached_zone.pe_uptime_hour

        npe_pricing, pe_pricing = GCE_PRICING_TABLE[self.config.MACHINE_TYPE]
        npe_total, pe_total = npe_pricing * npe_hour, pe_pricing * pe_hour
        savings = (npe_pricing * pe_hour) - (pe_pricing * pe_hour)

        cost_record.append([GCE_PREEMPTIBLE, str(pe_hour), '$%s' % pe_pricing, '$%s' % pe_total, '$%s' % savings])
        cost_record.append([GCE_NON_PREEMPTIBLE, str(npe_hour), '$%s' % npe_pricing, '$%s' % npe_total, '$%s' % 0])
        cost_record.append(['All', str(pe_hour + npe_hour), '', '$%s' % (pe_total + npe_total), '$%s' % savings])

        return str(table(cost_record)) if html else cost_record

    def get_event_message_param(self, instance, include_uptime_hour=False):
        instance_type = GCE_PREEMPTIBLE if instance.preemptible else GCE_NON_PREEMPTIBLE
        if include_uptime_hour:
            return (instance_type, instance.name, instance.zone, round(instance.uptime_hour, UPTIME_DECIMAL))
        else:
            return (instance_type, instance.name, instance.zone)

    def get_html_summary_report(self):
        log_buffer = self.logviewer.get_log_buffer(REPORT_LOG_COUNT)
        params = (  HTML_LINE_BREAK_TAG.join(log_buffer),
                    self.get_cost_summary_table(True),
                    self.get_zone_summary_table(True),
                    self.get_instance_summary_table(True),
                    self.get_config_summary_table(True),
                    DEFAULT_EMAIL_FOOTER   )

        return REPORT_TEMPLATE % params

    def get_instance_summary_table(self, html=False):
        instance_record = [TABLE_TITLE_INSTANCE]

        for instance in self.cloud_cache.get_instance_list():
            node = instance.name
            for prefix in self.config.INSTANCE_NAME_PREFIX_LIST:
                node = node.replace(prefix, '')

            instance_record.append([
                node,
                instance.zone,
                instance.ip,
                GCE_PREEMPTIBLE if instance.preemptible else GCE_NON_PREEMPTIBLE,
                str(round(instance.uptime_hour, UPTIME_DECIMAL)),
                instance.flag,
                instance.status.lower()])

        return str(table(instance_record)) if html else instance_record

    def get_sorted_zone_table(self, sortkey_index, include_low_preemptible_supply_zone):
        unsorted_zone_table, sorted_zone_table = [], []

        # Prepare a list of tuples with [instance_count, zone_name]
        for zone in self.cloud_cache.get_zone_list():
            if not self.low_preemptible_supply(zone.name) or include_low_preemptible_supply_zone:
                unsorted_zone_table.append([zone.instance_count, zone.name, zone.get_termination_rate(), zone.get_total_uptime_hour()])

        def get_key(item):
            return item[sortkey_index]

        # Prepare a list of tuples with [zone_name, instance_count, termination_rate] sorted by instance_count
        for instance_count, zone_name, termination_rate, zone_total_uptime_hour in sorted(unsorted_zone_table, key=get_key):
            sorted_zone_table.append((zone_name, instance_count, termination_rate, zone_total_uptime_hour))

        return sorted_zone_table

    def get_unstable_zone_count(self):
        unstable_zone_count = 0

        for zone_info in self.get_zone_info_list():
            zone_name, instance_count, zone_total_uptime_hour, termination_count, termination_rate = zone_info
            unstable_zone_count += 1 if (termination_rate > self.termination_rate_threshold) else 0

        return unstable_zone_count

    def get_zone_candidate(self, instance):
        zone_candidate_table, unique_instance_count_list = [], []
        _zone_name, _instance_count, _termination_rate = None, 0, 0
        instance_count_sorted_zone_table = self.get_sorted_zone_table(INDEX_INSTANCE_COUNT, PE_AVAILABLE_ZONE_ONLY)

        # Pick zone(s) with lower instance count to prioritize zone spread balance followed by termination rate
        for zone_name, instance_count, termination_rate, zone_total_uptime_hour in instance_count_sorted_zone_table:
            # Pick zone(s) with unique instance count up to the number of minimum zone spread
            if len(unique_instance_count_list) < self.config.MIN_ZONE_SPREAD_COUNT:
                zone_candidate_table.append([zone_name, instance_count, termination_rate])
                if not instance_count in unique_instance_count_list:
                    unique_instance_count_list.append(instance_count)

        # Pick the zone with lowest termination rate from zone_candidate_table
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
        zone_info_list = []

        for zone_name in self.config.ZONE_LIST:
            cached_zone = self.cloud_cache.get_zone(zone_name)
            zone_info_list.append(
                (zone_name,
                self.get_zone_instance_count(zone_name),
                cached_zone.get_total_uptime_hour(),
                cached_zone.total_termination_count,
                cached_zone.get_termination_rate()))

        return zone_info_list

    def get_zone_instance_count(self, zone_name):
        instance_count = 0

        for instance in self.cloud.get_instance_list():
            if instance.zone == zone_name:
                instance_count += 1

        return instance_count

    def get_zone_summary_table(self, html=False):
        zone_configured = [TABLE_TITLE_ZONE]

        for zone_info in self.get_zone_info_list():
            zone_name, instance_count, zone_total_uptime_hour, termination_count, termination_rate = zone_info
            zone_configured.append([
                zone_name,
                str(instance_count),
                str(round(zone_total_uptime_hour, UPTIME_DECIMAL)),
                str(termination_count),
                str(termination_rate)])

        return str(table(zone_configured)) if html else zone_configured

    def instance_event_engine(self):
        while not self.abort_all:
            start_time = datetime.utcnow()
            try:
                self.instance_event_generator()
                self.update_cloud_metric()
                self.flush_cloud_cache()
                threading.Thread(target=self.flush_email_queue).start()
            except Exception, exception:
                content = API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception)
                self.email_queue.append((content, self.config.EMAIL_RECIPIENT_LIST, ERROR_THREAD_CRASHED))
            finally:
                time.sleep(self.get_cooldown_time(start_time))

    def instance_event_generator(self):
        while len(self.instance_event_list) > 0:
            _target, _instance = self.instance_event_list.pop(0)
            threading.Thread(target=_target, args=(_instance,)).start()

    def instance_matured(self, instance):
        pe_matured = (instance.flag != INSTANCE_FLAG_MATURED and instance.uptime_hour >= INSTANCE_MATURITY_HOUR)
        npe_matured = instance.uptime_hour > self.config.NON_PREEMPTIBLE_INSTANCE_MIN_ALIVE_HOUR
        return pe_matured if instance.preemptible else npe_matured

    # TODO: FUTURE ENHANCEMENT
    # Auto-create instance from snapshot if instance deleted and instance count < self.config.MIN_INSTANCE_COUNT
    # Creation of instance in respective zone should observe self.config.MIN_ZONE_SPREAD_COUNT
    def instance_restructure_engine(self):
        while not self.abort_all:
            start_time = datetime.utcnow()
            # IMPLEMENTATION HERE
            time.sleep(self.get_cooldown_time(start_time))

    def instance_status_updater(self):
        while not self.abort_all:
            start_time = datetime.utcnow()
            try:
                self.cloud = Cloud(self.engine.get_all_instance(self.config.ZONE_LIST))
            except Exception, exception:
                content = API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception)
                self.email_queue.append((content, self.config.EMAIL_RECIPIENT_LIST, ERROR_THREAD_CRASHED))
            finally:
                time.sleep(self.get_cooldown_time(start_time, max_cooldown=API_POLLING_INTERVAL))

    def load_cached_cloud(self):
        cloud_cache = self.util.load_object(self.config.PROJECT_ID)
        cloud_cache = Cloud() if cloud_cache == None else cloud_cache

        # Add any newly configured zone into local cache
        for zone_name in self.config.ZONE_LIST:
            if not cloud_cache.has_zone(zone_name):
                cloud_cache.add_zone(Zone(zone_name))
        return cloud_cache

    def log(self, message, send_email=False, email=None):
        self.util.logger.info(message)

        if len(self.config.SLACKBOT_API_TOKEN.strip()) > 0:
            self.slackbot.send_message(self.config.SLACKBOT_LOGGING_CHANNEL, message)

        if send_email:
            recipient = self.config.EMAIL_RECIPIENT_LIST if email == None else email
            self.email_queue.append((self.get_html_summary_report(), recipient, message))

    def low_preemptible_supply(self, zone_name=None):
        if zone_name != None:
            termination_rate = self.cloud_cache.get_zone(zone_name).get_termination_rate()
            return termination_rate > self.termination_rate_threshold
        else:
            # Get zone(s) with available preemptible instance supply sorted by termination rate
            termination_rate_sorted_zone_table = self.get_sorted_zone_table(INDEX_TERMINATION_RATE, PE_AVAILABLE_ZONE_ONLY)
            available_zone_count = len(termination_rate_sorted_zone_table)
            min_zone_spread_count_satisfied = (available_zone_count >= self.config.MIN_ZONE_SPREAD_COUNT)
            stable_zone_available = (available_zone_count > 0) and min_zone_spread_count_satisfied
            overall_pe_supply_low = self.get_unstable_zone_count() > self.unstable_zone_threshold

            # Return overall zone count availability status if there's stable zone available
            return overall_pe_supply_low if stable_zone_available else True

    def on_instance_created_notification(self, created_instance):
        self.log(MESSAGE_CREATED % self.get_event_message_param(created_instance))

    def on_instance_deleted_notification(self, deleted_instance):
        self.log(MESSAGE_DELETED % self.get_event_message_param(deleted_instance, True))

    def on_instance_running_notification(self, running_instance):
        # FOR DEBUGGING USE ONLY
        # self.log(MESSAGE_RUNNING % self.get_event_message_param(running_instance, True))
        return

    def on_instance_started_notification(self, started_instance):
        self.log(MESSAGE_STARTED % self.get_event_message_param(started_instance), send_email=True)

    def on_instance_terminated_notification(self, terminated_instance):
        params = self.get_event_message_param(terminated_instance, True)
        self.log(MESSAGE_TERMINATED % params, send_email=True)

        # Convert non-preemptible instance to preemptible instance
        if not terminated_instance.preemptible:
            self.log(MESSAGE_CONVERT_PE % params, send_email=True)
        else:
            # Strategy 1: Recycling instance
            if terminated_instance.flag != INSTANCE_FLAG_RECYCLED:
                self.log(MESSAGE_RECYCLE % params, send_email=True)
            else:
                if not self.low_preemptible_supply():
                    zone_candidate = self.get_zone_candidate(terminated_instance)

                    # Relocate instance only if different zone
                    if zone_candidate != terminated_instance.zone:
                        # Strategy 2: Relocate instance to different zone
                        self.log(MESSAGE_RELOCATE % params, send_email=True)
                    else:
                        # Strategy 3: Convert instance to non-preemptible instance
                        self.log(MESSAGE_PE_HIGH_DEMAND)
                        self.log(MESSAGE_CONVERT_NPE % params, send_email=True)
                else:
                    # Strategy 3: Convert instance to non-preemptible instance
                    self.log(MESSAGE_PE_HIGH_DEMAND)
                    self.log(MESSAGE_CONVERT_NPE % params, send_email=True)

        self.instance_event_list.append((self.process_terminated_instance, terminated_instance))

    # TODO: Check and don't recreate instance if it is deleted on purpose - for instance_restructure_engine()
    def process_terminated_instance(self, terminated_instance):
        self.instance_recovering += 1

        # Wait until terminated instance is fully stopped
        while self.cloud.get_instance(terminated_instance.name).status != GCE_STATUS_TERMINATED:
            time.sleep(1)

        # Convert non-preemptible instance to preemptible instance
        if not terminated_instance.preemptible:
            self.recover_instance(terminated_instance, PREEMPTIBLE, terminated_instance.zone)
        else:
            # Strategy 1: Recycling instance
            if terminated_instance.flag != INSTANCE_FLAG_RECYCLED:
                self.recover_instance(terminated_instance, PREEMPTIBLE, terminated_instance.zone)
            else:
                if not self.low_preemptible_supply():
                    # Strategy 2: Relocate instance only if zone candidate is in different zone
                    # Otherwise recreate it as non-preemptible instance in the same zone
                    zone_candidate = self.get_zone_candidate(terminated_instance)
                    preemptibility = PREEMPTIBLE if (zone_candidate != terminated_instance.zone) else NON_PREEMPTIBLE
                    self.recover_instance(terminated_instance, preemptibility, zone_candidate)
                else:
                    # Pick zone with the least instance count which is the first entry
                    instance_count_sorted_zone_table = self.get_sorted_zone_table(INDEX_INSTANCE_COUNT, PE_AVAILABLE_ZONE_ONLY)
                    zone_name, instance_count, termination_rate, zone_total_uptime_hour = instance_count_sorted_zone_table[0]

                    # Strategy 3: Convert instance to non-preemptible instance
                    self.recover_instance(terminated_instance, NON_PREEMPTIBLE, zone_name)

        self.instance_recovering -= 1

    def recover_instance(self, instance, preemptible, zone_name):
        # Update instance count when source and destination zones are different
        if instance.zone != zone_name:
            source_zone = self.cloud_cache.get_zone(instance.zone)
            destination_zone = self.cloud_cache.get_zone(zone_name)
            source_zone.instance_count -= 1
            destination_zone.instance_count += 1
            self.cloud_cache.update_zone(source_zone)
            self.cloud_cache.update_zone(destination_zone)

        # Start back the same instance if same preemptibility type and zone
        if instance.preemptible == preemptible and instance.zone == zone_name:
            self.engine.start_instance(zone_name, instance.name)
        else:
            # The zone and preemptible option cannot be changed after instance creation, hence recreate instance
            response = self.engine.delete_instance(instance.zone, instance.name)
            self.engine.wait_for_operation(instance.zone, response)
            self.engine.create_instance_from_snapshot(zone_name, instance.name, preemptible)

    def shutdown(self, message=None):
        if not self.abort_all:
            if message is not None:
                self.log(message)
            self.abort_all = True
            self.engine.shutdown()
            self.slackbot.shutdown()

    def start(self):
        self.update_cloud_metric()
        self.update_zone_instance_count()
        self.log(STARTUP_MESSAGE % self.config.PROJECT_ID, send_email=True)

        if self.validate_rules():
            # Start polling instances status in all zones for any changes
            threading.Thread(target=self.instance_status_updater).start()

            # Start generating instances event such as creation, deletion, startup and termination
            threading.Thread(target=self.instance_event_engine).start()

            # Start waiting for jobs to increase/decrease instances if required
            threading.Thread(target=self.instance_restructure_engine).start()

            # Start Slackbot that allow instance status query
            threading.Thread(target=self.slackbot.start_bot).start()

            # Start updating summary tables for Slackbot retrieval
            threading.Thread(target=self.update_slackbot_summary_table_cache).start()

            # Exit whenever shutdown signal triggered
            while not self.abort_all: time.sleep(1)
        self.shutdown()

    def update_cloud_cache(self, instance, zone):
        self.cloud_cache.update_instance(instance)
        self.cloud_cache.update_zone(zone)

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

            self.update_cloud_cache(live_instance, cached_zone)

    def update_running_instance_metric(self, cached_zone, live_instance):
        # Update instance uptime_hour and zone uptime_hour
        live_instance.uptime_hour += HOUR_PER_SECOND
        cached_zone.pe_uptime_hour += HOUR_PER_SECOND if live_instance.preemptible else 0
        cached_zone.npe_uptime_hour += HOUR_PER_SECOND if not live_instance.preemptible else 0

        # Trigger stop if instance is non-preemptible and matured, else continue running
        live_instance.flag = INSTANCE_FLAG_MATURED if self.instance_matured(live_instance) else live_instance.flag
        non_preemptible_matured = (not live_instance.preemptible and live_instance.flag == INSTANCE_FLAG_MATURED)

        if non_preemptible_matured:
            threading.Thread(target=self.engine.stop_instance, args=(live_instance.zone, live_instance.name,)).start()
        else:
            self.instance_event_list.append((self.on_instance_running_notification, live_instance))

        return cached_zone, live_instance

    def update_slackbot_summary_table_cache(self):
        while not self.abort_all:
            start_time = datetime.utcnow()
            try:
                self.slackbot.config_table = self.get_config_summary_table()
                self.slackbot.cost_table = self.get_cost_summary_table()
                self.slackbot.instance_table = self.get_instance_summary_table()
                self.slackbot.zone_table = self.get_zone_summary_table()
            except Exception, exception:
                content = API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception)
                self.email_queue.append((content, self.config.EMAIL_RECIPIENT_LIST, ERROR_THREAD_CRASHED))
            finally:
                time.sleep(self.get_cooldown_time(start_time))

    def update_started_instance_metric(self, live_instance):
        # Reset instance uptime_hour when it is started
        live_instance.uptime_hour = 0
        self.instance_event_list.append((self.on_instance_started_notification, live_instance))

        return live_instance

    def update_terminated_instance_metric(self, cached_instance, cached_zone, live_instance):
        # Increment zone total termination count if instance gets terminated before maturity
        cached_zone.total_termination_count += (1 if live_instance.flag != INSTANCE_FLAG_MATURED else 0)

        # Update cached instance with current instance status to reflect correctly in instance list
        cached_instance.status = live_instance.status

        # Update cloud cache to ensure report reflects current instance status and zone termination rate
        self.update_cloud_cache(cached_instance, cached_zone)

        # Trigger notification synchronously to show flag before update
        self.on_instance_terminated_notification(deepcopy(live_instance))

        # Update to proper flag after an instance termination
        pe_instance_flag = INSTANCE_FLAG_RECYCLED if live_instance.flag == INSTANCE_FLAG_NEW else INSTANCE_FLAG_NEW
        live_instance.flag = pe_instance_flag if live_instance.preemptible else INSTANCE_FLAG_NEW

        return cached_zone, live_instance

    def update_zone_instance_count(self):
        unique_zone_list = []

        for instance in self.cloud.get_instance_list():
            cached_zone = self.cloud_cache.get_zone(instance.zone)

            if cached_zone.name not in unique_zone_list:
                cached_zone.instance_count = 1
                unique_zone_list.append(cached_zone.name)
            else:
                cached_zone.instance_count += 1

            self.cloud_cache.update_zone(cached_zone)

    def validate_rules(self):
        if self.config.MIN_INSTANCE_COUNT < self.config.MIN_ZONE_SPREAD_COUNT:
            self.log(ERR_INSTANCE_LESSER_THAN_ZONE_SPREAD)
            return False
        elif len(self.config.ZONE_LIST) < self.config.MIN_ZONE_SPREAD_COUNT:
            self.log(ERR_ZONES_LESSER_THAN_ZONE_SPREAD)
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
