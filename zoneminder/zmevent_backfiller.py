#!/usr/bin/env python3
"""
Script to backfill database information on ZoneMinder Events.

<https://github.com/jantman/home-automation-configs/blob/master/zoneminder/zmevent_backfiller.py>

Configuration is in ``zmevent_config.py``.

Program flow:

- Searches all Events in ZM database since ``FIRST_EVENT_ID`` for ones that do
  not exist in ``ANALYSIS_TABLE_NAME`` and runs analysis/handling on them.

The functionality of this script relies on the other ``zmevent_*.py`` modules
in this git repo.
"""

import sys
import os
import logging
import argparse
from time import sleep

try:
    import pymysql
except ImportError:
    raise SystemExit(
        'could not import pymysql - please "pip install PyMySQL"'
    )

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import (
    ANALYSIS_TABLE_NAME, CONFIG, RETRY_START_ID
)
from zmevent_handler import (
    handle_event, populate_secrets, setup_library_logging
)
from zm_videoizer import set_log_debug, set_log_info

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()
setup_library_logging()

for lname in ['urllib3']:
    l = logging.getLogger(lname)
    l.setLevel(logging.WARNING)
    l.propagate = True


class ZmEventBackfiller(object):

    def __init__(self):
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=CONFIG['MYSQL_USER'],
            password=CONFIG['MYSQL_PASS'], db=CONFIG['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )

    def run(self, min_event_id=RETRY_START_ID, sleep_time=0, dry_run=False):
        events = self._find_events(min_event_id)
        logger.info('Found %d events needing analysis', len(events))
        count = 0
        for evt in events:
            count += 1
            print('Handling event: %s' % evt)
            if dry_run:
                continue
            handle_event(evt['Id'], evt['MonitorId'], evt['Cause'])
            print('Finished event %d of %d' % (count, len(events)))
            if sleep_time > 0:
                logger.debug('Sleeping for %s', sleep_time)
                sleep(sleep_time)
        print('Done.')

    def _find_events(self, min_event_id=RETRY_START_ID):
        logger.info(
            'Looking for events after %d needing analysis...', min_event_id
        )
        sql = 'SELECT e.*,ia.Results FROM (' \
              'SELECT Id,MonitorId,Name,StartTime,Cause FROM Events ' \
              'WHERE EndTime IS NOT NULL AND Id > %s ORDER BY Id DESC' \
              ') AS e LEFT JOIN zmevent_handler_ImageAnalysis AS ia ' \
              'ON e.Id=ia.EventId WHERE ia.Results IS NULL AND ' \
              'e.Id < (SELECT MAX(EventId) FROM' \
              '%s);' % (min_event_id, ANALYSIS_TABLE_NAME)
        with self._conn.cursor() as cursor:
            logger.debug('EXECUTE: %s', sql)
            cursor.execute(sql)
            result = cursor.fetchall()
        logger.debug('Got %d results', len(result))
        return result


def parse_args(argv):
    """Parse command line arguments with ArgumentParser."""
    p = argparse.ArgumentParser(description='handler for Motion events')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-s', '--sleep', dest='sleep', action='store', default=0.0,
                   type=float, help='Time to sleep between each event')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False, help='Dry run - only log what would be done')
    p.add_argument('-i', '--id', dest='FIRST_EVENT_ID', action='store',
                   type=int, help='first Event ID to check',
                   default=RETRY_START_ID)
    args = p.parse_args(argv)
    return args


def main():
    # populate secrets from environment variables
    populate_secrets()
    # parse command line arguments
    args = parse_args(sys.argv[1:])
    # set logging level
    if args.verbose > 1:
        set_log_debug(logger)
    else:
        set_log_info(logger)
    ZmEventBackfiller().run(
        min_event_id=args.FIRST_EVENT_ID, sleep_time=args.sleep,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
