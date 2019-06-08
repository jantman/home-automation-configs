#!/opt/homeassistant/appdaemon/bin/python
"""
A script using MySQL to find all Events between a set of dates, matching a
specific set of criteria, and export some frames from them to a temporary
directory.
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


class ZmFrameExporter(object):

    def __init__(self, mysql_user, mysql_pass, mysql_db):
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=mysql_user,
            password=mysql_pass, db=mysql_db,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        self._outdir = mkdtemp()
        print('Output to: %s' % self._outdir)

    def run(
        self, start_dt, end_dt, monitor_ids=[], object_names=[],
        complete=False
    ):
        event_ids = self._find_event_ids(start_dt, end_dt)
        logger.info('Found %d Events in specified timeframe', len(event_ids))
        logger.debug('Event IDs: %s', event_ids.keys())
        count = 0
        for eid in event_ids:
            evt = ZMEvent(eid)
            if monitor_ids and evt.MonitorId not in monitor_ids:
                logger.debug(
                    'Skipping Event %d for Monitor %s', eid, evt.MonitorId
                )
                continue
            if complete:
                count += self._copy_complete(evt)
            elif object_names:
                count += self._copy_with_objects(evt, object_names)
            else:
                count += 1
                self._copy_frame(eid, evt.Name, evt.AllFrames[evt.BestFrameId])
        print('Wrote frames for %d events to: %s' % (count, self._outdir))

    def _copy_with_objects(self, evt, object_names):
        count = 0
        sql = 'SELECT * FROM `' + ANALYSIS_TABLE_NAME + '` WHERE ' \
              'EventID=%s'
        args = [evt.EventId]
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s with args: %s', sql, args)
            cursor.execute(sql, args)
            for row in cursor.fetchall():
                if row['Results'] == '[]':
                    continue
                results = json.loads(row['Results'])
                labels = [x['label'] for x in results]
                if any([o in labels for o in object_names]):
                    count += 1
                    self._copy_frame(
                        evt.EventId, evt.Name, evt.AllFrames[row['FrameId']]
                    )
            self._conn.commit()
        return count

    def _copy_frame(self, evt_id, ename, frame):
        src = frame.path
        dest = os.path.join(
            self._outdir, '%s_%s_%s' % (evt_id, ename, frame.filename)
        )
        logger.debug('copy %s to %s', src, dest)
        copy(src, dest)

    def _copy_complete(self, evt):
        src = evt.path
        dest = os.path.join(
            self._outdir,
            '%s_%s_%s' % (
                evt.StartTime.strftime('%Y%m%d%H%M%S'),
                evt.Monitor.Name,
                evt.EventId
            )
        )
        logger.debug('Recursively copy %s to %s', src, dest)
        copytree(src, dest)

    def _find_event_ids(self, start_dt, end_dt):
        sql = 'SELECT `Id`,`StartTime`,`Name` FROM `Events` WHERE ' \
              '((`StartTime` >= %s AND `StartTime` <= %s) OR ' \
              '(`EndTime` >= %s AND `EndTime` <= %s))'
        args = [start_dt, end_dt, start_dt, end_dt]
        results = {}
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s; with args: %s', sql, args)
            cursor.execute(sql, args)
            for row in cursor.fetchall():
                results[row['Id']] = row
            self._conn.commit()
        return results


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Export matching frames for Events in a time interval'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-m', '--monitor-id', dest='monitor_ids', action='append',
                   type=int, default=[],
                   help='limit to monitor ID(s) '
                        '(may be specified multiple times)')
    p.add_argument('-o', '--object-detection', dest='object_names',
                   action='append', type=str, default=[],
                   help='limit to events with the given object detected. '
                        'Can be specified multiple times.'
                   )
    p.add_argument('-c', '--complete', dest='complete', action='store_true',
                   default=False, help='copy complete event directory')
    p.add_argument('START_TIME', action='store', type=str,
                   help='start time (YYYY-MM-DD HH:MM:SS)')
    p.add_argument('END_TIME', action='store', type=str,
                   help='start time (YYYY-MM-DD HH:MM:SS)')
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
    start_dt = parse(args.START_TIME)
    end_dt = parse(args.END_TIME)
    script = ZmFrameExporter(
        os.environ['MYSQL_USER'], os.environ['MYSQL_PASS'],
        os.environ['MYSQL_DB']
    )
    script.run(
        start_dt, end_dt, monitor_ids=args.monitor_ids,
        object_names=args.object_names, complete=args.complete
    )
