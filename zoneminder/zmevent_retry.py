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
    HASS_IGNORE_EVENT_NAME_RES, HASS_IGNORE_MONITOR_ZONES, RETRY_DIR
)
from zmevent_analyzer import ImageAnalysisWrapper
from zmevent_models import ZMEvent
from zmevent_filters import *
from zmevent_ir_change import handle_ir_change
from statsd_utils import statsd_increment_counter, statsd_send_time
from zmevent_handler import (
    send_to_hass, _set_event_name, update_event_name, set_retry, handle_event,
    event_to_hass
)
from zm_videoizer import set_log_debug, set_log_info

NODE_NAME = node()

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class ZmEventRetrier:

    def __init__(self):
        pass

    def _handle_one(self, fname):
        logger.info('Handling: %s', fname)
        with open(fname, 'r') as fh:
            data = json.load(fh)
        logger.info('Handling event: %s', data)
        result, zones, success, event = handle_event(
            data['event_id'], data['monitor_id'], data['cause'],
            num_retries=data.get('num_retries', 0)
        )
        if not success:
            logger.info('No success.')
            return
        if event.StartTime >= datetime.now() - timedelta(minutes=10):
            event_to_hass(
                data['monitor_id'], data['event_id'], result, zones
            )
        statsd_set_gauge('analyze_event.num_retries', data['num_retries'])

    def run(self):
        while True:
            g = os.path.join(RETRY_DIR + '*.json')
            files = sorted(glob.glob(g))
            if files:
                logger.info(
                    'Found %d files to process; handling first', len(files)
                )
                self._handle_one(files[0])
            else:
                logger.debug('No files to handle in: %s', g)
            time.sleep(10)


def parse_args(argv):
    """Parse command line arguments with ArgumentParser."""
    p = argparse.ArgumentParser(description='retry handler for Motion events')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    args = p.parse_args(argv)
    return args


def main():
    # populate secrets from environment variables
    populate_secrets()
    # parse command line arguments
    args = parse_args(sys.argv[1:])
    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()
    ZmEventRetrier().run()


if __name__ == "__main__":
    main()
