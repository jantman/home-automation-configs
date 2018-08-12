"""
This is my ZoneMinder alarm/event handler app. It works with the ``zmevent_*``
Python modules in the ``zoneminder/`` directory, as well as with
``alarm_handler.py``.

NOTE that ZoneMinder and HASS **must** be running on the same machine, or at
least this app must have access to the ZoneMinder event directory mounted at
the same path.

All configuration is in constants near the top of the file.

# Dependencies

- requests, which appdaemon should provide

# Important Notes

- This script retrieves secrets directly from the HASS ``secrets.yaml`` file.
The user it runs as must be able to read that file. The path to the HASS
configuration directory is read from the HASS API in
``AlarmHandler._get_hass_secrets()`` via the ``conf_dir`` key of the return
value of ``appdaemon.plugins.hass.hassapi.Hass.get_hass_config()`` and then
``secrets.yaml`` in that file is read and loaded. The expected secrets.yaml
keys are defined in ``AlarmHandler._get_hass_secrets()``.

# Highly Custom Bits

- Notifications via Pushover (direct to API, for image attachments)
- Notifications via Email (SMTP to GMail, sent from this app)

# Features

- Disregard event if alarm is "Disarmed".
- Disregard event if there were no objects detected in any frame.
- Otherwise:
  - Send Pushover notification with best analyzed frame
  - Send Email notification with all analyzed frames
"""

import logging
import os
import requests
import appdaemon.plugins.hass.hassapi as hass
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from yaml import load as load_yaml

from sane_app_logging import SaneLoggingApp
from alarm_handler import ALARM_STATE_SELECT_ENTITY, HOME, AWAY, DISARMED

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False


