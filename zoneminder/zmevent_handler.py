#!/usr/bin/env python3
"""
My Python script for handling ZoneMinder events. This is called by
zmeventnotification.pl.

<https://github.com/jantman/home-automation-configs/blob/master/zoneminder/zmevent_handler.py>

Configuration is in ``zmevent_config.py``.

Program flow:

- Called from zmeventnotification.pl with EventID, MonitorID and possible Cause.
  The event may still be in progress when called.
- Populate Event information from the ZoneMinder database into objects.
- Ignore events where the camera switched from B&W (IR) to color or from color
  to B&W (IR).
- Feed images through darknet yolo3 object detection.
- Send email and pushover notifications with first/best/last motion frame and
  object detection results, as well as some other stats.

The functionality of this script relies on the other ``zmevent_*.py`` modules
in this git repo.

##########################################
@TODO:
- select Frames for object detection
- run object detection on frames, save results to DB, add to dict to pass to HASS
  - each detection should also be localized to one or a list of zones
  - global config for objects to ignore - IgnoredObject classes that ObjectDetectionResult instances match against
- serialize all that info and pass it to HASS via an event, to be handled by AppDaemon
  - keep trying for 120s or so. If all fail, write to disk in logdir
"""

import sys
import os
import logging
from logging.handlers import SysLogHandler
import argparse
import json

try:
    import requests
except ImportError:
    raise SystemExit(
        'could not import requests - please "pip install requests"'
    )
try:
    import pymysql
except ImportError:
    raise SystemExit(
        'could not import pymysql - please "pip install PyMySQL"'
    )
try:
    from PIL import Image
except ImportError:
    raise SystemExit(
        'could not import PIL - please "pip install Pillow"'
    )

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import (
    LOG_PATH, MIN_LOG_LEVEL, ANALYSIS_TABLE_NAME, DateSafeJsonEncoder
)
from zmevent_image_analysis import YoloAnalyzer
from zmevent_models import ZMEvent
from zmevent_filters import *

#: A list of the :py:class:`~.ImageAnalyzer` subclasses to use for each frame.
ANALYZERS = [YoloAnalyzer]

#: logger - this will be set in :py:func:`~.main` to log to either stdout/err
#: or a file depending on options
logger = None


