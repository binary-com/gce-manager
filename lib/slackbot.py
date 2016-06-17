import signal
import sys
import time

from config import *
from constant import *
from datetime import datetime
from slackclient import SlackClient
from util import *

class Slackbot:
    def __init__(self, config_obj):
        self.abort_all = False
        self.bot_tag = None
        self.config = config_obj
        self.util = Util('slackbot')
        self.logger = self.util.logger
        self.sc = SlackClient(self.config.SLACKBOT_API_TOKEN)
        self.config_table, self.cost_table, self.instance_table, self.zone_table = [], [], [], []

    def format_slack_table(self, table, make_single_column=False):
        single_column_table = ''

        for row in table:
            _row, first_record = '', True
            for record in row:
                if first_record:
                    _row += '*%s*' % record + '\n'
                    first_record = False
                else:
                    _row += '>%s' % record + '\n'
            single_column_table += _row + '\n'

        multi_column_table = '''```%s```''' % self.util.get_ascii_table(table)
        return single_column_table if make_single_column else multi_column_table

    def get_channel_name(self, channel):
        if channel != None:
            channel_info = self.sc.api_call('channels.info', channel=channel)
            channel_name = channel_info.get('channel')['name'] if channel_info.get('channel') != None else None
            return '#%s' % channel_name if channel_name != None else None
        else:
            return None

    def get_current_user_info(self):
        return self.sc.api_call('auth.test', token=self.config.SLACKBOT_API_TOKEN)

    def get_message(self, payload):
        user_name = self.get_user_name(payload.get('user'))
        channel_name = self.get_channel_name(payload.get('channel'))
        timestamp = self.get_timestamp(float(payload.get('ts') if payload.get('ts') != None else 0))
        text = payload.get('text')
        valid_message = channel_name != None and text != None and user_name != None
        return (channel_name, text, timestamp, user_name) if valid_message else None

    def get_timestamp(self, timestamp):
        if timestamp > 0:
            return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')
        else:
            return None

    def get_user_name(self, user_id):
        if user_id != None:
            user_info = self.sc.api_call("users.info", user=user_id)
            return user_info.get('user')['name'] if user_info.get('user') != None else None
        else:
            return None

    def process_command(self, channel_name, text, timestamp, caller_name):
        self.send_message(channel_name, SLACKBOT_MSG_ACK % caller_name)
        lowercase_text = text.lower()

        if 'help' in lowercase_text:
            self.send_message(channel_name, SLACKBOT_MSG_HELP)
        elif 'show config' in lowercase_text:
            self.send_message(channel_name, self.format_slack_table(self.config_table, True))
        elif 'show instance list' in lowercase_text:
            self.send_message(channel_name, self.format_slack_table(self.instance_table))
        elif 'show savings' in lowercase_text:
            self.send_message(channel_name, self.format_slack_table(self.cost_table))
        elif 'show zone list' in lowercase_text:
            self.send_message(channel_name, self.format_slack_table(self.zone_table))
        else:
            self.send_message(channel_name, SLACKBOT_MSG_UNKNOWN % (caller_name, SLACKBOT_USERNAME))

    def send_message(self, channel, message, username=SLACKBOT_USERNAME, icon_emoji=SLACKBOT_ICON_EMOJI):
        if message != None and len(message) > 0:
            self.sc.api_call("chat.postMessage", channel=channel, text=message, username=username, icon_emoji=icon_emoji)

    def start_bot(self):
        if self.sc.rtm_connect():
            try:
                self.bot_tag = '<@%s>' % self.get_current_user_info().get('user_id')
                self.channel_message_monitor()
            except Exception, exception:
                self.logger.info(API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception))
        else:
            self.logger.info(SLACKBOT_ERR_CONNECT)

    def channel_message_monitor(self):
        while not self.abort_all:
            buffer = self.sc.rtm_read()

            if len(buffer) > 0 and buffer[0]['type'] == 'message':
                message = self.get_message(buffer[0])

                if message != None:
                    channel_name, text, timestamp, user_name = message

                    if self.bot_tag not in text:
                        continue

                    if user_name in self.config.SLACKBOT_USER_LIST:
                        self.process_command(channel_name, text, timestamp, user_name)
                    else:
                        self.send_message(channel_name, SLACKBOT_MSG_UNAUTH % user_name)

            time.sleep(1)

    def shutdown(self, message=None):
        if not self.abort_all:
            if message is not None:
                self.logger.info(message)
            self.abort_all = True

if __name__ == "__main__":
    try:
        # Standalone mode for development/testing purposes
        slackbot = Slackbot(Config('../config.yml'))
        slackbot.start_bot()
    except KeyboardInterrupt:
        slackbot.shutdown('Exiting...')
