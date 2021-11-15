#!/usr/bin/env python3
"""
Daemon to sync ZM archived events to an S3 bucket

<https://github.com/jantman/home-automation-configs/blob/master/zoneminder/zmevent_archived_s3d.py>

Environment Variables used:

BUCKET_NAME
BUCKET_REGION (default: us-east-1)
BUCKET_PREFIX= (default: empty string)
"""

import sys
import os
import logging
import argparse
from typing import List, Dict, Set
import boto3
import pymysql
from pymysql.connections import Connection
from io import StringIO
import json

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import (
    ANALYSIS_TABLE_NAME, CONFIG, ZM_HOSTNAME, populate_secrets,
    DateSafeJsonEncoder
)
from zmevent_models import ZMEvent
from zm_videoizer import set_log_debug, set_log_info

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()

for lname in ['urllib3', 'botocore', 'boto3']:
    l = logging.getLogger(lname)
    l.setLevel(logging.WARNING)
    l.propagate = True


class ZmArchivedToS3(object):

    def __init__(self, dry_run: bool = False):
        self._dry_run: bool = dry_run
        logger.debug('Connecting to MySQL')
        self._conn: Connection = pymysql.connect(
            host='localhost', user=CONFIG['MYSQL_USER'],
            password=CONFIG['MYSQL_PASS'], db=CONFIG['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        self._s3 = boto3.resource(
            's3',
            region_name=os.environ.get(
                'BUCKET_REGION',
                os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
            )
        )
        self._bucket = self._s3.Bucket(os.environ['BUCKET_NAME'])
        self._prefix: str = os.environ.get('BUCKET_PREFIX', '')
        self._s3_prefixes: List[str] = self._list_s3_prefixes()
        logger.debug(
            'Found %d prefixes in S3: %s', len(self._s3_prefixes),
            self._s3_prefixes
        )
        self._max_event_id: int = 0

    def loop(self, do_sleep=True):
        logger.info('Running zmevent_archived_s3d.py loop')
        while True:
            self.run()
            if do_sleep:
                time.sleep(30)

    def run(self):
        logger.info('Looking for archived events...')
        events: List[dict] = self._find_events()
        count = 0
        evt: Dict
        for evt in events:
            dirname: str = self._directory_for_event(evt)
            logger.debug('Event directory name: %s', dirname)
            if dirname in self._s3_prefixes:
                logger.debug('Event already in S3: %s', dirname)
                continue
            d: Dict = self._dict_for_event(
                evt['Id'], evt['MonitorId'], evt['Cause']
            )
            if not os.path.exists(d['path']):
                logger.info('Skipping; does not exist: %s', d['path'])
                continue
            self._event_to_s3(d, dirname)
            count += 1
            self._s3_prefixes.append(dirname)
            self._max_event_id = evt['Id']
        print(f'Uploaded {count} archived events to S3')

    def _event_to_s3(self, evt: Dict, dirname: str):
        dir: str = os.path.join(self._prefix, dirname)
        logger.debug(
            'Upload event %s to: s3://%s/%s', evt['EventId'],
            self._bucket.name, dir
        )
        d_key = os.path.join(dir, 'info.json')
        if self._dry_run:
            logger.warning(
                'Would upload event %s info to %s', evt['EventId'],
                d_key
            )
        else:
            logger.warning(
                'Upload event %s info to: %s', evt['EventId'], d_key
            )
            self._bucket.Object(d_key).put(Body=json.dumps(
                evt, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
            ))
        for fname in os.listdir(evt['path']):
            fpath = os.path.join(evt['path'], fname)
            p = os.path.join(dir, os.path.basename(fname))
            if self._dry_run:
                logger.warning(
                    'Would upload %s to %s', fpath, p
                )
            else:
                logger.warning('Upload %s to %s', fpath, p)
                self._bucket.upload_file(fpath, p)

    def _list_s3_prefixes(self) -> List[str]:
        res: Set[str] = set()
        for o in self._bucket.objects.filter(Prefix=self._prefix):
            k: str = o.key[len(self._prefix):].split('/')[0]
            res.add(k)
        return list(res)

    def _directory_for_event(self, event: Dict) -> str:
        t = event['StartTime'].strftime('%Y-%m-%dT%H-%M-%S')
        n = event['Name'].replace(' ', '')
        s = f"{t}_{ZM_HOSTNAME}_{n}_{event['Id']}"
        return s

    def _dict_for_event(self, event_id, monitor_id, cause):
        e = ZMEvent(event_id, monitor_id, cause)
        d: Dict = e.as_dict
        d['frames'] = self._run_sql(
            'SELECT * FROM Frames WHERE EventId=%d;' % event_id
        )
        d['ImageAnalysis'] = self._run_sql(
            'SELECT * FROM %s WHERE EventId=%d;' % (
                ANALYSIS_TABLE_NAME, event_id
            )
        )
        d['path'] = e.path
        return d

    def _find_events(self) -> List[dict]:
        logger.info('Looking for archived events...')
        sql = 'SELECT e.Id AS Id,MonitorId,m.Name AS MonitorName,' \
              'e.Name AS Name,Cause,StartTime,Archived ' \
              'FROM Events AS e ' \
              'LEFT JOIN Monitors AS m ON e.MonitorId=m.Id WHERE Archived=1 ' \
              f'AND e.Id > {self._max_event_id};'
        return self._run_sql(sql)

    def _run_sql(self, sql: str) -> List[dict]:
        with self._conn.cursor() as cursor:
            logger.debug('EXECUTE: %s', sql)
            cursor.execute(sql)
            result = cursor.fetchall()
        logger.debug('Got %d results', len(result))
        return result


def parse_args(argv):
    """Parse command line arguments with ArgumentParser."""
    p = argparse.ArgumentParser(description='upload archived events to S3')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False, help='Dry run - only log what would be done')
    p.add_argument('-n', '--no-sleep', dest='sleep', action='store_false',
                   default=True, help='do not sleep')
    p.add_argument('-o', '--one-shot', dest='oneshot', action='store_true',
                   default=False, help='Run sync once and then exit')
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
    elif args.verbose > 0:
        set_log_info(logger)
    if args.oneshot:
        ZmArchivedToS3(dry_run=args.dry_run).run()
    else:
        ZmArchivedToS3(dry_run=args.dry_run).loop(do_sleep=args.sleep)


if __name__ == "__main__":
    main()
