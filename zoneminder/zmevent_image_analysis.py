import os
import time
import logging
from textwrap import dedent
import requests
from shapely.geometry.polygon import LinearRing, Polygon
from zmevent_config import IGNORED_OBJECTS
from zmevent_models import DetectedObject, ObjectDetectionResult


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

#: Path on disk where darknet yolo configs/weights will be stored
YOLO_CFG_PATH = '/var/cache/zoneminder/yolo'
YOLO_ALT_CFG_PATH = '/var/cache/zoneminder/yolo-alt'


class suppress_stdout_stderr(object):
    """
    Context manager to do "deep suppression" of stdout and stderr.

    from: https://stackoverflow.com/q/11130156/211734

    A context manager for doing a "deep suppression" of stdout and stderr in
    Python, i.e. will suppress all print, even if the print originates in a
    compiled C/Fortran sub-function.
       This will not suppress raised exceptions, since exceptions are printed
    to stderr just before a script exits, and after the context manager has
    exited (at least, I think that is why it lets exceptions through).
    """

    def __init__(self):
        # Open a pair of null files
        self.null_fds = [os.open(os.devnull, os.O_RDWR) for x in range(2)]
        # Save the actual stdout (1) and stderr (2) file descriptors.
        self.save_fds = [os.dup(1), os.dup(2)]

    def __enter__(self):
        # Assign the null pointers to stdout and stderr.
        os.dup2(self.null_fds[0],1)
        os.dup2(self.null_fds[1],2)

    def __exit__(self, *_):
        # Re-assign the real stdout/stderr back to (1) and (2)
        os.dup2(self.save_fds[0],1)
        os.dup2(self.save_fds[1],2)
        # Close all file descriptors
        for fd in self.null_fds + self.save_fds:
            os.close(fd)


class ImageAnalyzer(object):
    """
    Base class for specific object detection algorithms/packages.
    """

    def __init__(self, monitor_zones, hostname):
        """
        Initialize an image analyzer.

        :param monitor_zones: dict of string zone names to MonitorZone objects,
          for the monitor this event happened on
        :type monitor_zones: dict
        """
        self._monitor_zones = monitor_zones
        self._hostname = hostname

    def analyze(self, event_id, frame_id, frame_path):
        """
        Analyze a frame; return an ObjectDetectionResult.
        """
        raise NotImplementedError('Implement in subclass!')


class YoloAnalyzer(ImageAnalyzer):
    """Object detection using yolo34py and yolov3-tiny"""

    def __init__(self, monitor_zones, hostname):
        super(YoloAnalyzer, self).__init__(monitor_zones, hostname)
        self._ensure_configs()
        logger.info('Instantiating YOLO3 Detector...')
        with suppress_stdout_stderr():
            self._net = Detector(
                bytes(self._config_path("yolov3.cfg"), encoding="utf-8"),
                bytes(self._config_path("yolov3.weights"), encoding="utf-8"),
                0,
                bytes(self._config_path("coco.data"), encoding="utf-8")
            )
        logger.debug('Done instantiating YOLO3 Detector.')

    def _ensure_configs(self):
        """Ensure that yolov3-tiny configs and data are in place."""
        # This uses the yolov3-tiny, because I only have a 1GB GPU
        if not os.path.exists(YOLO_CFG_PATH):
            logger.warning('Creating directory: %s', YOLO_CFG_PATH)
            os.mkdir(YOLO_CFG_PATH)
        configs = {
            'yolov3.cfg': 'https://raw.githubusercontent.com/pjreddie/darknet/'
                          'master/cfg/yolov3-tiny.cfg',
            'coco.names': 'https://raw.githubusercontent.com/pjreddie/darknet/'
                          'master/data/coco.names',
            'yolov3.weights': 'https://pjreddie.com/media/files/'
                              'yolov3-tiny.weights'
        }
        for fname, url in configs.items():
            path = self._config_path(fname)
            if os.path.exists(path):
                continue
            logger.warning('%s does not exist; downloading', path)
            logger.info('Download %s to %s', url, path)
            r = requests.get(url)
            logger.info('Writing %d bytes to %s', len(r.content), path)
            with open(path, 'wb') as fh:
                fh.write(r.content)
            logger.debug('Wrote %s', path)
        # coco.data is special because we change it
        path = self._config_path('coco.data')
        if not os.path.exists(path):
            content = dedent("""
            classes= 80
            train  = /home/pjreddie/data/coco/trainvalno5k.txt
            valid = %s
            names = %s
            backup = /home/pjreddie/backup/
            eval=coco
            """)
            logger.warning('%s does not exist; writing', path)
            with open(path, 'w') as fh:
                fh.write(content % (
                    self._config_path('coco_val_5k.list'),
                    self._config_path('coco.names')
                ))
            logger.debug('Wrote %s', path)

    def _config_path(self, f):
        return os.path.join(YOLO_CFG_PATH, f)

    def do_image_yolo(self, event_id, frame_id, fname, detected_fname):
        """
        Analyze a single image using yolo34py.

        :param event_id: the EventId being analyzed
        :type event_id: int
        :param frame_id: the FrameId being analyzed
        :type frame_id: int
        :param fname: path to input image
        :type fname: str
        :param detected_fname: file path to write object detection image to
        :type detected_fname: str
        :return: yolo3 detection results
        :rtype: list of DetectedObject instances
        """
        logger.info('Analyzing: %s', fname)
        img = cv2.imread(fname)
        img2 = Image(img)
        results = self._net.detect(img2, thresh=0.2, hier_thresh=0.3, nms=0.4)
        logger.debug('Raw Results: %s', results)
        retval = {'detections': [], 'ignored_detections': []}
        for cat, score, bounds in results:
            if not isinstance(cat, str):
                cat = cat.decode()
            x, y, w, h = bounds
            zones = self._zones_for_object(x, y, w, h)
            logger.debug('Checking IgnoredObject filters for detections...')
            matched_filters = [
                foo.name for foo in IGNORED_OBJECTS.get(self._hostname, [])
                if foo.should_ignore(cat, x, y, w, h, zones, score)
            ]
            if len(matched_filters) > 0:
                # object should be ignored
                logger.info(
                    'Event %s Frame %s: Ignoring %s (%.2f) at %d,%d based on '
                    'filters: %s',
                    event_id, frame_id, cat, score, x, y, matched_filters
                )
                rect_color = (104, 104, 104)
                text_color = (111, 247, 93)
                retval['ignored_detections'].append(DetectedObject(
                    cat, zones, score, x, y, w, h, ignore_reason=matched_filters
                ))
            else:
                # object should not be ignored; add to result
                rect_color = (255, 0, 0)
                text_color = (255, 255, 0)
                retval['detections'].append(DetectedObject(
                    cat, zones, score, x, y, w, h
                ))
            cv2.rectangle(
                img, (int(x - w / 2), int(y - h / 2)),
                (int(x + w / 2), int(y + h / 2)), rect_color, thickness=2
            )
            cv2.putText(
                img, '%s (%.2f)' % (cat, score),
                (int(x), int(y)),
                cv2.FONT_HERSHEY_COMPLEX, 1, text_color
            )
        logger.info('Writing: %s', detected_fname)
        cv2.imwrite(detected_fname, img)
        logger.info('Done with: %s', fname)
        return retval

    def _xywh_to_ring(self, x, y, width, height):
        points = [
            (x - (width / 2.0), y - (height / 2.0)),
            (x - (width / 2.0), y + (height / 2.0)),
            (x + (width / 2.0), y + (height / 2.0)),
            (x + (width / 2.0), y - (height / 2.0)),
            (x - (width / 2.0), y - (height / 2.0))
        ]
        return Polygon(LinearRing(points))

    def _zones_for_object(self, x, y, w, h):
        res = {}
        obj_polygon = self._xywh_to_ring(x, y, w, h)
        for zone in self._monitor_zones.values():
            if obj_polygon.intersects(zone.polygon):
                amt = (
                    obj_polygon.intersection(zone.polygon).area /
                    obj_polygon.area
                ) * 100
                res[zone.Name] = amt
        return res

    def analyze(self, event_id, frame_id, frame_path):
        _start = time.time()
        # get all the results
        output_path = frame_path.replace('.jpg', '.yolo3.jpg')
        res = self.do_image_yolo(event_id, frame_id, frame_path, output_path)
        _end = time.time()
        return ObjectDetectionResult(
            self.__class__.__name__,
            event_id,
            frame_id,
            frame_path,
            output_path,
            res['detections'],
            res['ignored_detections'],
            _end - _start
        )


