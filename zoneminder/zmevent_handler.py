#!/usr/bin/env python3

import sys
import os
from datetime import datetime
import requests
import time
import logging
import argparse
import pymysql
import json
from decimal import Decimal
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

from PIL import Image

sys.path.append('/opt/home-automation-configs/zoneminder')

from zmevent_image_analysis import YoloAnalyzer
ANALYZERS = [YoloAnalyzer]

logger = None
LOG_PATH = '/var/cache/zoneminder/temp/zmevent_handler.log'
MIN_LOG_LEVEL = 1

ANALYSIS_TABLE_NAME = 'zmevent_handler_ImageAnalysis'

EVENTS_PATH = '/usr/share/zoneminder/www/events'

# These are populated from environment variables; see populate_secrets()
CONFIG = {
    'MYSQL_DB': None,
    'MYSQL_USER': None,
    'MYSQL_PASS': None,
    'BASE_URL': None,
    'PUSHOVER_APIKEY': None,
    'PUSHOVER_USERKEY': None,
    'EMAIL_FROM': None,
    'EMAIL_TO': None
}


class DateSafeJsonEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, 'as_dict'):
            return obj.as_dict
        if hasattr(obj, 'as_json'):
            return {
                x: getattr(obj, x) for x in vars(obj) if x[0].isupper()
            }
        return json.JSONEncoder.default(self, obj)


class PushoverNotifier(object):

    def __init__(self, zmevent, analyzer, dry_run=False):
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

    def __init__(self, zmevent, analyzer, dry_run=False):
        self._event = zmevent
        self._analyzer = analyzer
        self._dry_run = dry_run

    def build_message(self, suppression_reason=None):
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
        with open('/etc/ssmtp/ssmtp.conf', 'r') as fh:
            lines = fh.readlines()
        items = {
            x.split('=', 1)[0]: x.split('=', 1)[1] for x in lines
        }
        return items

    def build_and_send(self, suppression_reason=None):
        self.send_message(
            self.build_message(suppression_reason=suppression_reason)
        )


class EventFilter(object):

    def __init__(self, event):
        self._event = event
        self._should_notify = True
        self._reason = []
        self._suffix = None

    def run(self):
        self._filter_ir_switch()

    def _filter_ir_switch(self):
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
        return self._should_notify

    @property
    def reason(self):
        if len(self._reason) == 0:
            return None
        elif len(self._reason) == 1:
            return self._reason[0]
        return '; '.join(self._reason)

    @property
    def suffix(self):
        return self._suffix


class Monitor(object):

    def __init__(self, **kwargs):
        self.AlarmFrameCount = None
        self.ControlAddress = None
        self.ControlDevice = None
        self.ControlId = None
        self.Controllable = None
        self.Enabled = None
        self.EventPrefix = None
        self.Function = None
        self.Height = None
        self.Host = None
        self.Id = None
        self.ImageBufferCount = None
        self.LinkedMonitors = None
        self.Method = None
        self.Name = None
        self.Path = None
        self.Port = None
        self.PostEventCount = None
        self.PreEventCount = None
        self.Protocol = None
        self.RefBlendPerc = None
        self.SectionLength = None
        self.SignalCheckColour = None
        self.Type = None
        self.WebColour = None
        self.Width = None
        self.Zones = {}
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def __repr__(self):
        return '<Monitor(MonitorId=%d)>' % self.Id

    @property
    def as_json(self):
        d = {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }
        return json.dumps(
            d, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
        )


class FrameStats(object):

    def __init__(self, **kwargs):
        self.AlarmPixels = None
        self.BlobPixels = None
        self.Blobs = None
        self.EventId = None
        self.FilterPixels = None
        self.FrameId = None
        self.MaxBlobSize = None
        self.MaxX = None
        self.MaxY = None
        self.MinBlobSize = None
        self.MinX = None
        self.MinY = None
        self.MonitorId = None
        self.PixelDiff = None
        self.Score = None
        self.ZoneId = None
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def __repr__(self):
        return '<FrameStats(FrameId=%d, EventId=%d, ZoneId=%s)>' % (
            self.FrameId, self.EventId, self.ZoneId
        )

    @property
    def as_json(self):
        d = {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }
        return json.dumps(
            d, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
        )


