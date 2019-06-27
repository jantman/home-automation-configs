#!/opt/homeassistant/appdaemon/bin/python
"""
A script using MySQL to output the event directories for a list of one or more
Event IDs.
"""

import sys
import os
import logging
import argparse
from dateutil.parser import parse
import pymysql
from tempfile import mkdtemp
from shutil import copy, copytree
import json

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import (
    LOG_PATH, MIN_LOG_LEVEL, ANALYSIS_TABLE_NAME, DateSafeJsonEncoder,
    HASS_EVENT_NAME, CONFIG
)
from zmevent_models import ZMEvent

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

for lname in ['urllib3']:
    l = logging.getLogger(lname)
    l.setLevel(logging.WARNING)
    l.propagate = True


class ZmDirLister(object):

    def __init__(self, mysql_user, mysql_pass, mysql_db):
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=mysql_user,
            password=mysql_pass, db=mysql_db,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )

    def run(self, event_ids):
        for eid in event_ids:
            evt = ZMEvent(eid)
            print(evt.path)


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Export matching frames for Events in a time interval'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('EVENT_ID', action='append', type=int, default=[],
                   nargs='+', help='Event ID(s)')
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


def populate_secrets():
    """Populate the ``CONFIG`` global from environment variables."""
    global CONFIG
    for varname in CONFIG.keys():
        if varname not in os.environ:
            raise RuntimeError(
                'ERROR: Variable %s must be set in environment' % varname
            )
        CONFIG[varname] = os.environ[varname]


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()

    populate_secrets()
    ZmDirLister(
        os.environ['MYSQL_USER'], os.environ['MYSQL_PASS'],
        os.environ['MYSQL_DB']
    ).run(args.EVENT_ID)
