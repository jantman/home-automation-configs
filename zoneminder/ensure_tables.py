#!/usr/bin/env python3

import sys
import logging
import pymysql

sys.path.append('/usr/local/bin')
from zmevent_handler import (
    ANALYSIS_TABLE_NAME, MYSQL_USER, MYSQL_PASS, MYSQL_DB
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()


def ensure_table():
    conn = pymysql.connect(
        host='localhost', user=MYSQL_USER, password=MYSQL_PASS,
        db=MYSQL_DB, charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    try:
        with conn.cursor() as cursor:
            sql = 'SHOW TABLES;'
            logger.debug('EXECUTE: %s', sql)
            cursor.execute(sql)
            tmp = cursor.fetchall()
            tables = [x['Tables_in_zm'] for x in tmp]
            logger.debug('Tables: %s', sorted(tables))
            if ANALYSIS_TABLE_NAME in tables:
                logger.debug('Table %s exists', ANALYSIS_TABLE_NAME)
                return
            logger.warning(
                'Table %s does not exist; creating', ANALYSIS_TABLE_NAME
            )
            parts = [
                'CREATE TABLE `%s` (' % ANALYSIS_TABLE_NAME,
                "`MonitorId` int(10) unsigned NOT NULL DEFAULT '0',",
                "`ZoneId` int(10) unsigned NOT NULL DEFAULT '0',",
                "`EventId` int(10) unsigned NOT NULL DEFAULT '0',",
                "`FrameId` int(10) unsigned NOT NULL DEFAULT '0',",
                "`FrameType` tinytext,",
                "`AnalyzerName` VARCHAR(30) NOT NULL,",
                "`RuntimeSec` decimal(10,2) DEFAULT '0.00',",
                "`Results` text,",
                "KEY `EventId` (`EventId`),",
                "KEY `MonitorId` (`MonitorId`),",
                "KEY `ZoneId` (`ZoneId`),",
                "KEY `FrameId` (`FrameId`),",
                "KEY `AnalyzerName` (`AnalyzerName`),",
                "PRIMARY KEY (`EventId`, `MonitorId`, `ZoneId`, `FrameId`, "
                "`AnalyzerName`)",
                ") ENGINE=InnoDB DEFAULT CHARSET='utf8mb4';"
            ]
            sql = ' '.join(parts)
            logger.debug('EXECUTE: %s', sql)
            cursor.execute(sql)
        conn.commit()
        with conn.cursor() as cursor:
            sql = 'SHOW TABLES;'
            logger.debug('EXECUTE: %s', sql)
            cursor.execute(sql)
            tmp = cursor.fetchall()
            tables = [x['Tables_in_zm'] for x in tmp]
            logger.debug('Tables: %s', sorted(tables))
            if ANALYSIS_TABLE_NAME in tables:
                logger.warning(
                    'Ok, table %s successfully created', ANALYSIS_TABLE_NAME
                )
                return
            logger.critical(
                'ERROR: Failed creating table %s', ANALYSIS_TABLE_NAME
            )
            raise RuntimeError('Failed creating table %s' % ANALYSIS_TABLE_NAME)
    finally:
        conn.close()


def main():
    ensure_table()


if __name__ == "__main__":
    main()
