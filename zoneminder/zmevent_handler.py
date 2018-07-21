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
"""

import sys
import os
import time
import logging
from logging.handlers import SysLogHandler
import argparse
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

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
from zmevent_db import ZMEvent

#: A list of the :py:class:`~.ImageAnalyzer` subclasses to use for each frame.
ANALYZERS = [YoloAnalyzer]

#: logger - this will be set in :py:func:`~.main` to log to either stdout/err
#: or a file depending on options
logger = None


class EventFilter(object):
    """
    Responsible for determining whether an Event should be notified on or not.

    Instantiate class and call :py:meth:`~.run`. After that, check the return
    value of the :py:attr:`~.should_notify` property.
    """

    def __init__(self, event):
        """
        Initialize EventFilter.

        :param event: the event to check
        :type event: ZMEvent
        """
        self._event = event
        self._should_notify = True
        self._reason = []
        self._suffix = None

    def run(self):
        """Test for all filter conditions, update should_notify."""
        self._filter_ir_switch()

    def _filter_ir_switch(self):
        """Determine if the camera switched from or to IR during this event."""
        f1 = self._event.FirstFrame
        f2 = self._event.LastFrame
        if f1.is_color and not f2.is_color:
            self._should_notify = False
            self._reason.append('Color to BW switch')
            self._suffix = 'Color2BW'
            return
        if not f1.is_color and f2.is_color:
            self._should_notify = False
            self._reason.append('BW to color switch')
            self._suffix = 'BW2Color'

    @property
    def should_notify(self):
        """
        Whether we should send (True) or suppress (False) a notification for
        this event.

        :returns: whether to send a notification or not
        :rtype: bool
        """
        return self._should_notify

    @property
    def reason(self):
        """
        Return the reason why notification should be suppressed or None.

        :return: reason why notification should be suppressed, or None
        :rtype: ``str`` or ``None``
        """
        if len(self._reason) == 0:
            return None
        elif len(self._reason) == 1:
            return self._reason[0]
        return '; '.join(self._reason)

    @property
    def suffix(self):
        """
        Return a suffix to append to the event name describing the suppression
        reason.

        :return: event suffix
        :rtype: str
        """
        return self._suffix


class ImageAnalysisWrapper(object):
    """Wraps calling the ``ANALYZER`` classes and storing their results."""

    def __init__(self, event):
        self._event = event
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
    # populate the event
    event = ZMEvent(args.event_id, args.monitor_id, args.cause)
    # ensure that this command is run by the user that owns the event
    evt_owner = os.stat(event.path).st_uid
    if os.geteuid() != evt_owner:
        raise RuntimeError(
            'This command may only be run by the user that owns %s: UID %s'
            ' (not UID %s)', event.path, evt_owner, os.geteuid()
        )
    logger.debug('Loaded event: %s', event.as_json)
    # instantiate the analysis wrapper
    analyzer = ImageAnalysisWrapper(event)
    # wait for the event to finish - we wait up to 30s then continue
    event.wait_for_finish()
    if not event.is_finished:
        logger.warning('Event did not finish after 30s')
    # run initial filter on the event; see if we should suppress it
    try:
        filter = EventFilter(event)
        filter.run()
        if not filter.should_notify:
            logger.warning(
                'Suppressing notification for event %s because of filter',
                event
            )
            EmailNotifier(
                event, analyzer, args.dry_run
            ).build_and_send(filter.reason)
            if args.dry_run:
                logger.warning('DRY RUN - would add suffix to event name: %s',
                               filter.suffix)
            else:
                event.add_suffix_to_name(filter.suffix)
            return
    except Exception:
        logger.critical(
            'ERROR filtering event: %s', event.as_json, exc_info=True
        )
        raise
    # run object detection on the event
    try:
        if not analyzer.analyze_event():
            logger.warning(
                'Suppressing notification for event %s because of image '
                'analysis', event
            )
            EmailNotifier(event, analyzer, args.dry_run).build_and_send(
                analyzer.suppression_reason
            )
            if args.dry_run:
                logger.warning('DRY RUN - would add suffix to event name: IA')
            else:
                event.add_suffix_to_name('IA')
            return
    except Exception:
        logger.critical(
            'ERROR running ImageAnalysisWrapper on event: %s', event.as_json,
            exc_info=True
        )
    # finally, if everything worked and the event wasn't suppressed, notify
    try:
        PushoverNotifier(event, analyzer, args.dry_run).generate_and_send()
    except Exception as ex:
        logger.critical(
            'ERROR sending pushover notification for event %s: %s',
            event.EventId, ex, exc_info=True
        )
    try:
        EmailNotifier(event, analyzer, args.dry_run).build_and_send()
    except Exception as ex:
        logger.critical(
            'ERROR sending email notification for event %s: %s',
            event.EventId, ex, exc_info=True
        )



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
    run(args)


if __name__ == "__main__":
    main()
