#!/opt/homeassistant/appdaemon/bin/python
"""
A script using MySQL to find all Events matched by a specified ZM Filter, and
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

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import (
    LOG_PATH, MIN_LOG_LEVEL, ANALYSIS_TABLE_NAME, DateSafeJsonEncoder,
    HASS_EVENT_NAME, CONFIG, populate_secrets
)
from zmevent_models import ZMEvent

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

for lname in ['urllib3']:
    l = logging.getLogger(lname)
    l.setLevel(logging.WARNING)
    l.propagate = True


def _zm_term_to_sql(term: dict) -> str:
    """
    {"obr":"1","attr":"Name","op":"LIKE","val":"person","cbr":"0"}
    {"cnj":"or","obr":"0","attr":"Archived","op":"=","val":"1","cbr":"1"}
    {"cnj":"and","obr":"0","attr":"MonitorId","op":"<","val":"3","cbr":"0"}
    """
    s: str = ''
    if term.get('obr') in [1, '1']:
        s += '( '
    if term.get('cnj') not in [None, '']:
        s += term.get('cnj') + ' '
    s += term['attr'] + ' ' + term['op'] + ' "' + term['val'] + '"'
    if term.get('cbr') in [1, '1']:
        s += ')'
    s += ' '
    return s


def zm_json_filter_to_sql(f: dict) -> str:
    s: str = 'SELECT * FROM Events WHERE '
    for term in f['terms']:
        s += _zm_term_to_sql(term)
    if 'sort_field' in f:
        s += 'ORDER BY ' + f['sort_field']
        if f.get('sort_asc') in [1, '1']:
            s += ' ASC '
        else:
            s += ' DESC '
    if f.get('limit'):
        s += 'LIMIT ' + f['limit']
    s += ';'
    return s


class ZmFilterFrameExporter(object):

    def __init__(self, mysql_user, mysql_pass, mysql_db, dry_run=False):
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=mysql_user,
            password=mysql_pass, db=mysql_db,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        self._outdir = mkdtemp()
        print('Output to: %s' % self._outdir)
        self.dry_run = dry_run

    def run(
        self, filter_id, min_score=None, num_frames=5, complete=False
    ):
        event_ids = self._find_event_ids(filter_id)
        logger.info('Found %d Events for filter %d', len(event_ids), filter_id)
        logger.debug('Event IDs: %s', event_ids.keys())
        count = 0
        for eid in event_ids:
            evt = ZMEvent(eid)
            if complete:
                self._copy_complete(evt)
                count += 1
            elif min_score:
                count += self._copy_with_min_score(evt, min_score)
            else:
                count += self._copy_max_score(evt, num_frames)
        print('Wrote frames for %d events to: %s' % (count, self._outdir))

    def _copy_with_min_score(self, evt, min_score):
        count = 0
        sql = 'SELECT * FROM `Frames` WHERE EventID=%s AND Score >= %s'
        args = [evt.EventId, min_score]
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s with args: %s', sql, args)
            cursor.execute(sql, args)
            for row in cursor.fetchall():
                self._copy_frame(
                    evt.EventId, evt.Name, evt.AllFrames[row['FrameId']]
                )
            self._conn.commit()
        return count

    def _copy_max_score(self, evt, num_frames):
        count = 0
        sql = 'SELECT * FROM `Frames` WHERE EventID=%s ' \
              'ORDER BY Score DESC LIMIT %s'
        args = [evt.EventId, num_frames]
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s with args: %s', sql, args)
            cursor.execute(sql, args)
            for row in cursor.fetchall():
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
        if self.dry_run:
            with open(os.path.join(self._outdir, 'frames.txt'), 'a') as fh:
                fh.write(src + "\n")
            return
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
        if self.dry_run:
            with open(os.path.join(self._outdir, 'frames.txt'), 'a') as fh:
                fh.write(src + "\n")
            return
        copytree(src, dest)

    def _find_event_ids(self, filter_id):
        sql = 'SELECT Id,Name,Query_json FROM Filters WHERE Id=%s;'
        args = [filter_id]
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s with args: %s', sql, args)
            cursor.execute(sql, args)
            row = cursor.fetchone()
            self._conn.commit()
        logger.info(
            'Build SQL for query %d (%s): %s',
            row['Id'], row['Name'], row['Query_json']
        )
        sql = zm_json_filter_to_sql(json.loads(row['Query_json']))
        logger.info('Resulting SQL: %s', sql)
        results = {}
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s', sql)
            cursor.execute(sql)
            for row in cursor.fetchall():
                results[row['Id']] = row
            self._conn.commit()
        return results


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Export frames for Events matched by a Filter'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-c', '--complete', dest='complete', action='store_true',
                   default=False, help='copy complete event directory')
    p.add_argument('-s', '--min-score', dest='min_score', action='store',
                   type=int, default=None,
                   help='Only export frames with score greater than or equal to'
                   )
    p.add_argument('-n', '--num-frames', dest='num_frames', action='store',
                   type=int, default=5,
                   help='Only export the N highest-scoring frames')
    p.add_argument('-D', '--dry-run', action='store_true', dest='dry_run',
                   default=False,
                   help='Instead of copying frames, write file with '
                        'paths that would be copied.')
    p.add_argument('FILTER_ID', type=int, help='Filter ID')
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
    ZmFilterFrameExporter(
        os.environ['MYSQL_USER'], os.environ['MYSQL_PASS'],
        os.environ['MYSQL_DB'], dry_run=args.dry_run
    ).run(
        args.FILTER_ID, complete=args.complete, min_score=args.min_score,
        num_frames=args.num_frames
    )