class ImageAnalysisWrapper(object):
    """Wraps calling the ``ANALYZER`` classes and storing their results."""

    def __init__(self, event):
        self._event = event
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=CONFIG['MYSQL_USER'],
            password=CONFIG['MYSQL_PASS'], db=CONFIG['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        self._analyzers = []
        self._suppression_reason = None

    def _result_to_db(self, analyzer):
        sql = 'INSERT INTO `' + ANALYSIS_TABLE_NAME + \
              '` (`MonitorId`, `ZoneId`, `EventId`, `FrameId`, ' \
              '`FrameType`, `AnalyzerName`, `RuntimeSec`, `Results`) ' \
              'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ' \
              'ON DUPLICATE KEY UPDATE `RuntimeSec`=%s, `Results`=%s'
        for ftype in ['First', 'Best', 'Last']:
            with self._conn.cursor() as cursor:
                frame = getattr(self._event, '%sFrame' % ftype)
                res = {
                    'result': analyzer.result[ftype],
                    'paths': analyzer.frames[ftype]
                }
                res_json = json.dumps(res)
                args = [
                    self._event.MonitorId,
                    0,  # ZoneId
                    self._event.EventId,
                    frame.FrameId,
                    ftype,
                    analyzer.__class__.__name__,
                    '%.2f' % analyzer.runtime,
                    res_json,
                    '%.2f' % analyzer.runtime,
                    res_json
                ]
                try:
                    logger.debug('EXECUTING: %s; ARGS: %s', sql, args)
                    cursor.execute(sql, args)
                    self._conn.commit()
                except Exception:
                    logger.error(
                        'ERROR executing %s; for %s frame type %s',
                        sql, self._event, ftype, exc_info=True
                    )

    def analyze_event(self):
        """returns True or False whether to notify about this event"""
        for a in ANALYZERS:
            logger.debug('Running object detection with: %s', a)
            cls = a(self._event)
            cls.analyze()
            self._analyzers.append(cls)
            try:
                self._result_to_db(cls)
            except Exception:
                logger.critical(
                    'Exception writing analysis result to DB for %s %s',
                    self._event, a.__name__, exc_info=True
                )
        return True

    @property
    def suppression_reason(self):
        return self._suppression_reason

    @property
    def analyzers(self):
        return self._analyzers

    @property
    def new_object_labels(self):
        o = []
        for a in self.analyzers:
            o.extend(a.new_objects)
        return list(set(o))


def parse_args(argv):
    """Parse command line arguments with ArgumentParser."""
    p = argparse.ArgumentParser(description='handler for Motion events')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('-d', '--dry-run', dest='dry_run', action='store_true',
                   default=False, help='do not send notifications')
    p.add_argument('-f', '--foreground', dest='foreground', action='store_true',
                   default=False, help='log to foreground instead of file')
    p.add_argument('-E', '--event-id', dest='event_id', action='store',
                   type=int, help='Event ID', required=True)
    p.add_argument('-M', '--monitor-id', dest='monitor_id', action='store',
                   type=int, help='Monitor ID')
    p.add_argument('-C', '--cause', dest='cause', action='store', type=str,
                   help='event cause')
    args = p.parse_args(argv)
    return args


def populate_secrets():
    """Populate the ``CONFIG`` global from environment variables."""
    global CONFIG
    for varname in CONFIG.keys():
        if varname not in os.environ:
            raise RuntimeError(
                'ERROR: Variable %s must be set in environment' % varname
            )
        CONFIG[varname] = os.environ[varname]


def get_basicconfig_kwargs(args):
    """Return a dict of kwargs for :py:func:`logging.basicConfig`."""
    log_kwargs = {
        'level': logging.WARNING,
        'format': "[%(asctime)s %(levelname)s][%(process)d] %(message)s"
    }
    if not args.foreground:
        log_kwargs['filename'] = LOG_PATH
    # set logging level
    if args.verbose > 1 or (MIN_LOG_LEVEL is not None and MIN_LOG_LEVEL > 1):
        log_kwargs['level'] = logging.DEBUG
        log_kwargs['format'] = "%(asctime)s [%(process)d - %(levelname)s " \
                               "%(filename)s:%(lineno)s - %(name)s." \
                               "%(funcName)s() ] %(message)s"
    elif (
        args.verbose == 1 or (MIN_LOG_LEVEL is not None and MIN_LOG_LEVEL == 1)
    ):
        log_kwargs['level'] = logging.INFO
        log_kwargs['format'] = '%(asctime)s [%(process)d] %(levelname)s:' \
                               '%(name)s:%(message)s'
    return log_kwargs


def setup_logging(args):
    global logger
    kwargs = get_basicconfig_kwargs(args)
    logging.basicConfig(**kwargs)
    logger = logging.getLogger()
    if args.foreground:
        return
    # if not running in foreground, log to syslog also
    sh = SysLogHandler()
    sh.ident = 'zmevent_handler.py'
    sh.setFormatter(logging.Formatter(kwargs['format']))
    logger.addHandler(sh)


def run(args):
    # populate the event from ZoneMinder DB
    event = ZMEvent(args.event_id, args.monitor_id, args.cause)
    # ensure that this command is run by the user that owns the event
    evt_owner = os.stat(event.path).st_uid
    if os.geteuid() != evt_owner:
        raise RuntimeError(
            'This command may only be run by the user that owns %s: UID %s'
            ' (not UID %s)', event.path, evt_owner, os.geteuid()
        )
    logger.debug('Loaded event: %s', event.as_json)
    # wait for the event to finish - we wait up to 30s then continue
    event.wait_for_finish()
    result = {
        'event': event,
        'filters': [],
        'object_detections': []
    }
    # run filters on event
    logger.debug('Running filters on %s', event)
    for cls in EventFilter.__subclasses__():
        try:
            logger.debug('Filter: %s', cls)
            f = cls(event)
            f.run()
            result['filters'].append(f)
        except Exception:
            logger.critical(
                'Exception running filter %s on event %s',
                cls, event, exc_info=True
            )
    # run object detection on the event
    try:
        analyzer = ImageAnalysisWrapper(event)
        analyzer.analyze_event()
    except Exception:
        logger.critical(
            'ERROR running ImageAnalysisWrapper on event: %s', event,
            exc_info=True
        )
    raise NotImplementedError('send to HASS')


def main():
    # setsid so we can continue running even if caller dies
    os.setsid()
    # populate secrets from environment variables
    populate_secrets()
    # parse command line arguments
    args = parse_args(sys.argv[1:])
    # setup logging
    setup_logging(args)
    # initial log
    logger.warning(
        'Triggered; EventId=%s MonitorId=%s Cause=%s',
        args.event_id, args.monitor_id, args.cause
    )
    # run...
    run(args)


if __name__ == "__main__":
    main()
