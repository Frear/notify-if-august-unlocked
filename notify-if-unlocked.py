
# The August door lock is a good product with a decent app, except for one
# shortcoming. Because of the automation overriding natural human door locking
# behavior, it's easy to accidentally leave the door unlocked.
#
# August's apps have a shortcoming in this regard - they can auto-lock the
# door, but they don't have a setting to simply notify you the door is unlocked.
#
# This program sends a notification that the door has been left unlocked
# longer than a given threshold.
#
# This program runs in an endless loop, polling the status of the door lock.
# The first time it is run, it must be launched with --auth= so you can input
# your username and password to obtain an auth token.  On subsequent runs, it
# can run non-interactively.
#
# If the door is left unlocked, the notification command will be invoked.
# (And, for reasons explained in the source, the notification command cannot
# use escaping to prevent whitespace splitting.)
#
# By John Frear <software YouKnowTheDelimiter frear.com>
# July 11, 2021


# Requires:
# - Python (was developed on python 3.6.12)
# - py-august, from https://github.com/snjoetw/py-august


from august.api import Api 
from august.authenticator import Authenticator, AuthenticationState
from august.authenticator_common import ValidationResult
from august.lock import LockStatus, LockDoorStatus

#from august.util import update_lock_detail_from_activity, as_utc_from_local
#from august.activity import (
#    ACTIVITY_ACTION_STATES,
#    DoorbellMotionActivity,
#    DoorOperationActivity,
#    LockOperationActivity,
#)

from argparse import ArgumentParser
from getpass import getpass

# Setting umask so that, in the event we create a
# token file, it isn't left writable
from os import umask

import dateutil

# Doing this so we can call out to the aws cli aws
# because I don't want to code the aws boto3 libs into here now.
# Besides, calling out to an external command is more flexible anyway.
import subprocess

from pathlib import Path
from time import sleep
from datetime import datetime, timezone



# Some important program defaults are embedded in these parser options
# For ex, the Authenticator api call takes exactly two options for login_method
parser = ArgumentParser(description='Notify if the door is unlocked.')
parser.add_argument('-a','--auth',
                    dest='auth',
                    choices={'email', 'phone'},
                    help='Request uname & pw from stdin, auth, then exit, which is necessary if we need to re-auth')
parser.add_argument('-f','--cache-file',
                    dest='cache_file',
                    default=str(Path.home()) + "/.august-authtoken",
                    help='Path to the auth token')
parser.add_argument('-p','--polling-interval',
                    dest='polling_interval',
                    type=int,
                    default=293,
                    help='How often we check the lock status, in seconds')
parser.add_argument('-n','--notification-interval',
                    dest='notification_interval',
                    type=int,
                    default=900,
                    help='How long the door must be closed and unlocked before we send notification, in seconds')
# Note that, due to subprocess.run requiring discrete arguments and our use of
# split() to generate them, we cannot accept commands which have whitespace
# in their arguments. That is, if we are called with, for example:
#   --notification-command="aws sns publish --topic-arn arn:aws:sns:someregion:somearn:SmsEvents --message \"The door is unlocked\""
# then the above fails because split acts on whitespace and treats the
# quoted portion of message is treated as several distinct tokens.
# Therefore, make sure your command will be invoked correctly after splitting.
parser.add_argument('-c','--notification-command',
                    dest='notification_command',
                    default="echo Provide a notification command",
                    help='A command we\'ll run when it\'s time to notify. Note, quoted args are not supported.')
parser.add_argument('-v','--verbose',
                    dest='verbose',
                    action='store_true',
                    help='Print a message each time the locks are polled')

args = parser.parse_args()
print("Started with args", args)

# Parse the "args" param
# If "auth" was given, prompt the user for their credentials
uname = 'No username'
pw = 'No password'
if args.auth:
    authtype = args.auth
    if args.auth == 'phone':
        print("Enter phone number, starting with + and country code: ")
    else:
        print("Enter email address: ")
    uname = input()
    pw = getpass("Enter pw: ")
    #print("have uname [" + uname + "] and pw [" + pw + "]")
else:
    authtype = 'email'
# If --auth= wasn't supplied, args.auth = None


api = Api(timeout=60)
authenticator = Authenticator(api,
                              login_method=authtype,
                              username=uname,
                              password=pw,
                              access_token_cache_file=str(args.cache_file))

authentication = authenticator.authenticate()
state = authentication.state

if state == AuthenticationState.BAD_PASSWORD:
    if args.auth == None:
        print("Fatal: You MUST use the --auth argument and re-auth.")
    else:
        print("Fatal: Bad password.")
    exit(1)

# Send a validation code and allow the user many chances
# to enter the right one.
if state == AuthenticationState.REQUIRES_VALIDATION:
    # When we write our token cache file, keep the permissions private
    prev_umask = umask(0o077)
    authenticator.send_verification_code()
    print("Auth code sent.")
    validation_result = ValidationResult.INVALID_VERIFICATION_CODE
    while validation_result == ValidationResult.INVALID_VERIFICATION_CODE:
        print("Enter code:")
        code = input()
        #print("Using code [" + str(code) + "]")
        validation_result = authenticator.validate_verification_code(str(code))
    if validation_result != ValidationResult.VALIDATED:
        print("Fatal: Validation result was", ValidationResult)
        exit(1)
    authentication = authenticator.authenticate()
    state = authentication.state
    umask(prev_umask)

