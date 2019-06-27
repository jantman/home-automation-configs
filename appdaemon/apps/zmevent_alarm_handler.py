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
value of ``appdaemon.plugins.hass.hassapi.Hass.get_plugin_config()`` and
then ``secrets.yaml`` in that file is read and loaded. The expected secrets.yaml
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

import os
import re
import time
import appdaemon.plugins.hass.hassapi as hass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

from sane_app_logging import SaneLoggingApp
from alarm_handler import ALARM_STATE_SELECT_ENTITY, HOME, AWAY, DISARMED
from pushover_notifier import PushoverNotifier

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False

#: List of monitor names to ignore when the alarm state is HOME
HOME_IGNORE_MONITORS = ['LRKitchen', 'OFFICE', 'BEDRM', 'HALL']

#: Path of a file that's touched every time the alarm changes state.
TRANSITION_FILE_PATH = '/tmp/alarm_last_state_transition'

#: Hoe many seconds to suppress ZM alarms after alarm state transition
TRANSITION_DELAY_SECONDS = 75


class ZMEventAlarmHandler(hass.Hass, SaneLoggingApp, PushoverNotifier):
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

    @property
    def _in_transition_period(self):
        """
        If we are within ``TRANSITION_DELAY_SECONDS`` seconds of alarm state
        changing, according to the mtime of ``TRANSITION_FILE_PATH``,
        suppress the alarm
        """
        try:
            mtime = os.stat(TRANSITION_FILE_PATH).st_mtime
        except Exception:
            self._log.error(
                'Unable to read transition file mtime: %s',
                TRANSITION_FILE_PATH, exc_info=True
            )
            return False
        self._log.debug(
            'Transition file mtime=%s; delay=%s',
            mtime, TRANSITION_DELAY_SECONDS
        )
        if mtime < (time.time() - TRANSITION_DELAY_SECONDS):
            self._log.debug('Transition file is older than delay.')
            return False
        self._log.info(
            'Transition file (%s) mtime of %s is newer than %s seconds ago; '
            'suppressing ZM alarm.', TRANSITION_FILE_PATH, mtime,
            TRANSITION_DELAY_SECONDS
        )
        return True

    def _handle_alarm_event(self, event_name, data, _):
        """
        Handle the ZM_ALARM event.

        event type: ZM_ALARM
        data: dict from ``zmevent_handler.py``
        """
        alarm_state = self.alarm_state
        self._log.debug('Got %s event data=%s', event_name, data)
        self._log.info(
            'Handle %s - event %s for monitor %s', event_name,
            data['event']['EventId'], data['event']['Monitor']['Name']
        )
        if event_name != 'ZM_ALARM':
            self._log.error(
                'Got event of improper type: %s', event_name
            )
        if alarm_state == DISARMED:
            self._log.info(
                'Ignoring ZM_ALARM for Event %s - alarm disarmed',
                data['event']['EventId']
            )
            return
        if self._in_transition_period:
            self._log.info(
                'Ignoring ZM_ALARM for Event %s - current time is within %d '
                'seconds of last alarm state transition.',
                data['event']['EventId'], TRANSITION_DELAY_SECONDS
            )
            return
        if (
            alarm_state == HOME and
            data['event']['Monitor']['Name'] in HOME_IGNORE_MONITORS
        ):
            self._log.info(
                'Ignoring ZM_ALARM for Event %s on Monitor %s; alarm is in '
                'HOME state and monitor in HOME_IGNORE_MONITORS.',
                data['event']['EventId'], data['event']['Monitor']['Name']
            )
            return
        if max([len(x['detections']) for x in data['object_detections']]) == 0:
            self._log.info(
                'Ignoring ZM_ALARM for Event %s - no objects detected',
                data['event']['EventId']
            )
            return
        if self.motion_in_street(data['event']['Notes']):
            self._log.info(
                'Ignoring ZM_ALARM for Event %s - all motion in Street zones',
                data['event']['EventId']
            )
            return
        for f in data.get('filters', []):
            if f.get('matched', False) is False:
                continue
            self._log.info(
                'Ignoring ZM_ALARM for Event %s based on filter %s: %s',
                data['event']['EventId'], f.get('filter_name', 'unknown'),
                f.get('reason', 'unknown')
            )
            return
        # else our alarm isn't disarmed and we have some objects detected
        img = self._primary_detection_for_event(data)
        subject = 'ZoneMinder Alarm on %s - %s' % (
            data['event']['Monitor']['Name'], self.detection_str(img)
        )
        input_name = 'silence_monitor_' + data['event']['Monitor']['Name']
        input_name = input_name.lower()
        try:
            input_state = self.get_state(input_name)
        except Exception:
            input_state = 'off'
        if self.get_state('input_boolean.cameras_silent') == 'on':
            self._log.warning(
                'Suppressing pushover notification - '
                'input_boolean.cameras_silent is on'
            )
        elif input_state == 'on':
            self._log.warning(
                'Suppressing pushover notification - %s is on', input_name
            )
        else:
            self._notify_pushover(subject, data, img)
        self._notify_email(subject, data)

    def motion_in_street(self, notes):
        m = re.match(r'^Motion: (.+)', notes)
        if not m:
            return False
        parts = m.group(1).split()
        zones = [p.strip().strip(',') for p in parts]
        return all([z.startswith('Street') for z in zones])

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

    def _notify_pushover(self, subject, data, primary_image):
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
        image = primary_image['output_path']
        self._do_notify_pushover(
            subject, message, sound='siren', image=open(image, 'rb'),
            image_name=os.path.basename(image), url=url
        )

    def _notify_email(self, subject, data):
        addr = self._hass_secrets['gmail_username']
        index_url = '%sindex.php' % self._hass_secrets['zm_url_base']
        msg = EmailNotifier(subject, data, addr, index_url).build_message()
        self._do_notify_email(msg)


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
