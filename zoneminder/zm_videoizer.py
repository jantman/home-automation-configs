#!/opt/homeassistant/appdaemon/bin/python
"""
A script using MySQL and the ZoneMinder web UI to ensure videos exist for all
events in a given timeframe (and optionally from a given monitor)
"""

import sys
import os
import logging
import argparse
from dateutil.parser import parse
import requests
import pymysql


FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

for lname in ['urllib3']:
    l = logging.getLogger(lname)
    l.setLevel(logging.WARNING)
    l.propagate = True


class ZmVideoizer(object):

    def __init__(self, mysql_user, mysql_pass, mysql_db):
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=mysql_user,
            password=mysql_pass, db=mysql_db,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )

    def run(self, start_dt, end_dt, monitor_id=None, symlink_to=None):
        event_ids = self._find_event_ids(
            start_dt, end_dt, monitor_id=monitor_id
        )
        logger.info('Found %d matching Events', len(event_ids))
        logger.debug('Event IDs: %s', event_ids.keys())
        filepaths = []
        logger.info('Triggering video generation for all events...')
        for k in event_ids.keys():
            p = self._generate_video(k)
            filepaths.append(p)
            if symlink_to is not None:
                lpath = os.path.join(symlink_to, os.path.basename(p))
                if os.path.exists(lpath):
                    os.unlink(lpath)
                os.symlink(p, lpath)
        logger.info('Video generation complete.')
        for p in filepaths:
            print(p)

    def _generate_video(self, event_id):
        url = 'http://localhost/zm/index.php'
        data = {
            'view': 'request',
            'request': 'event',
            'action': 'video',
            'id': event_id,
            'videoFormat': 'mpeg',
            'rate': '100',
            'scale': '100'
        }
        logger.debug('POST %s data=%s', url, data)
        r = requests.post(
            url, data=data, headers={'Accept': 'application/json'}
        )
        r.raise_for_status()
        logger.debug('HTTP %s: %s', r.status_code, r.text)
        j = r.json()
        logger.info('Event %d: %s', event_id, j['response'])
        return j['response']

    def _find_event_ids(self, start_dt, end_dt, monitor_id=None):
        sql = 'SELECT `Id`,`StartTime`,`Name` FROM `Events` WHERE ' \
              '((`StartTime` >= %s AND `StartTime` <= %s) OR ' \
              '(`EndTime` >= %s AND `EndTime` <= %s))'
        args = [start_dt, end_dt, start_dt, end_dt]
        if monitor_id is not None:
            sql += ' AND `MonitorId`=%s'
            args.append(monitor_id)
        results = {}
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s; with args: %s', sql, args)
            cursor.execute(sql, args)
            for row in cursor.fetchall():
                results[row['Id']] = row
            self._conn.commit()
        return results


def parse_args(argv):
    p = argparse.ArgumentParser(description='Ensure videos exist for ZM events')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-m', '--monitor-id', dest='monitor_id', action='store',
                   type=int, default=None, help='limit to monitor ID')
    p.add_argument('-s', '--symlink-to', dest='symlink_to', action='store',
                   type=str, default=None,
                   help='symlink into this directory '
                        '(existing will be overwritten)')
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


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    else:
        set_log_info()

    start_dt = parse(args.START_TIME)
    end_dt = parse(args.END_TIME)
    if args.symlink_to is not None and not os.path.isdir(args.symlink_to):
        raise RuntimeError(
            'ERROR: If -s / --symlink-to is specified, it must be a directory'
        )
    script = ZmVideoizer(
        os.environ['MYSQL_USER'], os.environ['MYSQL_PASS'],
        os.environ['MYSQL_DB']
    )
    script.run(
        start_dt, end_dt, monitor_id=args.monitor_id,
        symlink_to=args.symlink_to
    )