class AlternateYoloAnalyzer(YoloAnalyzer):
    """
    This is used when I run from a script in a separate venv to compare CPU and
    GPU results.
    """

    def _config_path(self, f):
        return os.path.join(YOLO_ALT_CFG_PATH, f)

    def _ensure_configs(self):
        """Ensure that yolov3-tiny configs and data are in place."""
        # This uses the yolov3-tiny, because I only have a 1GB GPU
        if not os.path.exists(YOLO_ALT_CFG_PATH):
            logger.warning('Creating directory: %s', YOLO_ALT_CFG_PATH)
            os.mkdir(YOLO_ALT_CFG_PATH)
        configs = {
            'yolov3.cfg': 'https://raw.githubusercontent.com/pjreddie/darknet/'
                          'master/cfg/yolov3.cfg',
            'coco.names': 'https://raw.githubusercontent.com/pjreddie/darknet/'
                          'master/data/coco.names',
            'yolov3.weights': 'https://pjreddie.com/media/files/'
                              'yolov3.weights'
        }
        for fname, url in configs.items():
            path = self._config_path(fname)
            if os.path.exists(path):
                continue
            logger.warning('%s does not exist; downloading', path)
            logger.info('Download %s to %s', url, path)
            r = requests.get(url)
            logger.info('Writing %d bytes to %s', len(r.content), path)
            with open(path, 'wb') as fh:
                fh.write(r.content)
            logger.debug('Wrote %s', path)
        # coco.data is special because we change it
        path = self._config_path('coco.data')
        if not os.path.exists(path):
            content = dedent("""
            classes= 80
            train  = /home/pjreddie/data/coco/trainvalno5k.txt
            valid = %s
            names = %s
            backup = /home/pjreddie/backup/
            eval=coco
            """)
            logger.warning('%s does not exist; writing', path)
            with open(path, 'w') as fh:
                fh.write(content % (
                    self._config_path('coco_val_5k.list'),
                    self._config_path('coco.names')
                ))
            logger.debug('Wrote %s', path)

    def analyze(self, event_id, frame_id, frame_path):
        _start = time.time()
        # get all the results
        output_path = frame_path.replace('.jpg', '.yolo3alt.jpg')
        res = self.do_image_yolo(event_id, frame_id, frame_path, output_path)
        _end = time.time()
        return ObjectDetectionResult(
            self.__class__.__name__,
            event_id,
            frame_id,
            frame_path,
            output_path,
            res['detections'],
            res['ignored_detections'],
            _end - _start
        )
