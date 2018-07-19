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
from zmevent_db import ZMEvent, Monitor, MonitorZone, FrameStats, Frame

#: A list of the :py:class:`~.ImageAnalyzer` subclasses to use for each frame.
ANALYZERS = [YoloAnalyzer]

#: logger - this will be set in :py:func:`~.main` to log to either stdout/err
#: or a file depending on options
logger = None


class PushoverNotifier(object):
    """Send specially-formatted Pushover notification for an event."""

    def __init__(self, zmevent, analyzer, dry_run=False):
        """
        Initialize PushoverNotifier

        :param zmevent: the event to notify for
        :type zmevent: ZMEvent
        :param analyzer: the image analysis wrapper
        :type analyzer: ImageAnalysisWrapper
        :param dry_run: whether or not this is a dry run
        :type dry_run: bool
        """
        self._event = zmevent
        self._analyzer = analyzer
        self._dry_run = dry_run

    def generate(self):
        """generate params for the POST to pushover"""
        logger.debug('Generating parameters for notification...')
        e = self._event
        d = {
            'data': {
                'token': CONFIG['PUSHOVER_APIKEY'],
                'user': CONFIG['PUSHOVER_USERKEY'],
                'title': 'ZoneMinder Alarm on %s (%s) Event %s' % (
                    e.Monitor.Name,
                    ', '.join(self._analyzer.analyzers[0].new_objects),
                    e.EventId
                ),
                'message': '%s - %.2f seconds, %d alarm frames - Scores: '
                           'total=%d avg=%d max=%d' % (
                               e.Notes, e.Length, e.AlarmFrames,
                               e.TotScore, e.AvgScore, e.MaxScore
                           ),
                'timestamp': time.mktime(e.StartTime.timetuple()),
                'sound': 'siren'
            },
            'files': {}
        }
        cls = self._analyzer.analyzers[0]
        k = cls.frames['Best'].get('analyzed')
        if k is not None:
            fname = '%s_%s_%s' % (
                'Best',
                cls.__class__.__name__,
                os.path.basename(k)
            )
            d['files']['attachment'] = (
                fname, open(k, 'rb').read(), 'image/jpeg'
            )
        else:
            d['files']['attachment'] = (
                e.BestFrame.path,
                open(e.BestFrame.path, 'rb'),
                'image/jpeg'
            )
        d['data']['url'] = '%s?view=event&mode=stream&mid=%s&eid=%s' % (
            CONFIG['BASE_URL'], e.MonitorId, e.EventId
        )
        d['data']['retry'] = 300  # 5 minutes
        return d

    def send(self, params):
        """send to pushover"""
        url = 'https://api.pushover.net/1/messages.json'
        if self._dry_run:
            logger.warning('DRY RUN - Would POST to %s: %s', url, params)
            return
        logger.debug('Sending Pushover notification; params=%s', params)
        r = requests.post(url, **params)
        logger.debug(
            'Pushover POST response HTTP %s: %s', r.status_code, r.text
        )
        r.raise_for_status()
        if r.json()['status'] != 1:
            raise RuntimeError('Error response from Pushover: %s', r.text)
        logger.warning('Pushover Notification Success: %s', r.text)

    def generate_and_send(self):
        """generate params and POST to pushover"""
        self.send(self.generate())