class ZMEventAlarmHandler(hass.Hass, SaneLoggingApp):
    """
    ZoneMinder Alarm Handler AppDaemon app.

    See module docstring for further info.
    """

    def initialize(self):
        """
        Initialize the app.

        Setup logging and some instance variables. Get secrets from HASS
        ``secrets.yaml``. Setup event listener
        """
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing ZMEventAlarmHandler...")
        self._hass_secrets = self._get_hass_secrets()
        self._log.debug('listen_event(CUSTOM_ALARM_STATE_SET)')
        self.listen_event(
            self._handle_alarm_event, event='ZM_ALARM'
        )
        self._log.info('Done initializing AlarmHandler')

    @property
    def alarm_state(self):
        """Return the string state of the alarm_state input select."""
        return self.get_state(ALARM_STATE_SELECT_ENTITY)

    def _get_hass_secrets(self):
        """
        Return the dictionary contents of HASS ``secrets.yaml``.
        """
        # get HASS configuration from its API
        apiconf = self.get_hass_config()
        # formulate the absolute path to HASS secrets.yaml
        conf_path = os.path.join(apiconf['config_dir'], 'secrets.yaml')
        self._log.debug('Reading hass secrets from: %s', conf_path)
        # load the YAML
        with open(conf_path, 'r') as fh:
            conf = load_yaml(fh, Loader=Loader)
        self._log.debug('Loaded secrets.')
        # verify that the secrets we need are present
        assert 'pushover_api_key' in conf
        assert 'pushover_user_key' in conf
        assert 'amcrest_username' in conf
        assert 'amcrest_password' in conf
        assert 'gmail_username' in conf
        assert 'gmail_password' in conf
        assert 'zm_url_base' in conf
        # return the full dict
        return conf

    def _handle_alarm_event(self, event_name, data, _):
        """
        Handle the ZM_ALARM event.

        event type: ZM_ALARM
        data: dict from ``zmevent_handler.py``
        """
        self._log.debug('Got %s event data=%s', event_name, data)
        if event_name != 'ZM_ALARM':
            self._log.error(
                'Got event of improper type: %s', event_name
            )
        if self.alarm_state == DISARMED:
            self._log.info(
                'Ignoring ZM_ALARM for Event %s - alarm disarmed',
                data['event']['EventId']
            )
            return
        if max([len(x['detections']) for x in data['object_detections']]) == 0:
            self._log.info(
                'Ignoring ZM_ALARM for Event %s - no objects detected',
                data['event']['EventId']
            )
            return
        if self.detections_in_street(data['object_detections']):
            self._log.info(
                'Ignoring ZM_ALARM for Event %s - all objects in Street zones',
                data['event']['EventId']
            )
            return
        # else our alarm isn't disarmed and we have some objects detected
        img = self._primary_detection_for_event(data)
        subject = 'ZoneMinder Alarm on %s - %s' % (
            data['event']['Monitor']['Name'], self.detection_str(img)
        )
        if self.get_state('input_boolean.cameras_silent') == 'on':
            self._log.warning(
                'Suppressing pushover notification - '
                'input_boolean.cameras_silent is on'
            )
        else:
            self._do_notify_pushover(subject, data, img)
        self._do_notify_email(subject, data)

    def detections_in_street(self, detections):
        zones = []
        for frame in detections:
            for det in frame['detections']:
                zones.extend([k for k in det['zones'].keys()])
        return all([x.startswith('Street') for x in zones])

    @staticmethod
    def detection_str(img):
        if len(img['detections']) == 0:
            return '(no objects detected)'
        s = []
        for d in sorted(
            img['detections'], key=lambda x: x['score'], reverse=True
        ):
            s.append('%s (%d%%; %s)' % (
                d['label'], d['score'] * 100,
                '/'.join(
                    sorted(
                        d['zones'], key=lambda x: d['zones'][x], reverse=True
                    )
                )
            ))
        return '; '.join(s)

    def _primary_detection_for_event(self, data):
        # let's just use the one with the most object detections...
        return sorted(
            data['object_detections'], key=lambda x: len(x['detections'])
        )[-1]

    def _do_notify_pushover(self, subject, data, primary_image):
        """Build Pushover API request arguments and call _send_pushover"""
        message = '%s - %.2f seconds, %d alarm frames; Scores: total=%d ' \
                  'avg=%d max=%d' % (
            data['event']['Notes'], data['event']['Length'],
            data['event']['AlarmFrames'], data['event']['TotScore'],
            data['event']['AvgScore'], data['event']['MaxScore']
        )
        url = '%sindex.php?view=event&eid=%s' % (
            self._hass_secrets['zm_url_base'],
            data['event']['EventId']
        )
        d = {
            'data': {
                'token': self._hass_secrets['pushover_api_key'],
                'user': self._hass_secrets['pushover_user_key'],
                'title': subject,
                'message': message,
                'url': url,
                'retry': 300,  # 5 minutes
                'sound': 'siren'
            },
            'files': {}
        }
        image = primary_image['output_path']
        self._log.info(
            'Sending Pushover notification with image: %s (image: %s)', d,
            image
        )
        d['files']['attachment'] = (
            os.path.basename(image), open(image, 'rb'), 'image/jpeg'
        )
        self._send_pushover(d)

    def _send_pushover(self, params):
        """
        Send the actual Pushover notification.

        We do this directly with ``requests`` because python-pushover still
        doesn't have support for images or some other API options.
        """
        url = 'https://api.pushover.net/1/messages.json'
        self._log.debug('Sending Pushover notification')
        r = requests.post(url, **params)
        self._log.debug(
            'Pushover POST response HTTP %s: %s', r.status_code, r.text
        )
        r.raise_for_status()
        if r.json()['status'] != 1:
            raise RuntimeError('Error response from Pushover: %s', r.text)
        self._log.info('Pushover Notification Success: %s', r.text)

    def _do_notify_email(self, subject, data):
        addr = self._hass_secrets['gmail_username']
        index_url = '%sindex.php' % self._hass_secrets['zm_url_base']
        msg = EmailNotifier(subject, data, addr, index_url).build_message()
        self._log.debug('Connecting to SMTP on smtp.gmail.com:587')
        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(
            self._hass_secrets['gmail_username'],
            self._hass_secrets['gmail_password']
        )
        self._log.info('Sending mail From=%s To=%s', addr, addr)
        s.sendmail(addr, addr, msg)
        self._log.info('EMail sent.')
        s.quit()


