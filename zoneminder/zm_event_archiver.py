#!/usr/bin/env python3
"""
Semi-companion to zmevent_handler.py.

1. Deletes all records from ANALYSIS_TABLE_NAME in ZoneMinder's MySQL DB that
   don't have matching records in the Event table (i.e. deleted events).
2. Queries the DB directly for all non-archived events older than a given number
   of days (default 30) and then uses the ZM API to delete them.
"""

import sys
import os
import logging
import argparse
import json
from datetime import datetime
import pymysql
import requests

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import ANALYSIS_TABLE_NAME

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class ZmEventArchiver(object):

    def __init__(self, base_url, dry_run=False):
        self._dry_run = dry_run
        self._base_url = base_url
        if not self._base_url.endswith('/'):
            self._base_url += '/'
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=os.environ['MYSQL_USER'],
            password=os.environ['MYSQL_PASS'], db=os.environ['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        logger.debug('Connected to MySQL')

    def run(self, keep_days=30):
        self._purge_analysis_table()
        event_ids = self._find_events(keep_days)
        self._delete_events(event_ids)

    def _find_events(self, num_days):
        logger.info(
            'Looking for unarchived events older than %d days', num_days
        )
        sql = 'SELECT Id from Events WHERE Archived=0 AND ' \
              'StartTime < DATE_SUB(NOW(), INTERVAL %d DAY);' % num_days
        events = []
        with self._conn.cursor() as cursor:
            logger.debug('Executing: %s', sql)
            cursor.execute(sql)
            res = cursor.fetchall()
            for r in res:
                events.append(r['Id'])
            self._conn.commit()
        logger.info(
            'Found %d unarchived events older than %d days', len(events),
            num_days
        )
        return events

    def _delete_events(self, event_ids):
        logger.info('About to DELETE %d events...', len(event_ids))
        for eid in event_ids:
            url = '%sevents/%s.json' % (self._base_url, eid)
            if self._dry_run:
                logger.warning('Would execute HTTP DELETE %s' % url)
                continue
            logger.info('DELETEing Event %s', eid)
            logger.debug('HTTP DELETE %s', url)
            r = requests.delete(url)
            r.raise_for_status()
            logger.debug('Responded %s: %s', r.status_code, r.text)
        logger.info('Deleted all %d events.', len(event_ids))

    def _purge_analysis_table(self):
        sql = 'DELETE FROM %s WHERE (EventId, FrameId) NOT IN ' \
              '(SELECT EventId, FrameId FROM Frames);' % ANALYSIS_TABLE_NAME
        if self._dry_run:
            logger.warning('WOULD EXECUTE: %s', sql)
            return
        with self._conn.cursor() as cursor:
            logger.debug('EXECUTING: %s', sql)
            num_rows = cursor.execute(sql)
            logger.info(
                'Purged %d rows from %s', num_rows, ANALYSIS_TABLE_NAME
            )
            self._conn.commit()


def parse_args(argv):
    p = argparse.ArgumentParser(description='ZoneMinder Event Archiver')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False,
                   help="dry-run - don't actually make any changes")
    p.add_argument('-v', '--verbose', dest='verbose', action='store_true',
                   default=False,
                   help='verbose output')
    p.add_argument('-k', '--keep-days', dest='keep_days', action='store',
                   type=int, default=30,
                   help='number of days of non-archived events to keep '
                        '(default 30)')
    p.add_argument('-u', '--url', dest='base_url', action='store', type=str,
                   default='http://localhost/zm/api/',
                   help='ZM API base url; default: http://localhost/zm/api/')

    args = p.parse_args(argv)

    return args


def set_log_info():
    """set logger level to INFO"""
    set_log_level_format(logging.INFO,
                         '%(asctime)s %(levelname)s:%(name)s:%(message)s')


def set_log_debug():
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(level, format):
    """
    Set logger level and format.

    :param level: logging level; see the :py:mod:`logging` constants.
    :type level: int
    :param format: logging formatter format string
    :type format: str
    """
    formatter = logging.Formatter(fmt=format)
    logger.handlers[0].setFormatter(formatter)
    logger.setLevel(level)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()

    script = ZmEventArchiver(args.base_url, dry_run=args.dry_run)
    script.run(args.keep_days)