class Frame(object):

    def __init__(self, **kwargs):
        self.Id = None
        self.EventId = None
        self.FrameId = None
        self.Delta = None
        self.Score = None
        self.TimeStamp = None
        self.Type = None
        self.Stats = {}
        self.event = None
        self._image = None
        self._is_color = None
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def __repr__(self):
        return '<Frame(Id=%d, EventId=%d, FrameId=%s)>' % (
            self.Id, self.EventId, self.FrameId
        )

    @property
    def as_dict(self):
        d = {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }
        d['frame_filename'] = self.filename
        d['frame_path'] = self.path
        return d

    @property
    def as_json(self):
        return json.dumps(
            self.as_json, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
        )

    @property
    def filename(self):
        return self.event.frame_fmt % self.FrameId

    @property
    def path(self):
        return os.path.join(self.event.path, self.filename)

    @property
    def is_color(self):
        if self._is_color is not None:
            return self._is_color
        img = self.image
        logger.debug('Finding if image is color or not for %s', self)
        bands = img.split()
        histos = [x.histogram() for x in bands]
        if histos[1:] == histos[:-1]:
            self._is_color = False
        else:
            self._is_color = True
        logger.info(
            'Frame %s is_color=%s based on histograms of bands',
            self, self._is_color
        )
        return self._is_color

    @property
    def image(self):
        if self._image is not None:
            return self._image
        logger.debug('Loading image for %s from: %s', self, self.path)
        self._image = Image.open(self.path)
        return self._image


class MonitorZone(object):

    def __init__(self, **kwargs):
        self.AlarmRGB = None
        self.Area = None
        self.CheckMethod = None
        self.Coords = None
        self.ExtendAlarmFrames = None
        self.FilterX = None
        self.FilterY = None
        self.Id = None
        self.MaxAlarmPixels = None
        self.MaxBlobPixels = None
        self.MaxBlobs = None
        self.MaxFilterPixels = None
        self.MaxPixelThreshold = None
        self.MinAlarmPixels = None
        self.MinBlobPixels = None
        self.MinBlobs = None
        self.MinFilterPixels = None
        self.MinPixelThreshold = None
        self.MonitorId = None
        self.Name = None
        self.NumCoords = None
        self.OverloadFrames = None
        self.Type = None
        self.Units = None
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def __repr__(self):
        return '<MonitorZone(MonitorId=%d, Id=%s)>' % (
            self.MonitorId, self.Id
        )

    @property
    def as_json(self):
        d = {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }
        return json.dumps(
            d, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
        )