class EmailNotifier(object):
    """Send specially-formatted HTML email notification for an event."""

    def __init__(self, subject, data, addr, index_url):
        self.subject = subject
        self.data = data
        self.addr = addr
        self.index_url = index_url

    def build_message(self):
        """
        Build the email message; return a string email message.

        :return: email to send
        :rtype: str
        """
        e = self.data['event']
        msg = MIMEMultipart()
        msg['Subject'] = 'ZoneMinder: Alarm - %s-%s - %s ' \
                         '(%s sec, t%s/m%s/a%s)' % (
            e['Monitor']['Name'], e['EventId'], e['Notes'], e['Length'],
            e['TotScore'], e['MaxScore'], e['AvgScore']
        )
        msg['From'] = self.addr
        msg['To'] = self.addr
        html = '<html><head></head><body>\n'
        html += '<p>ZoneMinder has detected an alarm:</p>\n'
        html += '<table style="border-spacing: 0px; box-shadow: 5px 5px 5px ' \
                'grey; border-collapse:separate; border-radius: 7px;">\n'
        html += self._table_rows([
            [
                'Monitor',
                '<a href="%s?view=watch&mid=%s">%s (%s)</a>' % (
                    self.index_url, e['MonitorId'], e['Monitor']['Name'],
                    e['MonitorId']
                )
            ],
            [
                'Event',
                '<a href="%s?view=event&mid=%s&eid=%s">%s (%s)</a>' % (
                    self.index_url, e['MonitorId'], e['EventId'], e['Name'],
                    e['EventId']
                )
            ],
            ['Cause', e['Cause']],
            ['Notes', e['Notes']],
            ['Length', e['Length']],
            ['Start Time', e['StartTime']],
            ['Frames', '%s (%s alarm)' % (e['Frames'], e['AlarmFrames'])],
            [
                'Best Image',
                '<a href="%s?view=frame&mid=%s&eid=%s&fid=%s">Frame %s</a>' % (
                    self.index_url, e['MonitorId'], e['EventId'],
                    e['BestFrameId'], e['BestFrameId']
                )
            ],
            ['Scores', '%s Total / %s Max / %s Avg' % (
                e['TotScore'], e['MaxScore'], e['AvgScore']
            )],
            [
                'Live Monitor',
                '<a href="%s?view=watch&mid=%s">%s Live View</a>' % (
                    self.index_url, e['MonitorId'], e['Monitor']['Name']
                )
            ]
        ])
        html += '</table>\n'
        # BEGIN image analysis
        analyzers = list(set([
            d['analyzer_name'] for d in self.data['object_detections']
        ]))
        for a in analyzers:
            frames = sorted(
                [
                    x for x in self.data['object_detections']
                    if x['analyzer_name'] == a
                ],
                key=lambda x: x['FrameId']
            )
            html += '<p>%s Object Detection</p>\n' % a
            html += '<table style="border-spacing: 0px; box-shadow: 5px 5px ' \
                    '5px grey; border-collapse:separate; ' \
                    'border-radius: 7px;">\n'
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
                    '</tr>\n'
            for f in frames:
                html += self._analyzer_table_row(f)
            html += '</table>\n'
        # END image analysis
        html += '</body></html>\n'
        msg.attach(MIMEText(html, 'html'))
        for d in sorted(
            self.data['object_detections'], key=lambda x: x['FrameId']
        ):
            msg.attach(
                MIMEImage(
                    open(d['output_path'], 'rb').read(),
                    name=os.path.basename(d['output_path'])
                )
            )
        return msg.as_string()

    def _analyzer_table_row(self, frame):
        s = ''
        td = '<td style="border: 1px solid #a1bae2; text-align: center; ' \
             'padding: 5px;"%s>%s</td>\n'
        s += '<tr>'
        dets = sorted(
            frame['detections'], reverse=True, key=lambda x: x['score']
        )
        if len(dets) == 0:
            s += td % ('', frame['FrameId'])
            s += td % ('', '%.2f sec' % frame['runtime'])
            s += td % ('', 'None')
            s += '</tr>'
            return s
        s += td % (' rowspan="%d"' % len(dets), frame['FrameId'])
        s += td % (' rowspan="%d"' % len(dets), '%.2f sec' % frame['runtime'])
        zoneinfo = [
            '%s=%d%%' % (x, dets[0]['zones'][x]) for x in
            sorted(
                dets[0]['zones'], key=lambda x: dets[0]['zones'][x],
                reverse=True
            )
        ]
        s += td % (
            '',
            '%s (%.2f%%) %s (x=%d y=%d w=%d h=%d)' % (
                dets[0]['label'], dets[0]['score'] * 100,
                '/'.join(zoneinfo),
                dets[0]['x'], dets[0]['y'], dets[0]['w'], dets[0]['h']
            )
        )
        s += '</tr>'
        for d in dets[1:]:
            s += '<tr>'
            s += td % (
                '',
                '%s (%.2f%%) %s (x=%d y=%d w=%d h=%d)' % (
                    d['label'], d['score'],
                    '/'.join(
                        sorted(
                            d['zones'], key=lambda x: d['zones'][x],
                            reverse=True
                        )
                    ),
                    d['x'], d['y'], d['w'], d['h']
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
