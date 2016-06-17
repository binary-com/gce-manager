# Use machine_type as key, (npe_pricing, pe_pricing) as value
GCE_PRICING_TABLE = {}
GCE_PRICING_TABLE['f1-micro']       = (0.006, 0.005)
GCE_PRICING_TABLE['g1-small']       = (0.021, 0.010)
GCE_PRICING_TABLE['n1-standard-1']  = (0.038, 0.015)
GCE_PRICING_TABLE['n1-standard-2']  = (0.076, 0.030)
GCE_PRICING_TABLE['n1-standard-4']  = (0.152, 0.060)
GCE_PRICING_TABLE['n1-standard-8']  = (0.304, 0.120)
GCE_PRICING_TABLE['n1-standard-16'] = (0.608, 0.240)
GCE_PRICING_TABLE['n1-standard-32'] = (1.216, 0.480)
GCE_PRICING_TABLE['n1-highmem-2']   = (0.096, 0.035)
GCE_PRICING_TABLE['n1-highmem-4']   = (0.192, 0.070)
GCE_PRICING_TABLE['n1-highmem-8']   = (0.384, 0.140)
GCE_PRICING_TABLE['n1-highmem-16']  = (0.768, 0.280)
GCE_PRICING_TABLE['n1-highmem-32']  = (1.536, 0.560)
GCE_PRICING_TABLE['n1-highcpu-2']   = (0.058, 0.020)
GCE_PRICING_TABLE['n1-highcpu-4']   = (0.116, 0.040)
GCE_PRICING_TABLE['n1-highcpu-8']   = (0.232, 0.080)
GCE_PRICING_TABLE['n1-highcpu-16']  = (0.464, 0.160)
GCE_PRICING_TABLE['n1-highcpu-32']  = (0.928, 0.320)

API_FAILURE_MESSAGE     = '%s() failed: %s'
API_MAX_RETRY_NESSAGE   = '%s() max. retry exceeded after %s call(s). Reason: %s'
API_RETRY_MESSAGE       = '%s() failed: %s. Retrying...'
API_POLLING_INTERVAL    = 2
API_TYPE                = 'compute'
API_VERSION             = 'v1'

GCE_PREEMPTIBLE         = 'PE'
GCE_NON_PREEMPTIBLE     = 'NPE'

GCE_STATUS_PROVISIONING = 'PROVISIONING'
GCE_STATUS_STAGING      = 'STAGING'
GCE_STATUS_RUNNING      = 'RUNNING'
GCE_STATUS_STOPPING     = 'STOPPING'
GCE_STATUS_TERMINATED   = 'TERMINATED'

INSTANCE_FLAG_NEW       = 'NEW'
INSTANCE_FLAG_MATURED   = 'MATURED'
INSTANCE_FLAG_RECYCLED  = 'RECYCLED'

INDEX_INSTANCE_COUNT    = 0
INDEX_ZONE_NAME         = 1
INDEX_TERMINATION_RATE  = 2
INDEX_UPTIME_HOUR       = 3

ALL_ZONE                = True
PE_AVAILABLE_ZONE_ONLY  = False
PREEMPTIBLE             = True
NON_PREEMPTIBLE         = False

INSTANCE_MATURITY_HOUR  = 23
LOGGER_MAX_LINE_BUFFER  = 500
MAX_API_RETRY_COUNT     = 2
PRETTY_PRINT_INDENT     = 4
PRETTY_PRINT_WIDTH      = 80
HOUR_PER_SECOND         = (float(1) / 3600)
REPORT_LOG_COUNT        = 10
UPTIME_DECIMAL          = 5

CURRENT_PROCESS         = '/proc/self'
DEFAULT_EMAIL_FOOTER    = 'For more details, go to https://github.com/binary-com/gce-manager'
DEFAULT_EMAIL_SUBJECT   = 'Report of GCE instance changes'
DEFAULT_EMAIL_TAG       = '[GCE-MANAGER]'
DEFAULT_LOGGER_NAME     = 'gce_manager'
ERROR_THREAD_CRASHED    = 'Thread is crashed in GCE-MANAGER!'
HTML_LINE_BREAK_TAG     = '<br />'