if state != AuthenticationState.AUTHENTICATED:
    print("Fatal: Not authenticated. Auth state is", state)
    exit(1)

# We only get here if we completed authentication
#print("Authenticated, state is", state)
if args.auth != None:
    # If authentication was requested and succeeded, exit
    # because this program required stdin for the --auth
    # flag but noramlly runs non-interactively.
    print("Auth successful - you no longer need to use the --auth arugmnet")
    exit(0)

# Print detailed lock status - get_lock_detail must be called by caller
def print_lock_detail(now, lockdetail):
    if lockdetail.bridge_is_online:
        lockdate = str(lockdetail.lock_status_datetime)
        doordate = str(lockdetail.door_state_datetime)
    else:
        lockdate = "unknown"
        doordate = "unknown"
    print(now,
          "Lock", lockdetail.device_name,
          "batt level", lockdetail.battery_level,
          "serial", lockdetail.serial_number,
          "firmware", lockdetail.firmware_version,
          "model", lockdetail.model,
          "doorsense", lockdetail.doorsense,
          "bridge", lockdetail.bridge_is_online,
          "lock status date", lockdate,
          "door status date", doordate)

locks = api.get_locks(authentication.access_token)
print("Using lock(s):", locks)
# prev_lock_state will store the results from get_lock_status
# and the time, and will only be updated when the lock
# status changes.
prev_lock_state = {}
skip_next_polling_delay = True
while True:
    if not skip_next_polling_delay:
        # No need to wait before making an api call if this is our
        # first pass.  But wait if this is an nth iteration.
        sleep(args.polling_interval)
    else:
        skip_next_polling_delay = False
    for lock in locks:
        now = datetime.now(timezone.utc).astimezone()
        if args.verbose:
            print(now, "checking status of", lock.device_name)
        lockstatus, doorstatus = api.get_lock_status(authentication.access_token, lock.device_id, True)
        if not lock in prev_lock_state:
            # If we haven't seen this lock before, simply save the
            # state observations and go back into the loop.
            prev_lock_state[lock] = {
                "statechange_time": now,
                "lockstatus": lockstatus,
                "doorstatus": doorstatus,
                "notified": False,
                "operable": lock.is_operable,
                "bugfix_query": False
            }
            print(now,
                  "Lock", lock.device_name,
                  "state is:",
                  "operable", lock.is_operable,
                  "Lock", lockstatus,
                  "Door", doorstatus)
            # Print extended detail the first time we see a lock
            lockdetail = api.get_lock_detail(authentication.access_token, lock.device_id)
            print_lock_detail(now, lockdetail)
            continue
        if ( lock.is_operable != prev_lock_state[lock]['operable'] ):
            print(now,
                  "lock operable state changed from",
                  prev_lock_state[lock]['operable'],
                  "->",
                  lock.is_operable)
            prev_lock_state[lock]['operable'] = lock.is_operable
        if not lock.is_operable:
            continue
        if ( lockstatus != prev_lock_state[lock]['lockstatus'] or
             doorstatus != prev_lock_state[lock]['doorstatus'] ):
            print(now,
                  "Lock", lock.device_name,
                  "state changed after",
                      (now - prev_lock_state[lock]['statechange_time']).total_seconds(),
                  "secs:",
                      prev_lock_state[lock]['lockstatus'],
                      "->",
                      lockstatus,
                  "and",
                      prev_lock_state[lock]['doorstatus'],
                      "->",
                      doorstatus)
            prev_lock_state[lock] = {
                "statechange_time": now,
                "lockstatus": lockstatus,
                "doorstatus": doorstatus,
                "notified": False,
                "operable": lock.is_operable,
                "bugfix_query": False
            }
        if ( lockstatus == LockStatus.UNLOCKED and
             doorstatus == LockDoorStatus.CLOSED and
             (now - prev_lock_state[lock]['statechange_time']).total_seconds() > args.notification_interval and
             prev_lock_state[lock]['notified'] == False ):
                if( prev_lock_state[lock]['bugfix_query'] == False ):
                    # August seems to have a bug - sometimes when the door is
                    # locked, their systems continue to say it is unlocked.
                    # This is also true when using their native phone app.
                    # The correct state seems to be obtainable by viewing the
                    # lock history on the phone, or the overall house status,
                    # and then going back and viewing the lock state once more.
                    # Let's do that here in our app.
                    api.get_house(authentication.access_token, lock.house_id)
                    api.get_house_activities(authentication.access_token, lock.house_id)
                    lockdetail = api.get_lock_detail(authentication.access_token, lock.device_id)
                    print(now, "August says lock is unlocked and door closed - nudging to make sure")
                    print_lock_detail(now, lockdetail)
                    prev_lock_state[lock]['bugfix_query'] = True
                    # The bug is hard to repro, it occurs intermittently. Rapid
                    # testing also seems to trigger different problems, possibly
                    # due to rate limiting within August's infrastructure.
                    # In any case, let's wait an interval after nudging.
                    skip_next_polling_delay = False
                else:
                    # Send a notification
                    print(now, "** Sending notification **")
                    prev_lock_state[lock]['notified'] = True
                    subprocess.run(args.notification_command.split())
