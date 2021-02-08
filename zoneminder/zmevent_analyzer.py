import logging
import pymysql
import json
import requests
from time import sleep, time
from random import uniform

from zmevent_config import CONFIG, ANALYSIS_TABLE_NAME, DateSafeJsonEncoder
from zmevent_models import ObjectDetectionResult, DetectedObject
from statsd_utils import statsd_send_time, statsd_set_gauge


logger = logging.getLogger(__name__)


class ImageAnalysisWrapper(object):
    """Wraps calling the ``ANALYZER`` classes and storing their results."""

    def __init__(self, event, _, hostname):
        self._event = event
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=CONFIG['MYSQL_USER'],
            password=CONFIG['MYSQL_PASS'], db=CONFIG['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        self._hostname = hostname

    def _result_to_db(self, result, frame):
        """Write an ObjectDetectionResult instance to DB"""
        sql = 'INSERT INTO `' + ANALYSIS_TABLE_NAME + \
              '` (`MonitorId`, `ZoneId`, `EventId`, `FrameId`, ' \
              '`AnalyzerName`, `RuntimeSec`, `Results`, `IgnoredResults`) ' \
              'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ' \
              'ON DUPLICATE KEY UPDATE `RuntimeSec`=%s, `Results`=%s,' \
              '`IgnoredResults`=%s'
        with self._conn.cursor() as cursor:
            res_json = json.dumps(result.detections, cls=DateSafeJsonEncoder)
            ign_json = json.dumps(
                result.ignored_detections, cls=DateSafeJsonEncoder
            )
            args = [
                self._event.MonitorId,
                0,  # ZoneId
                self._event.EventId,
                frame.FrameId,
                result.analyzer_name,
                '%.2f' % result.runtime,
                res_json,
                ign_json,
                '%.2f' % result.runtime,
                res_json,
                ign_json
            ]
            try:
                logger.debug('EXECUTING: %s; ARGS: %s', sql, args)
                cursor.execute(sql, args)
                self._conn.commit()
            except Exception:
                logger.error(
                    'ERROR executing %s; for %s',
                    sql, self._event, exc_info=True
                )

    def _to_framepath(self, p):
        if self._hostname != 'telescreen':
            return p.replace(
                '/usr/share/zoneminder/www/events/',
                '/mnt/guarddog/guarddog-events/'
            )
        return p

    def _to_results(self, d):
        result = []
        for item in d:
            if self._hostname != 'telescreen':
                item['frame_path'] = item['frame_path'].replace(
                    '/mnt/guarddog/guarddog-events/',
                    '/usr/share/zoneminder/www/events/'
                )
                item['output_path'] = item['output_path'].replace(
                    '/mnt/guarddog/guarddog-events/',
                    '/usr/share/zoneminder/www/events/'
                )
            item['detections'] = [
                DetectedObject(**x) for x in item['detections']
            ]
            item['ignored_detections'] = [
                DetectedObject(**y) for y in item['ignored_detections']
            ]
            item['detected_path'] = item['output_path']
            del item['output_path']
            item['event_id'] = item['EventId']
            del item['EventId']
            item['frame_id'] = item['FrameId']
            del item['FrameId']
            result.append(ObjectDetectionResult(**item))
        return result

    def analyze_event(self):
        """returns a list of ObjectDetectionResult instances"""
        NUM_TRIES = 15
        data = {
            'hostname': self._hostname,
            'EventId': self._event.EventId,
            'monitor_zones': {
                x: self._event.Monitor.Zones[x].as_dict
                for x in self._event.Monitor.Zones.keys()
            },
            'frames': {
                f.FrameId: self._to_framepath(f.path)
                for f in self._event.FramesForAnalysis.values()
            }
        }
        logger.debug('POST data: %s', data)
        results = None
        start = time()
        i = 0
        for i in range(0, NUM_TRIES):
            url = 'http://192.168.0.103:8008/'  # telescreen
            try:
                logger.info('POST to %s', url)
                r = requests.post(url, json=data, timeout=20.0)
                r.raise_for_status()
                results = r.json()
                break
            except Exception:
                statsd_send_time(
                    'analyze_event.post_failure_time', time() - start
                )
                logger.error(
                    'ERROR POSTing to zmevent_analysis_server', exc_info=True
                )
                sleep(uniform(0.25, 3.0))
        statsd_set_gauge('analyze_event.num_posts', i + 1)
        if results is None:
            logger.critical(
                'Analysis POST failed on all %d attempts!', NUM_TRIES
            )
            statsd_send_time(
                'analyze_event.unrecoverable_failure_time', time() - start
            )
            return None
        results = self._to_results(results)
        for res in results:
            try:
                self._result_to_db(
                    res,
                    self._event.FramesForAnalysis[int(res._frame_id)]
                )
            except Exception:
                logger.critical(
                    'Exception writing analysis result to DB for %s: %s',
                    self._event, res, exc_info=True
                )
        statsd_send_time(
            'analyze_event.success_time', time() - start
        )
        return results
