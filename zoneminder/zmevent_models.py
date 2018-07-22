"""
Database components of zmevent_handler.py
"""

import os
import logging
import time
import json
import pymysql
from PIL import Image
import requests

from zmevent_config import (
    EVENTS_PATH, CONFIG, DateSafeJsonEncoder
)

logger = logging.getLogger(__name__)


class Monitor(object):
    """Class to represent a Monitor from ZoneMinder's database."""

    def __init__(self, **kwargs):
        self.Height = None
        self.Id = None
        self.Name = None
        self.Width = None
        self.Zones = {}
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def __repr__(self):
        return '<Monitor(MonitorId=%d)>' % self.Id

    @property
    def as_dict(self):
        return {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }


class FrameStats(object):
    """Class to represent frame stats from ZoneMinder's Database."""

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
    def as_dict(self):
        return {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }


class Frame(object):
    """
    Class to represent a frame from ZoneMinder's database, augmented with some
    additional information.
    """

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
    def filename(self):
        return self.event.frame_fmt % self.FrameId

    @property
    def path(self):
        return os.path.join(self.event.path, self.filename)

    @property
    def image(self):
        if self._image is not None:
            return self._image
        logger.debug('Loading image for %s from: %s', self, self.path)
        self._image = Image.open(self.path)
        return self._image


class MonitorZone(object):
    """Class to represent a Zone for a single Monitor from ZM's database."""

    def __init__(self, **kwargs):
        self.Coords = None
        self.Id = None
        self.MonitorId = None
        self.Name = None
        self.Type = None
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.point_list = self._parse_db_coords_string(self.Coords)

    def _parse_db_coords_string(self, s):
        res = []
        for point in s.split():
            x, y = point.split(',')
            res.append((int(x), int(y)))
        return res

    def __repr__(self):
        return '<MonitorZone(MonitorId=%d, Id=%s)>' % (
            self.MonitorId, self.Id
        )

    @property
    def as_dict(self):
        d = {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }
        d['point_list'] = self.point_list
        del d['Coords']
        return d


class ZMEvent(object):
    """Class to store overall representation of a ZoneMinder Event."""

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
        self.BestFrameId = None
        self.FirstFrameId = None
        self.LastFrameId = None

        self.Monitor = None
        self.AllFrames = {}
        self.FramesForAnalysis = {}

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
    def as_dict(self):
        d = {
            x: getattr(self, x) for x in vars(self) if x[0].isupper()
        }
        d['path'] = self.path
        del d['AllFrames']
        return d

    @property
    def as_json(self):
        return json.dumps(
            self.as_dict, sort_keys=True, indent=4, cls=DateSafeJsonEncoder
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
            self._set_analysis_frames()
        for zone in results:
            self.Monitor.Zones[zone['Id']] = MonitorZone(**zone)
        logger.info('Done populating.')
        self._conn.commit()

    def _set_analysis_frames(self):
        """Generate and set ``self.FramesForAnalysis``."""
        logger.debug('Determining Frames to analyze')
        self.FirstFrameId = min(self.AllFrames.keys())
        self.LastFrameId = max(self.AllFrames.keys())
        self.BestFrameId = sorted(
            self.AllFrames.values(), key=lambda x: (x.Score, x.FrameId)
        )[-1].FrameId
        self.FramesForAnalysis = {
            self.FirstFrameId: self.AllFrames[self.FirstFrameId],
            self.BestFrameId: self.AllFrames[self.BestFrameId],
            self.LastFrameId: self.AllFrames[self.LastFrameId]
        }
        logger.info('Frames to analyze: %s', self.FramesForAnalysis)

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
