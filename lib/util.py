#!/usr/bin/python

import getpass
import logging
import os
import pickle
import platform
import pwd
import smtplib
import socket
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# External modules
from constant import *

class Util:
    def __init__(self, logger_name='util'):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(fmt=LOG_RECORD_FORMAT, datefmt=LOG_TIMESTAMP_FORMAT))
        self.logger = logging.getLogger(logger_name)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

    def _get_current_user_home(self):
        if platform.system() == 'Linux':
            uid = os.stat(CURRENT_PROCESS).st_uid
            user_info = pwd.getpwuid(uid)
            name, passwd, uid, gid, gecos, home, shell = user_info
            return home
        else:
            # For local development/testing under Mac/Darwin
            return '.'

    def load_object(self, name):
        try:
            abs_fname = PICKLE_FILE_PATH_FORMAT % (self._get_current_user_home(), name, PICKLE_FILE_EXTENSION)
            if os.path.isfile(abs_fname):
                with open(abs_fname, 'rb') as input:
                    return pickle.load(input)
            else:
                return None
        except Exception, exception:
            self.logger.info(API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception))
            return None

    def save_object(self, name, _object):
        try:
            # Save to a temporary path then move when pickle done to achieve atomic write
            tmp_file = '/tmp/.%s%s' % (name, PICKLE_FILE_EXTENSION)
            abs_fname = PICKLE_FILE_PATH_FORMAT % (self._get_current_user_home(), name, PICKLE_FILE_EXTENSION)
            with open(tmp_file, 'wb') as output:
                pickle.dump(_object, output, pickle.HIGHEST_PROTOCOL)
            os.rename(tmp_file, abs_fname)
        except Exception, exception:
            self.logger.info(API_FAILURE_MESSAGE % (sys._getframe().f_code.co_name, exception))

    def send_email(self, html, recipient_list, subject=None, retry_count=MAX_API_RETRY_COUNT):
        try:
            if len([x for x in recipient_list if x != '']) > 0:
                msg = MIMEMultipart()
                msg['Subject'] = '%s %s' % (DEFAULT_EMAIL_TAG, subject if subject else DEFAULT_EMAIL_SUBJECT)
                msg['From'] = '%s@%s' % (getpass.getuser(), socket.getfqdn())
                msg['To'] = ", ".join(recipient_list)
                msg.attach(MIMEText(html, 'html'))

                smtp = smtplib.SMTP(socket.getfqdn())
                smtp.sendmail(msg['From'], recipient_list, msg.as_string())
                smtp.quit()
        except Exception, exception:
            if retry_count > 0:
                self.logger.info(API_RETRY_MESSAGE % (sys._getframe().f_code.co_name, exception))
                return self.send_email(html, recipient_list, subject, (retry_count - 1))
            else:
                self.logger.info(API_MAX_RETRY_NESSAGE % (sys._getframe().f_code.co_name, MAX_API_RETRY_COUNT, exception))
