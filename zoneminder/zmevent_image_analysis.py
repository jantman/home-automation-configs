import time
import logging
from shapely.geometry.polygon import LinearRing, Polygon
from zmevent_config import IGNORED_OBJECTS
from zmevent_models import DetectedObject, ObjectDetectionResult
import darknet
import cv2
from statsd_utils import statsd_send_time

logger = logging.getLogger(__name__)


class YoloAnalyzer:

    def __init__(self):
        # cfg = '/opt/darknet/yolov4-608.cfg'
        cfg = '/opt/darknet/yolov4-512.cfg'
        logger.info('Instantiating YOLO Detector with cfg=%s...', cfg)
        s = time.time()
        self._network, self._names, self._colors = darknet.load_network(
            cfg,
            '/opt/darknet/coco.data',
            '/opt/darknet/yolov4.weights',
            batch_size=1
        )
        e = time.time()
        logger.info('Instantiated YOLO detector in %s seconds', e - s)
        statsd_send_time('darknet.init_time', e - s)

    def _image_detection(self, image, thresh):
        # Darknet doesn't accept numpy images.
        # Create one with image we reuse for each detect
        width = darknet.network_width(self._network)
        height = darknet.network_height(self._network)
        darknet_image = darknet.make_image(width, height, 3)

        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image_resized = cv2.resize(image_rgb, (width, height),
                                   interpolation=cv2.INTER_LINEAR)

        darknet.copy_image_from_bytes(darknet_image, image_resized.tobytes())
        detections = darknet.detect_image(
            self._network, self._names, darknet_image, thresh=thresh
        )
        darknet.free_image(darknet_image)
        #image = darknet.draw_boxes(detections, image_resized, class_colors)
        #return cv2.cvtColor(image, cv2.COLOR_BGR2RGB), detections
        return detections

    def detect(self, fname, img):
        s = time.time()
        logger.info('Running detection on %s' % fname)
        # image, detections = self._image_detection(
        #    img, self._network, self._names, self._colors, 0.25
        # )
        detections = self._image_detection(img, 0.25)
        e = time.time()
        logger.info('Done running detection in %s', e - s)
        statsd_send_time('darknet.detect_time', e - s)
        return detections


class ImageAnalyzer:
    """Object detection using yolo34py and yolov3-tiny"""

    def __init__(self, detector, monitor_zones, hostname):
        self._monitor_zones = monitor_zones
        self._hostname = hostname
        self._detector = detector

    def _do_image(self, event_id, frame_id, fname, detected_fname):
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
        img = cv2.imread(fname)
        logger.info('Analyzing: %s', fname)
        results = self._detector.detect(fname, img)
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
        output_path = frame_path.replace('.jpg', '.yolo4.jpg')
        res = self._do_image(event_id, frame_id, frame_path, output_path)
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
