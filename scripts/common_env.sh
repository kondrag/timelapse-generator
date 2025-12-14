#!/usr/bin/bash

# Common environment variables for timelapse scripts

# Logging
LOGFILE=/tmp/timelapse.log

# Directories
TIMELAPSE_DIR=/var/local/timelapse
WEEWX_DIR=/tmp/weewx
WEEWX_TIMELAPSE_DIR=${WEEWX_DIR}/aurora

# Date variables
TODAY=$(date +%Y%m%d)
DAY=$(date +%A)
ARCHIVE_DIR=${TIMELAPSE_DIR}/${TODAY}

# Path settings
export PATH=$PATH:/bin:/usr/bin:/sbin:/usr/sbin
