#!/opt/homeassistant/appdaemon/bin/python
"""
Companion to zmevent_handler.py. Runs in a different venv with a CPU
(non-GPU) version of yolo3. Runs image analysis with this analyzer on all
frames that don't have it (but do from the main yolo analyzer), saves the
results to the DB, and sends an email with comparison information.

Mainly intended to find out, for my use case, how much worse the -tiny variant
is than the normal one.
"""

import sys
import os
import logging
import argparse
import json
import pymysql
from collections import defaultdict

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import ANALYSIS_TABLE_NAME, CONFIG
from zmevent_image_analysis import ImageAnalysisWrapper, AlternateYoloAnalyzer
from zmevent_models import ZMEvent

#: A list of the :py:class:`~.ImageAnalyzer` subclasses to use for each frame.
ANALYZERS = [AlternateYoloAnalyzer]

#: logger - this will be set in :py:func:`~.main` to log to either stdout/err
#: or a file depending on options
logger = None


class EventComparer(object):
    """
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
        analyzer = ImageAnalysisWrapper(event, ANALYZERS)
        analysis = analyzer.analyze_event()
        result['object_detections'] = analysis
    except Exception:
        logger.critical(
            'ERROR running ImageAnalysisWrapper on event: %s', event,
            exc_info=True
        )
    res_json = json.dumps(
        result, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
    )
    send_to_hass(res_json, event.EventId)
    """

    def __init__(self):
        logger.debug('Connecting to MySQL')
        self._conn = pymysql.connect(
            host='localhost', user=CONFIG['MYSQL_USER'],
            password=CONFIG['MYSQL_PASS'], db=CONFIG['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )

    def run(self):
        self.purge_analysis_table()
        # find the events and frames we want to analyze
        to_analyze = self._events_to_analyze()
        results = {}
        # analyze each event
        for evt_id in to_analyze.keys():
            logger.info(
                'Analyzing %d Frames of EventId %d', len(to_analyze[evt_id]),
                evt_id
            )
            # load the event
            evt = ZMEvent(evt_id)
            # set FramesForAnalysis to the same ones as currently in the DB
            # for the GPU-based analyzer
            evt.FramesForAnalysis = {}
            for fid in to_analyze[evt_id]:
                evt.FramesForAnalysis[fid] = evt.AllFrames[fid]
            analyzer = ImageAnalysisWrapper(evt, ANALYZERS)
            results[evt_id] = analyzer.analyze_event()
            logger.debug('Done analyzing event %d', evt_id)
        # @TODO grab the YoloAnalyzer results for each event/frame
        # @TODO send an email with comparison information
        raise NotImplementedError(
            'REMOVE LIMIT from selection in _events_to_analyze'
        )

    def _events_to_analyze(self):
        """dict of EventId to list of FrameIds to analyze"""
        sql = 'SELECT EventId,FrameId FROM %s WHERE ' \
              'AnalyzerName="YoloAnalyzer" AND (EventId, FrameId) NOT IN ' \
              '(SELECT EventId, FrameId FROM %s WHERE ' \
              'AnalyzerName="AlternateYoloAnalyzer") LIMIT 3;' % (
                  ANALYSIS_TABLE_NAME, ANALYSIS_TABLE_NAME
              )
        results = defaultdict(list)
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s', sql)
            cursor.execute(sql)
            res = cursor.fetchall()
            logger.info('Found %d Frames to analyze', len(res))
            for r in res:
                results[r['EventId']].append(r['FrameId'])
            self._conn.commit()
        return dict(results)

    def purge_analysis_table(self):
        sql = 'DELETE FROM %s WHERE (EventId, FrameId) NOT IN ' \
              '(SELECT EventId, FrameId FROM Frames);' % ANALYSIS_TABLE_NAME
        with self._conn.cursor() as cursor:
            logger.info('EXECUTING: %s', sql)
            num_rows = cursor.execute(sql)
            logger.warning(
                'Purged %d rows from %s', num_rows, ANALYSIS_TABLE_NAME
            )
            self._conn.commit()


def parse_args(argv):
    """Parse command line arguments with ArgumentParser."""
    p = argparse.ArgumentParser(description='compare image analysis results')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
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
    # set logging level
    if args.verbose > 1:
        log_kwargs['level'] = logging.DEBUG
        log_kwargs['format'] = "%(asctime)s [%(process)d - %(levelname)s " \
                               "%(filename)s:%(lineno)s - %(name)s." \
                               "%(funcName)s() ] %(message)s"
    elif args.verbose == 1:
        log_kwargs['level'] = logging.INFO
        log_kwargs['format'] = '%(asctime)s [%(process)d] %(levelname)s:' \
                               '%(name)s:%(message)s'
    return log_kwargs


def setup_logging(args):
    global logger
    kwargs = get_basicconfig_kwargs(args)
    logging.basicConfig(**kwargs)
    logger = logging.getLogger()


def main():
    # populate secrets from environment variables
    populate_secrets()
    # parse command line arguments
    args = parse_args(sys.argv[1:])
    # setup logging
    setup_logging(args)
    EventComparer().run()


if __name__ == "__main__":
    main()
