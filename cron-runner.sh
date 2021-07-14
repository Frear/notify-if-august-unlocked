#!/bin/bash

if [ $(ps xo args | egrep -c '^python -u \./notify-if-unlocked\.py') -ne 0 ]; then exit 0 ; fi

source ~/dev/2021-07-10-august-door-lock/august/bin/activate
cd ~/dev/2021-07-10-august-door-lock/j-src || exit 1
python -u ./notify-if-unlocked.py -c ./send-sns-notification.sh "$@"
