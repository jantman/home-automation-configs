#!/usr/bin/env python3
"""
Daemon to retry zmevent_handler failed analyses

<https://github.com/jantman/home-automation-configs/blob/master/zoneminder/zmevent_retry.py>

This is like zmevent_handler.py but runs as a daemon and retries any failed
analyses from RETRY_DIR.
"""

import sys
import os
import logging
from systemd.journal import JournalHandler
import argparse
import json
import time
import re
from collections import defaultdict
from platform import node
import requests
import pymysql
import glob
from datetime import datetime, timedelta

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import (
    LOG_PATH, MIN_LOG_LEVEL, ANALYSIS_TABLE_NAME, DateSafeJsonEncoder,
    HASS_EVENT_NAME, CONFIG, HASS_IGNORE_MONITOR_IDS, populate_secrets,
    HASS_IGNORE_EVENT_NAME_RES, HASS_IGNORE_MONITOR_ZONES, RETRY_START_ID
)
from zmevent_analyzer import ImageAnalysisWrapper
from zmevent_models import ZMEvent
from zmevent_filters import *
from zmevent_ir_change import handle_ir_change
from statsd_utils import statsd_set_gauge, statsd_increment_counter
from zmevent_handler import (
    send_to_hass, _set_event_name, update_event_name, handle_event,
    event_to_hass
)
from zm_videoizer import set_log_debug, set_log_info

NODE_NAME = node()

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class ZmEventRetrier:

    def __init__(self):
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=CONFIG['MYSQL_USER'],
            password=CONFIG['MYSQL_PASS'], db=CONFIG['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )

    def _handle_one(self, event_id, monitor_id, cause):
        logger.info(
            'Handling: event_id=%s monitor_id=%s cause=%s',
            event_id, monitor_id, cause
        )
        result, zones, success, event = handle_event(
            event_id, monitor_id, cause
        )
        if not success:
            logger.info('No success.')
            statsd_increment_counter('analyze_event.retries_failed')
            return False
        if event.StartTime >= datetime.now() - timedelta(minutes=10):
            event_to_hass(
                monitor_id, event_id, result, zones
            )
        statsd_increment_counter('analyze_event.retries_succeeded')
        return True

    def run(self, do_sleep=True):
        logger.warning('Running zmevent_retry.py')
        sql = 'SELECT e.*,ia.Results FROM (' \
              'SELECT Id,MonitorId,Name,StartTime,Cause FROM Events ' \
              'WHERE EndTime IS NOT NULL AND Id > %s ORDER BY Id DESC' \
              ') AS e LEFT JOIN zmevent_handler_ImageAnalysis AS ia ' \
              'ON e.Id=ia.EventId WHERE ia.Results IS NULL AND ' \
              'e.Id < (SELECT MAX(EventId) FROM ' \
              '%s) ORDER BY e.Id DESC;' % (
                  RETRY_START_ID, ANALYSIS_TABLE_NAME
              )
        while True:
            logger.info(
                'Looking for events after %d needing analysis...',
                RETRY_START_ID
            )
            rows = 0
            with self._conn.cursor() as cursor:
                logger.debug('EXECUTE: %s', sql)
                rows = cursor.execute(sql)
                logger.info('Found %d events needing analysis', rows)
                statsd_set_gauge('zmevent.needs_retry', rows)
                result = cursor.fetchone()
            self._conn.commit()
            if rows > 0:
                self._handle_one(
                    result['Id'], result['MonitorId'], result['Cause']
                )
            if do_sleep:
                time.sleep(10)


def parse_args(argv):
    """Parse command line arguments with ArgumentParser."""
    p = argparse.ArgumentParser(description='retry handler for Motion events')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-n', '--no-sleep', dest='sleep', action='store_false',
                   default=True, help='do not sleep')
    args = p.parse_args(argv)
    return args


def main():
    # populate secrets from environment variables
    logger.info('Populating secrets')
    populate_secrets()
    logger.info('Done populating secrets')
    # parse command line arguments
    args = parse_args(sys.argv[1:])
    # set logging level
    if args.verbose > 1:
        set_log_debug(logger)
    else:
        set_log_info(logger)
    ZmEventRetrier().run(do_sleep=args.sleep)


if __name__ == "__main__":
    main()