MESSAGE_CREATED         = '%s:%s@%s is created'
MESSAGE_DELETED         = '%s:%s@%s is deleted after %s hour(s)'
MESSAGE_RUNNING         = '%s:%s@%s is running for %s hour(s)'
MESSAGE_STARTED         = '%s:%s@%s is online'
MESSAGE_TERMINATED      = '%s:%s@%s is terminated after %s hour(s)'

MESSAGE_CONVERT_PE      = 'Converting %s:%s@%s to preemptible instance after %s hour(s)'
MESSAGE_CONVERT_NPE     = 'Converting %s:%s@%s to non-preemptible instance after %s hour(s)'
MESSAGE_RECYCLE         = 'Recycling %s:%s@%s after %s hour(s)'
MESSAGE_RELOCATE        = 'Relocating %s:%s@%s to a different zone after %s hour(s)'
MESSAGE_PE_HIGH_DEMAND  = 'Exceeded threshold of total zone(s) with high demand in preemptible instance'

LOG_RECORD_FORMAT       = '[%(asctime)s] %(levelname)s - %(message)s'
LOG_TIMESTAMP_FORMAT    = '%Y-%m-%d %H:%M:%S'
PICKLE_FILE_EXTENSION   = '.pkl'
PICKLE_FILE_PATH_FORMAT = '%s/.%s%s'

REPORT_TEMPLATE         = '%s##Estimated Cost/Savings#%s##Zone(s) Configured#%s##Instance List#%s##GCE Manager Configuration#%s##%s'.replace('#', HTML_LINE_BREAK_TAG)
SHUTDOWN_MESSAGE        = 'Received SIGHUP signal for graceful shutdown. Exiting...'
STARTUP_MESSAGE         = 'Instance monitoring started for project \'%s\''
USAGE_MESSAGE           = 'Usage: gce_manager.py <config_file.yml>'

SLACKBOT_CMD_HELP       = 'help'
SLACKBOT_CMD_CONFIG     = 'show config'
SLACKBOT_CMD_LI         = 'show instance list'
SLACKBOT_CMD_LZ         = 'show zone list'
SLACKBOT_CMD_SAVINGS    = 'show savings'

SLACKBOT_EMOJI          = ':snowman:'
SLACKBOT_ERR_CONNECT    = 'Connection to Slack failed, invalid token?'
SLACKBOT_MSG_ACK        = '@%s Here\'s the information that you\'ve requested'
SLACKBOT_MSG_COST_NOTE  = 'Note: Savings are calculated based on pricing of (non-preemptible usage - preemptible usage)'
SLACKBOT_MSG_HELP       = '```Commands available:\n1. show config\n2. show instance list\n3. show savings\n4. show zone list\n5. help\n\n%s```' % DEFAULT_EMAIL_FOOTER
SLACKBOT_MSG_UNAUTH     = 'Nice try @%s but I\'m not authorized to serve your request :hand:'
SLACKBOT_MSG_UNKNOWN    = 'I\'m sorry @%s. I don\'t understand your request. Type @%s help to see available commands'
SLACKBOT_USERNAME       = 'gcebot'

TABLE_TITLE_COST        = ['Usage Type', 'Usage Hour', 'Cost/Hour', 'Total', 'Savings']
TABLE_TITLE_INSTANCE    = ['Node', 'Zone', 'Private IP', 'Type', 'Uptime Hour', 'Flag', 'Status']
TABLE_TITLE_ZONE        = ['Zone', 'Instance', 'Uptime Hour', 'Termination', 'Termination Rate']

ERR_INSTANCE_LESSER_THAN_ZONE_SPREAD = 'Minimum instance count must be greater or equal to the minimum number of zone(s) to be spread evenly'
ERR_ZONES_LESSER_THAN_ZONE_SPREAD = 'Minimum zone count must be greater or equal to the minimum number of zone(s) to be spread evenly'
