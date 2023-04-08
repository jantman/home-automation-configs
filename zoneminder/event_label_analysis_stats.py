#!/opt/homeassistant/appdaemon/bin/python
"""
A script using MySQL to find all Events matched by a SQL query, and
export some frames from them to a temporary directory.
"""

import sys
import os
import logging
import argparse
import pymysql
import json

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import ANALYSIS_TABLE_NAME, populate_secrets

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

for lname in ['urllib3']:
    l = logging.getLogger(lname)
    l.setLevel(logging.WARNING)
    l.propagate = True


class EventAnalysisStats:

    def __init__(self, mysql_user, mysql_pass, mysql_db):
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=mysql_user,
            password=mysql_pass, db=mysql_db,
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )

    def run(self, label: str, event_id: int):
        query: str = 'SELECT * FROM ' + ANALYSIS_TABLE_NAME + \
                     f' WHERE EventId={event_id} ORDER BY FrameId ASC;'
        print(f'Event {event_id} results for label "{label}"')
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s', query)
            cursor.execute(query)
            for row in cursor.fetchall():
                results = json.loads(row['Results'])
                ignored = json.loads(row['IgnoredResults'])
                print(f'## Frame {row["FrameId"]}')
                for r in results:
                    if r['label'] == label:
                        print(f'Result: Score={r["score"]} Zones={r["zones"]}; IgnoreReason={r["ignore_reason"]}')
                for r in ignored:
                    if r['label'] == label:
                        print(f'Ignored: Score={r["score"]} Zones={r["zones"]}; IgnoreReason={r["ignore_reason"]}')
            self._conn.commit()
        return results


def parse_args(argv):
    p = argparse.ArgumentParser(
        description='Show analysis stats for a specific label in a '
                    'specific event'
    )
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('LABEL', type=str, help='Label to report on')
    p.add_argument('EVENT_ID', type=int, help='Event ID')
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
    EventAnalysisStats(
        os.environ['MYSQL_USER'], os.environ['MYSQL_PASS'],
        os.environ['MYSQL_DB']
    ).run(args.LABEL, args.EVENT_ID)