class EmailNotifier(object):
    """Send specially-formatted HTML email notification for an event."""

    def __init__(self, zmevent, analyzer, dry_run=False):
        """
        Initialize EmailNotifier

        :param zmevent: the event to notify for
        :type zmevent: ZMEvent
        :param analyzer: the image analysis wrapper
        :type analyzer: ImageAnalysisWrapper
        :param dry_run: whether or not this is a dry run
        :type dry_run: bool
        """
        self._event = zmevent
        self._analyzer = analyzer
        self._dry_run = dry_run

    def build_message(self, suppression_reason=None):
        """
        Build the email message; return a string email message.

        :param suppression_reason: if the event is being suppressed, the string
          reason for it.
        :type suppression_reason: ``None`` or ``str``
        :return: email to send
        :rtype: str
        """
        e = self._event
        msg = MIMEMultipart()
        supp_text = ''
        if suppression_reason is not None:
            supp_text = 'SUPPRESSED '
        msg['Subject'] = 'ZoneMinder: %sAlarm - %s-%s - %s ' \
                         '(%s sec, t%s/m%s/a%s)' % (
            supp_text, e.Monitor.Name, e.EventId, e.Notes, e.Length,
            e.TotScore, e.MaxScore, e.AvgScore
        )
        msg['From'] = CONFIG['EMAIL_FROM']
        msg['To'] = CONFIG['EMAIL_TO']
        html = '<html><head></head><body>\n'
        if suppression_reason is None:
            html += '<p>ZoneMinder has detected an alarm:</p>\n'
        else:
            html += '<p>ZoneMinder detected an alarm that was ' \
                    '<strong>suppressed</strong> because: <strong>%s</strong>' \
                    '</p>\n' % suppression_reason
        html += '<table style="border-spacing: 0px; box-shadow: 5px 5px 5px ' \
                'grey; border-collapse:separate; border-radius: 7px;">\n'
        html += self._table_rows([
            [
                'Monitor',
                '<a href="%s?view=watch&mid=%s">%s (%s)</a>' % (
                    CONFIG['BASE_URL'], e.MonitorId, e.Monitor.Name,
                    e.MonitorId
                )
            ],
            [
                'Event',
                '<a href="%s?view=event&mid=%s&eid=%s">%s (%s)</a>' % (
                    CONFIG['BASE_URL'], e.MonitorId, e.EventId, e.Name,
                    e.EventId
                )
            ],
            ['Cause', e.Cause],
            ['Notes', e.Notes],
            ['Length', e.Length],
            ['Start Time', e.StartTime],
            ['Frames', '%s (%s alarm)' % (len(e.AllFrames), e.AlarmFrames)],
            [
                'Best Image',
                '<a href="%s?view=frame&mid=%s&eid=%s&fid=%s">Frame %s</a>' % (
                    CONFIG['BASE_URL'], e.MonitorId, e.EventId,
                    e.BestFrame.FrameId, e.BestFrame.FrameId
                )
            ],
            ['Scores', '%s Total / %s Max / %s Avg' % (
                e.TotScore, e.MaxScore, e.AvgScore
            )],
            [
                'Live Monitor',
                '<a href="%s?view=watch&mid=%s">%s Live View</a>' % (
                    CONFIG['BASE_URL'], e.MonitorId, e.Monitor.Name
                )
            ]
        ])
        html += '</table>\n'
        # BEGIN image analysis
        html += '<p>Image Analysis Results</p>\n'
        html += '<p><strong>New Objects: %s</strong></p>\n' % ', '.join(
            self._analyzer.new_object_labels
        )
        html += '<table style="border-spacing: 0px; box-shadow: 5px 5px 5px ' \
                'grey; border-collapse:separate; border-radius: 7px;">\n'
        html += '<tr>' \
                '<th style="border: 1px solid #a1bae2; text-align: center; ' \
                'padding: 5px;">Class</th>\n' \
                '<th style="border: 1px solid #a1bae2; text-align: center; ' \
                'padding: 5px;">Runtime</th>\n' \
                '<th style="border: 1px solid #a1bae2; text-align: center; ' \
                'padding: 5px;">Results</th>\n' \
                '</tr>\n'
        for a in self._analyzer.analyzers:
            html += self._analyzer_table_row(a)
        html += '</table>\n'
        # END image analysis
        html += '</body></html>\n'
        msg.attach(MIMEText(html, 'html'))
        if self._dry_run:
            logger.warning('MESSAGE:\n%s', msg.as_string())
        if e.BestFrame.path != e.FirstFrame.path:
            if self._dry_run:
                logger.warning('Would attach: %s', e.FirstFrame.path)
            msg.attach(
                MIMEImage(
                    open(e.FirstFrame.path, 'rb').read(),
                    name='first_%s' % e.FirstFrame.filename
                )
            )
            for cls in self._analyzer.analyzers:
                k = cls.frames['First'].get('analyzed')
                if k is not None:
                    fname = '%s_%s_%s' % (
                        'First',
                        cls.__class__.__name__,
                        os.path.basename(k)
                    )
                    msg.attach(
                        MIMEImage(open(k, 'rb').read(), name=fname)
                    )
                    if self._dry_run:
                        logger.warning(
                            'Would attach: %s as "%s"', k, fname
                        )
        if self._dry_run:
            logger.warning('Would attach: %s', e.BestFrame.path)
        msg.attach(
            MIMEImage(
                open(e.BestFrame.path, 'rb').read(),
                name='best_%s' % e.BestFrame.filename
            )
        )
        for cls in self._analyzer.analyzers:
            k = cls.frames['Best'].get('analyzed')
            if k is not None:
                fname = '%s_%s_%s' % (
                    'Best',
                    cls.__class__.__name__,
                    os.path.basename(k)
                )
                msg.attach(
                    MIMEImage(open(k, 'rb').read(), name=fname)
                )
                if self._dry_run:
                    logger.warning(
                        'Would attach: %s as "%s"', k, fname
                    )
            k = cls.frames['Last'].get('analyzed')
            if k is not None:
                fname = '%s_%s_%s' % (
                    'Last',
                    cls.__class__.__name__,
                    os.path.basename(k)
                )
                msg.attach(
                    MIMEImage(open(k, 'rb').read(), name=fname)
                )
                if self._dry_run:
                    logger.warning(
                        'Would attach: %s as "%s"', k, fname
                    )
        return msg.as_string()

    def _analyzer_table_row(self, result):
        s = ''
        td = '<td style="border: 1px solid #a1bae2; text-align: center; ' \
             'padding: 5px;"%s>%s</td>\n'
        s += '<tr>'
        s += td % (' rowspan="3"', result.__class__.__name__)
        s += td % (' rowspan="3"', '%.2f sec' % result.runtime)
        content = '<strong>First:</strong><br />' + '<br />'.join(
            result.result['First']
        )
        s += td % ('', content)
        s += '</tr>'
        s += '<tr>'
        content = '<strong>Best:</strong><br />' + '<br />'.join(
            result.result['Best']
        )
        s += td % ('', content)
        s += '</tr>'
        s += '<tr>'
        content = '<strong>Last:</strong><br />' + '<br />'.join(
            result.result['Last']
        )
        s += td % ('', content)
        s += '</tr>'
        return s

    def _table_rows(self, data):
        s = ''
        td = '<td style="border: 1px solid #a1bae2; text-align: center; ' \
             'padding: 5px;">%s</td>\n'
        for row in data:
            s += '<tr>'
            s += td % row[0]
            s += td % row[1]
            s += '</tr>\n'
        return s

    def send_message(self, msg):
        """send the email message (notification)"""
        logger.debug('Connecting to SMTP on smtp.gmail.com:587')
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.ehlo()
        s.starttls()
        s.ehlo()
        creds = self._get_creds()
        s.login(creds['AuthUser'], creds['AuthPass'])
        if self._dry_run:
            logger.warning(
                'DRY RUN - Would send mail FROM=%s TO=%s',
                CONFIG['EMAIL_FROM'], CONFIG['EMAIL_TO']
            )
            s.quit()
            return
        logger.info(
            'Sending mail From=%s To=%s', CONFIG['EMAIL_FROM'],
            CONFIG['EMAIL_TO']
        )
        s.sendmail(CONFIG['EMAIL_FROM'], CONFIG['EMAIL_TO'], msg)
        logger.warning('EMail sent.')
        s.quit()

    def _get_creds(self):
        """retrieve GMail credentials from ssmtp.conf"""
        with open('/etc/ssmtp/ssmtp.conf', 'r') as fh:
            lines = fh.readlines()
        items = {
            x.split('=', 1)[0]: x.split('=', 1)[1] for x in lines
        }
        return items

    def build_and_send(self, suppression_reason=None):
        """build and then send the email notification"""
        self.send_message(
            self.build_message(suppression_reason=suppression_reason)
        )


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


def main():
    # setsid so calling process can continue without terminating
    os.setsid()
    # populate secrets
    populate_secrets()
    # setup logging
    global logger
    args = parse_args(sys.argv[1:])
    logging.basicConfig(**get_basicconfig_kwargs(args))
    logger = logging.getLogger()
    # initial log
    logger.warning(
        'Triggered; EventId=%s MonitorId=%s Cause=%s',
        args.event_id, args.monitor_id, args.cause
    )
    # populate the event
    event = ZMEvent(args.event_id, args.monitor_id, args.cause)
    # instantiate the analysis wrapper
    analyzer = ImageAnalysisWrapper(event)
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


if __name__ == "__main__":
    main()
