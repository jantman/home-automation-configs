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
from datetime import datetime
import pymysql
from collections import defaultdict
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from yaml import load as load_yaml

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

# Imports from this directory
from zmevent_config import ANALYSIS_TABLE_NAME, CONFIG, HASS_SECRETS_PATH
from zmevent_image_analysis import ImageAnalysisWrapper, AlternateYoloAnalyzer
from zmevent_models import ZMEvent

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

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
        _start = datetime.now()
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
            for frame_id in to_analyze[evt_id].keys():
                evt.FramesForAnalysis[
                    frame_id
                ] = evt.AllFrames[frame_id]
            analyzer = ImageAnalysisWrapper(evt, ANALYZERS)
            results[evt_id] = analyzer.analyze_event()
            logger.debug('Done analyzing event %d', evt_id)
        duration = datetime.now() - _start
        self._send_email(to_analyze, results, duration)
        raise NotImplementedError(
            'REMOVE LIMIT from selection in _events_to_analyze'
        )

    def _get_hass_secrets(self):
        """
        Return the dictionary contents of HASS ``secrets.yaml``.
        """
        logger.debug('Reading hass secrets from: %s', HASS_SECRETS_PATH)
        # load the YAML
        with open(HASS_SECRETS_PATH, 'r') as fh:
            conf = load_yaml(fh, Loader=Loader)
        logger.debug('Loaded secrets.')
        # verify that the secrets we need are present
        assert 'gmail_username' in conf
        assert 'gmail_password' in conf
        # return the full dict
        return conf

    def _send_email(self, to_analyze, results, duration):
        hass_secrets = self._get_hass_secrets()
        addr = hass_secrets['gmail_username']
        msg = EmailNotifier(to_analyze, results, duration, addr).build_message()
        logger.debug('Connecting to SMTP on smtp.gmail.com:587')
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(
            hass_secrets['gmail_username'], hass_secrets['gmail_password']
        )
        logger.info('Sending mail From=%s To=%s', addr, addr)
        s.sendmail(addr, addr, msg)
        logger.info('EMail sent.')
        s.quit()

    def _events_to_analyze(self):
        """dict of EventId to list of FrameIds to analyze"""
        sql = 'SELECT * FROM %s WHERE ' \
              'AnalyzerName="YoloAnalyzer" AND (EventId, FrameId) NOT IN ' \
              '(SELECT EventId, FrameId FROM %s WHERE ' \
              'AnalyzerName="AlternateYoloAnalyzer") LIMIT 3;' % (
                  ANALYSIS_TABLE_NAME, ANALYSIS_TABLE_NAME
              )
        results = defaultdict(dict)
        with self._conn.cursor() as cursor:
            logger.info('Executing: %s', sql)
            cursor.execute(sql)
            res = cursor.fetchall()
            logger.info('Found %d Frames to analyze', len(res))
            for r in res:
                results[r['EventId']][r['FrameId']] = r
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


class EmailNotifier(object):
    """Send specially-formatted HTML email notification for an event."""

    def __init__(self, to_analyze, results, duration, addr):
        self.to_analyze = to_analyze
        self.results = results
        self.duration = duration
        self.addr = addr

    def build_message(self):
        """
        Build the email message; return a string email message.

        :return: email to send
        :rtype: str
        """
        msg = MIMEMultipart()
        msg['Subject'] = 'Yolo Object Detection Comparison'
        msg['From'] = self.addr
        msg['To'] = self.addr
        html = '<html><head></head><body>\n'
        html += '<p>Object detection comparison for last day</p>\n'
        html += '<p>Total runtime: %s</p>\n' % self.duration
        for evt_id in sorted(
            self.results.keys(),
            key=lambda x: self.results[x].as_dict['FrameId']
        ):
            html += self._event_table(
                evt_id,
                self.results[evt_id],
                self.to_analyze[evt_id]
            )
        # END image analysis
        html += '</body></html>\n'
        msg.attach(MIMEText(html, 'html'))
        return msg.as_string()

    def _event_table(self, evt_id, odr_list, db_dict):
        html = '<p>Event %s</p>\n' % evt_id
        html += '<table style="border-spacing: 0px; box-shadow: 5px 5px ' \
                '5px grey; border-collapse:separate; ' \
                'border-radius: 7px;">\n'
        html += '<tr>' \
                '<th style="border: 1px solid #a1bae2; ' \
                'text-align: center; ' \
                'padding: 5px;">&nbsp;</th>\n' \
                '<th style="border: 1px solid #a1bae2; ' \
                'text-align: center; ' \
                'padding: 5px;" colspan="2">GPU Tiny</th>\n' \
                '<th style="border: 1px solid #a1bae2; ' \
                'text-align: center; ' \
                'padding: 5px;" colspan="2">CPU</th>\n' \
                '</tr>\n'
        html += '<tr>' \
                '<th style="border: 1px solid #a1bae2; ' \
                'text-align: center; ' \
                'padding: 5px;">Frame</th>\n' \
                '<th style="border: 1px solid #a1bae2; ' \
                'text-align: center; ' \
                'padding: 5px;">Runtime</th>\n' \
                '<th style="border: 1px solid #a1bae2; ' \
                'text-align: center; ' \
                'padding: 5px;">Results</th>\n' \
                '<th style="border: 1px solid #a1bae2; ' \
                'text-align: center; ' \
                'padding: 5px;">Runtime</th>\n' \
                '<th style="border: 1px solid #a1bae2; ' \
                'text-align: center; ' \
                'padding: 5px;">Results</th>\n' \
                '</tr>\n'
        for frm in sorted(odr_list, key=lambda x: x.as_dict['FrameId']):
            html += self._analyzer_table_row(
                frm, db_dict[frm.as_dict['FrameId']]
            )
        html += '</table>\n'
        return html

    def _analyzer_table_row(self, cpu_frm, tiny_frm_json):
        cpu_frm = cpu_frm.as_dict
        tiny_frm = json.loads(tiny_frm_json)
        s = ''
        td = '<td style="border: 1px solid #a1bae2; text-align: center; ' \
             'padding: 5px;"%s>%s</td>\n'
        s += '<tr>'
        cpu_dets = sorted(
            cpu_frm['detections'], reverse=True, key=lambda x: x._score
        )
        tiny_dets = sorted(
            tiny_frm['Results']['detections'], reverse=True,
            key=lambda x: x._score
        )
        if len(cpu_dets) == 0 and len(tiny_dets) == 0:
            s += td % ('', cpu_frm['FrameId'])
            s += td % ('', '%.2f sec' % tiny_frm['runtime'])
            s += td % ('', 'None')
            s += td % ('', '%.2f sec' % cpu_frm['runtime'])
            s += td % ('', 'None')
            s += '</tr>'
            return s
        s += td % ('', cpu_frm['FrameId'])
        s += td % ('', '%.2f sec' % tiny_frm['runtime'])
        s += td % (
            '',
            '<br />'.join(
                [
                    '%s (%.2f%%) x=%d y=%d w=%d h=%d' % (
                        x['label'], x['score'] * 100,
                        x['x'], x['y'], x['w'],
                        x['h']
                    )
                    for x in tiny_dets
                ]
            )
        )
        s += td % ('', '%.2f sec' % cpu_frm['runtime'])
        s += td % (
            '',
            '<br />'.join(
                [
                    '%s (%.2f%%) x=%d y=%d w=%d h=%d' % (
                        x['label'], x['score'] * 100,
                        x['x'], x['y'], x['w'],
                        x['h']
                    )
                    for x in cpu_dets
                ]
            )
        )
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
