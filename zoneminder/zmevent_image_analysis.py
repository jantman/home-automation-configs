#!/usr/bin/env python3

import os
import requests
import time
import logging
from pydarknet import Detector, Image
import cv2
from textwrap import dedent

logger = logging.getLogger(__name__)
LOG_PATH = '/var/cache/zoneminder/temp/zmevent_image_analysis.log'
YOLO_CFG_PATH = '/var/cache/zoneminder/yolo'


class suppress_stdout_stderr(object):
    '''
    from: https://stackoverflow.com/q/11130156/211734

    A context manager for doing a "deep suppression" of stdout and stderr in
    Python, i.e. will suppress all print, even if the print originates in a
    compiled C/Fortran sub-function.
       This will not suppress raised exceptions, since exceptions are printed
    to stderr just before a script exits, and after the context manager has
    exited (at least, I think that is why it lets exceptions through).
    '''

    def __init__(self):
        # Open a pair of null files
        self.null_fds =  [os.open(os.devnull,os.O_RDWR) for x in range(2)]
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

    def __init__(self, event):
        self._event = event
        self._start = 0
        self._end = 0
        self._result = {
            'First': None,
            'Best': None,
            'Last': None,
        }
        self._raw_result = {}
        self._frame_paths = {
            'First': {},
            'Best': {},
            'Last': {}
        }

    def analyze(self):
        raise NotImplementedError('Implement in subclass!')

    @property
    def result(self):
        return self._result

    @property
    def frames(self):
        return self._frame_paths

    @property
    def runtime(self):
        return self._end - self._start

    @property
    def new_objects(self):
        raise NotImplementedError('Implement in subclass!')


class YoloAnalyzer(ImageAnalyzer):

    def _ensure_configs(self):
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

    def do_image_yolo(self, net, fname, detected_fname):
        logger.debug('Starting: %s', fname)
        img = cv2.imread(fname)
        img2 = Image(img)
        results = net.detect(img2, thresh=0.2, hier_thresh=0.3, nms=0.4)
        logger.debug('Raw Results: %s', results)

        for cat, score, bounds in results:
            x, y, w, h = bounds
            cv2.rectangle(
                img, (int(x - w / 2), int(y - h / 2)),
                (int(x + w / 2), int(y + h / 2)), (255, 0, 0), thickness=2
            )
            cv2.putText(
                img, '%s (%.2f)' % (cat.decode('utf-8'), score),
                (int(x), int(y)),
                cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 0)
            )
        logger.info('Writing: %s', detected_fname)
        cv2.imwrite(detected_fname, img)
        logger.info('Done with: %s', fname)
        return results

    def analyze(self):
        self._ensure_configs()
        self._start = time.time()
        logger.info('Instantiating YOLO3 Detector...')
        with suppress_stdout_stderr():
            net = Detector(
                bytes(self._config_path("yolov3.cfg"), encoding="utf-8"),
                bytes(self._config_path("yolov3.weights"), encoding="utf-8"),
                0,
                bytes(self._config_path("coco.data"), encoding="utf-8")
            )
        logger.debug('Done instantiating YOLO3 Detector.')
        # get all the results
        results = {}
        logger.info('Analyzing first frame')
        self._frame_paths['First']['original'] = self._event.FirstFrame.path
        self._frame_paths['First']['analyzed'] = self._frame_paths[
            'First']['original'].replace('.jpg', '.yolo3.jpg')
        results['First'] = self.do_image_yolo(
            net,
            self._frame_paths['First']['original'],
            self._frame_paths['First']['analyzed']
        )
        logger.info('Analyzing best frame')
        self._frame_paths['Best']['original'] = self._event.BestFrame.path
        self._frame_paths['Best']['analyzed'] = self._frame_paths[
            'Best']['original'].replace('.jpg', '.yolo3.jpg')
        results['Best'] = self.do_image_yolo(
            net,
            self._frame_paths['Best']['original'],
            self._frame_paths['Best']['analyzed']
        )
        logger.info('Analyzing last frame')
        self._frame_paths['Last']['original'] = self._event.LastFrame.path
        self._frame_paths['Last']['analyzed'] = self._frame_paths[
            'Last']['original'].replace('.jpg', '.yolo3.jpg')
        results['Last'] = self.do_image_yolo(
            net,
            self._frame_paths['Last']['original'],
            self._frame_paths['Last']['analyzed']
        )
        self._raw_result = results
        for key, res in results.items():
            self._result[key] = [
                '%s - %.2f%% - %s' % (
                    x[0].decode('utf-8'), (x[1] * 100), x[2]
                ) for x in res
            ]
        self._end = time.time()

    @property
    def new_objects(self):
        f = [x[0].decode('utf-8') for x in self._raw_result['First']]
        b = [x[0].decode('utf-8') for x in self._raw_result['Best']]
        return list(set(b) - set(f))
