#!/bin/bash

# This is a quick and dirty way to effective daemonize the
# notify-if-unlocked.py program.
#
# It has been tested with the following cron entry:
#
# Start the august door lock scanner program as a daemon
# 0 * * * * dev/2021-07-10-august-door-lock/j-src/cron-runner.sh >> dev/2021-07-10-august-door-lock/j-src/cron-output 2>&1

if [ $(ps xo args | egrep -c '^python -u \./notify-if-unlocked\.py') -ne 0 ]; then exit 0 ; fi

source ~/dev/2021-07-10-august-door-lock/august/bin/activate
cd ~/dev/2021-07-10-august-door-lock/j-src || exit 1
python -u ./notify-if-unlocked.py -c ./send-sns-notification.sh "$@"
