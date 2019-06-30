import logging
import pymysql
import json

from zmevent_config import CONFIG, ANALYSIS_TABLE_NAME, DateSafeJsonEncoder
from zmevent_image_analysis import YoloAnalyzer, AlternateYoloAnalyzer

try:
    import cv2
except ImportError:
    raise SystemExit(
        'could not import cv2 - please "pip install opencv-python"'
    )
try:
    from pydarknet import Detector, Image
except ImportError:
    raise SystemExit(
        'could not import pydarknet - please "pip install yolo34py" or '
        '"pip install yolo34py-gpu"'
    )


logger = logging.getLogger(__name__)

ANALYZER_NAMES = {
    'YoloAnalyzer': YoloAnalyzer,
    'AlternateYoloAnalyzer': AlternateYoloAnalyzer,
}


class ImageAnalysisWrapper(object):
    """Wraps calling the ``ANALYZER`` classes and storing their results."""

    def __init__(self, event, analyzer_names, hostname):
        self._event = event
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=CONFIG['MYSQL_USER'],
            password=CONFIG['MYSQL_PASS'], db=CONFIG['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        self._analyzers = [
            ANALYZER_NAMES[x] for x in analyzer_names
        ]
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

    def analyze_event(self):
        """returns a list of ObjectDetectionResult instances"""
        results = []
        for a in self._analyzers:
            logger.debug('Running object detection with: %s', a)
            # BEGIN TEMPORARY DEBUGGING
            logger.debug('ANALYZE CALL: %s', json.dumps({
                'monitor_zones': {
                    x: x.as_dict for x in self._event.Monitor.Zones
                },
                'hostname': self._hostname,
                'EventId': self._event.EventId,
                'FrameId': frame.FrameId,
                'frame_path': frame.path
            }))
            # END TEMPORARY DEBUGGING
            cls = a(self._event.Monitor.Zones, self._hostname)
            for frame in self._event.FramesForAnalysis.values():
                res = cls.analyze(
                    self._event.EventId,
                    frame.FrameId,
                    frame.path
                )
                results.append(res)
                try:
                    self._result_to_db(res, frame)
                except Exception:
                    logger.critical(
                        'Exception writing analysis result to DB for %s %s',
                        self._event, a.__name__, exc_info=True
                    )
        return results
