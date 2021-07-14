# notify-if-unlocked
The August door lock is a good product with a decent app, except for one shortcoming. Because of the automation overriding natural human door locking behavior, it's easy to accidentally leave the door unlocked.

August's apps have a shortcoming in this regard - they can auto-lock the door, but they don't have a setting to simply notify you the door is unlocked.

This program sends a notification that the door has been left unlocked longer than a given threshold.

This program runs in an endless loop, polling the status of the door lock.

The first time it is run, it must be launched with --auth= so you can input your username and password to obtain an auth token.  On subsequent runs, it can run non-interactively.# If the door is left unlocked, the notification command will be invoked. (And, for reasons explained in the source, the notification command must use escaping to prevent whitespace splitting.)

## Requires
- Python (was developed on python 3.6.12)
- [py-august](https://github.com/snjoetw/py-august)

## CLI usage


    usage: notify-if-unlocked.py [-h] [-a {phone,email}] [-f CACHE_FILE]
                                 [-p POLLING_INTERVAL] [-n NOTIFICATION_INTERVAL]
                                 [-c NOTIFICATION_COMMAND] [-v]
    
    Notify if the door is unlocked.
    
    optional arguments:
      -h, --help            show this help message and exit
      -a {phone,email}, --auth {phone,email}
                            Request uname & pw from stdin, auth, then exit, which
                            is necessary if we need to re-auth
      -f CACHE_FILE, --cache-file CACHE_FILE
                            Path to the auth token
      -p POLLING_INTERVAL, --polling-interval POLLING_INTERVAL
                            How often we check the lock status, in seconds
      -n NOTIFICATION_INTERVAL, --notification-interval NOTIFICATION_INTERVAL
                            How long the door must be closed and unlocked before
                            we send notification, in seconds
      -c NOTIFICATION_COMMAND, --notification-command NOTIFICATION_COMMAND
                            A command we'll run when it's time to notify. Note,
                            quoted args are not supported.
      -v, --verbose         Print a message each time the locks are polled
