import logging
from constant import *

class logviewer(logging.Handler):
    def __init__(self, *args, **kwargs):
        # Suppress SNIMissingWarning warning when running in Python 2.7
        logging.captureWarnings(True)

        logging.Handler.__init__(self, *args)
        self.log_buffer = []
        self.setFormatter(logging.Formatter(fmt=LOG_RECORD_FORMAT, datefmt=LOG_TIMESTAMP_FORMAT))

    def emit(self, record):
        self.log_buffer.append(self.format(record))

        # Remove excess line in buffer from oldest record
        if len(self.log_buffer) > LOGGER_MAX_LINE_BUFFER:
            trim_count = len(self.log_buffer) - LOGGER_MAX_LINE_BUFFER
            del self.log_buffer[0:trim_count]

    def get_log_buffer(self, line=-1):
        if line < 0 or len(self.log_buffer) <= line:
            return self.log_buffer
        else:
            line_count = 0 - line
            return self.log_buffer[line_count:]

    def hook_logger(self, logger_name):
        self.logger_instance = logging.getLogger(logger_name)
        self.logger_instance.addHandler(self)
