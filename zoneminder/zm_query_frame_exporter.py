#!/opt/homeassistant/appdaemon/bin/python
"""
A script using MySQL to find all Events matched by a SQL query, and
export some frames from them to a temporary directory.
"""

import sys
import os
import logging
import argparse
from dateutil.parser import parse
import requests
import pymysql
from tempfile import mkdtemp
from shutil import copy, copytree
import json
from glob import glob

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import (
    LOG_PATH, MIN_LOG_LEVEL, ANALYSIS_TABLE_NAME, DateSafeJsonEncoder,
    HASS_EVENT_NAME, CONFIG, populate_secrets
)
from zmevent_models import ZMEvent
from zm_filter_frame_exporter import ZmFilterFrameExporter

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

for lname in ['urllib3']:
    l = logging.getLogger(lname)
    l.setLevel(logging.WARNING)
    l.propagate = True


class ZmQueryFrameExporter(ZmFilterFrameExporter):

    def run(self, query, num_frames=5, complete=False):
        event_ids = self._find_event_ids(query)
        logger.info('Found %d Events for query: %s', len(event_ids), query)
        logger.debug('Event IDs: %s', event_ids.keys())
        count = 0
        for eid in event_ids:
            evt = ZMEvent(eid)
            if complete:
                self._copy_complete(evt)
                count += 1
            else:
                count += self._copy_max_score(evt, num_frames)
        print('Wrote frames for %d events to: %s' % (count, self._outdir))

    def _find_event_ids(self, where):
        query: str = 'SELECT * FROM Events WHERE ' + where + ';'
        results = {}
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s', query)
            cursor.execute(query)
            for row in cursor.fetchall():
                results[row['Id']] = row
            self._conn.commit()
        return results


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Export frames for Events matched by a SQL query'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-c', '--complete', dest='complete', action='store_true',
                   default=False, help='copy complete event directory')
    p.add_argument('-n', '--num-frames', dest='num_frames', action='store',
                   type=int, default=5,
                   help='Only export the N highest-scoring frames')
    p.add_argument('-D', '--dry-run', action='store_true', dest='dry_run',
                   default=False,
                   help='Instead of copying frames, write file with '
                        'paths that would be copied.')
    p.add_argument('QUERY', type=str, help='Query where clause')
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

    populate_secrets()
    ZmQueryFrameExporter(
        os.environ['MYSQL_USER'], os.environ['MYSQL_PASS'],
        os.environ['MYSQL_DB'], dry_run=args.dry_run
    ).run(
        args.QUERY, num_frames=args.num_frames, complete=args.complete
    )