class ZMEvent(object):

    def __init__(self, event_id, monitor_id=None, cause=None):
        self.EventId = event_id
        self.MonitorId = monitor_id
        self.Cause = cause
        self.AlarmFrames = None
        self.Archived = None
        self.AvgScore = None
        self.EndTime = None
        self.Frames = None
        self.Height = None
        self.Length = None
        self.MaxScore = None
        self.Name = None
        self.Notes = None
        self.StartTime = None
        self.TotScore = None
        self.Width = None
        self.BestFrame = None
        self.FirstFrame = None
        self.LastFrame = None

        self.Monitor = None
        self.AllFrames = {}

        self.frame_num_padding = None
        self.frame_fmt = None
        self.zm_url = None
        self.path = None

        self._conn = pymysql.connect(
            host='localhost', user=CONFIG['MYSQL_USER'],
            password=CONFIG['MYSQL_PASS'], db=CONFIG['MYSQL_DB'],
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
        )
        self._populate()
        if self.is_finished:
            self._conn.close()

    def __repr__(self):
        return '<Event(EventId=%d, MonitorId=%d)>' % (
            self.EventId, self.MonitorId
        )

    @property
    def as_json(self):
        d = {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }
        return json.dumps(
            d, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
        )

    def _query_and_return(self, sql, args, onlyone=True, none_ok=False):
        if not isinstance(args, type([])):
            args = [args]
        with self._conn.cursor() as cursor:
            logger.debug(
                'EXECUTE: %s ARGS: %s', sql,
                ', '.join(['%s (%s)' % (x, type(x)) for x in args])
            )
            cursor.execute(sql, args)
            if onlyone:
                result = cursor.fetchone()
                if result is None and not none_ok:
                    raise RuntimeError(
                        'ERROR: No row in DB for SQL: %s\nargs: %s' % (
                            sql, args
                        )
                    )
            else:
                result = cursor.fetchall()
                if (result is None or len(result) == 0) and not none_ok:
                    raise RuntimeError(
                        'ERROR: No row in DB for SQL: %s\nargs: %s' % (
                            sql, args
                        )
                    )
        return result

    def _class_from_sql(
        self, klass, attr, sql, args, onlyone=True, none_ok=False,
        key_attr=None, extra_args={}
    ):
        result = self._query_and_return(
            sql, args, onlyone=onlyone, none_ok=none_ok
        )
        if onlyone:
            result.update(extra_args)
            setattr(self, attr, klass(**result))
            return
        if key_attr is None:
            tmp = []
            for x in result:
                cls_args = x
                cls_args.update(extra_args)
                tmp.append(klass(**cls_args))
            setattr(self, attr, tmp)
            return
        tmp = {}
        for x in result:
            cls_args = x
            cls_args.update(extra_args)
            tmp[x[key_attr]] = klass(**cls_args)
        setattr(self, attr, tmp)

    def _populate(self):
        logger.info('Populating from DB...')
        # Query-once items:
        if self.frame_num_padding is None:
            self.frame_num_padding = int(self._query_and_return(
                'SELECT `Value` FROM `Config` WHERE '
                '`Name`="ZM_EVENT_IMAGE_DIGITS";',
                []
            )['Value'])
        logger.debug('Found EVENT_IMAGE_DIGITS as: %s' % self.frame_num_padding)
        self.frame_fmt = '%.{fp}d-capture.jpg'.format(fp=self.frame_num_padding)
        if self.zm_url is None:
            self.zm_url = self._query_and_return(
                'SELECT `Value` FROM `Config` WHERE Name="ZM_URL";',
                []
            )['Value']
        logger.debug('ZM_URL: %s', self.zm_url)
        # Event itself
        res = self._query_and_return(
            'SELECT * FROM `Events` WHERE `Id`=%s;', self.EventId
        )
        for k, v in res.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.path = os.path.join(
            EVENTS_PATH, '%s' % self.MonitorId,
            self.StartTime.strftime('%y/%m/%d/%H/%M/%S')
        )
        logger.debug(self.as_json)
        # Other items
        self._class_from_sql(
            Monitor, 'Monitor',
            'SELECT * FROM `Monitors` WHERE `Id`=%s;',
            self.MonitorId
        )
        self._class_from_sql(
            Frame, 'AllFrames',
            'SELECT * FROM Frames WHERE EventId=%s;',
            self.EventId,
            onlyone=False, key_attr='FrameId', none_ok=True,
            extra_args={'event': self}
        )
        results = self._query_and_return(
            'SELECT * FROM Stats WHERE EventId=%s;',
            self.EventId,
            onlyone=False, none_ok=True
        )
        for stat in results:
            if stat['FrameId'] not in self.AllFrames:
                continue
            self.AllFrames[stat['FrameId']].Stats[
                stat['ZoneId']
            ] = FrameStats(**stat)
        results = self._query_and_return(
            'SELECT * FROM Zones WHERE MonitorId=%s;',
            self.MonitorId, onlyone=False, none_ok=True
        )
        if len(self.AllFrames) > 0:
            self.FirstFrame = self.AllFrames[
                min(self.AllFrames.keys())
            ]
            self.LastFrame = self.AllFrames[
                max(self.AllFrames.keys())
            ]
            self.BestFrame = sorted(
                self.AllFrames.values(), key=lambda x: (x.Score, x.FrameId)
            )[-1]
        for zone in results:
            self.Monitor.Zones[zone['Id']] = MonitorZone(**zone)
        logger.info('Done populating.')
        self._conn.commit()

    @property
    def is_finished(self):
        return self.EndTime is not None

    def wait_for_finish(self, timeout_sec=30):
        if self.is_finished:
            return
        logger.info('Waiting up to %ds for event to finish...', timeout_sec)
        t = time.time()
        end_time = t + timeout_sec
        while t <= end_time:
            self._populate()
            if self.is_finished:
                logger.info('Event ended.')
                return
            time.sleep(2)
        logger.warning('%s did not end in %ds' % (self, timeout_sec))

    def add_suffix_to_name(self, suffix):
        if suffix is None:
            logger.error('Cannot add None suffix to event name!')
            return
        newname = '%s_SUP:%s' % (self.Name, suffix)
        logger.warning(
            'Renaming Event %s from "%s" to "%s"',
            self.EventId, self.Name, newname
        )
        r = requests.put(
            'http://localhost/zm/api/events/%s.json' % self.EventId,
            data={'Event[Name]': newname}
        )
        r.raise_for_status()
        assert r.json()['message'] == 'Saved'
        logger.info('%s renamed', self)


class ImageAnalysisWrapper(object):

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
    global CONFIG
    for varname in CONFIG.keys():
        if varname not in os.environ:
            raise RuntimeError(
                'ERROR: Variable %s must be set in environment' % varname
            )
        CONFIG[varname] = os.environ[varname]


def get_basicconfig_kwargs(args):
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
    os.setsid()
    global logger
    args = parse_args(sys.argv[1:])
    logging.basicConfig(**get_basicconfig_kwargs(args))
    populate_secrets()
    logger = logging.getLogger()
    logger.warning(
        'Triggered; EventId=%s MonitorId=%s Cause=%s',
        args.event_id, args.monitor_id, args.cause
    )
    event = ZMEvent(args.event_id, args.monitor_id, args.cause)
    analyzer = ImageAnalysisWrapper(event)
    evt_owner = os.stat(event.path).st_uid
    if os.geteuid() != evt_owner:
        raise RuntimeError(
            'This command may only be run by the user that owns %s: UID %s'
            ' (not UID %s)', event.path, evt_owner, os.geteuid()
        )
    logger.debug('Loaded event: %s', event.as_json)
    event.wait_for_finish()
    if not event.is_finished:
        logger.warning('Event did not finish after 30s')
        event.wait_for_finish(timeout_sec=240)
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
