#!/usr/bin/env python

import sys
import argparse
import logging
import os

if not os.path.exists('/opt/darknet/libdarknet.so'):
    os.environ['DARKNET_PATH'] = '/home/jantman/GIT/darknet'

sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from zmevent_config import DateSafeJsonEncoder
from zmevent_image_analysis import YoloAnalyzer, ImageAnalyzer
from zmevent_models import MonitorZone

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.WARNING, format=FORMAT)
logger = logging.getLogger()


class ZmAnalysisTester:

    def __init__(self, dry_run=False):
        self.dry_run = dry_run

    def run(self, fpath, debug=0):
        cfg = '/opt/darknet/yolov4-512.cfg'
        data = '/opt/darknet/coco.data'
        weights = '/opt/darknet/yolov4.weights'
        if not os.path.exists(cfg):
            cfg = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'yolov4-512.cfg'
            )
            data = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'coco.data'
            )
            weights = '/home/jantman/GIT/darknet/yolov4.weights'
        ANALYZERS = [YoloAnalyzer(
            cfg=cfg, data=data, weights=weights, debug=debug > 1
        )]
        msg = {
            'hostname': 'telescreen',
            'EventId': 460691,
            'monitor_zones': {
                "2": {
                    "Id": 2,
                    "MonitorId": 2,
                    "Name": "All",
                    "Type": "Active",
                    "point_list": [
                        [0, 484], [2148, 356], [1826, 1295], [0, 1295]
                    ]
                }
            },
            'frames': {
                '1': fpath
            }
        }
        logger.info(
            'Received analysis request for %s Event %s - %d frames',
            msg['hostname'], msg['EventId'], len(msg['frames'])
        )
        results = []
        for a in ANALYZERS:
            logger.debug('Running object detection with: %s', a)
            cls = ImageAnalyzer(
                a,
                {
                    x: MonitorZone(**msg['monitor_zones'][x])
                    for x in msg['monitor_zones'].keys()
                },
                msg['hostname']
            )
            for frameid, framepath in msg['frames'].items():
                res = cls.analyze(
                    msg['EventId'],
                    frameid,
                    framepath
                )
                results.append(res)
        logger.info(
            'Analysis for %s Event %s complete; returning %d results',
            msg['hostname'], msg['EventId'], len(results)
        )
        print('Result:')
        for r in results:
            print(r.as_dict)
            for d in r.detections:
                print(d.as_dict)


def parse_args(argv):
    """
    parse arguments/options

    this uses the new argparse module instead of optparse
    see: <https://docs.python.org/2/library/argparse.html>
    """
    p = argparse.ArgumentParser(description='zmevent_analysis tester')
    p.add_argument('-v', '--verbose', dest='verbose', action='count', default=0,
                   help='verbose output. specify twice for debug-level output.')
    p.add_argument('IMAGE', type=str, help='Image file path')
    args = p.parse_args(argv)
    return args


def set_log_info():
    """set logger level to INFO"""
    set_log_level_format(logging.INFO,
                         '%(asctime)s %(levelname)s:%(name)s:%(message)s')


def set_log_debug():
    """set logger level to DEBUG, and debug-level output format"""
    set_log_level_format(
        logging.DEBUG,
        "%(asctime)s [%(levelname)s %(filename)s:%(lineno)s - "
        "%(name)s.%(funcName)s() ] %(message)s"
    )


def set_log_level_format(level, format):
    """
    Set logger level and format.

    :param level: logging level; see the :py:mod:`logging` constants.
    :type level: int
    :param format: logging formatter format string
    :type format: str
    """
    formatter = logging.Formatter(fmt=format)
    logger.handlers[0].setFormatter(formatter)
    logger.setLevel(level)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    # set logging level
    if args.verbose > 1:
        set_log_debug()
    elif args.verbose == 1:
        set_log_info()

    ZmAnalysisTester().run(args.IMAGE, debug=args.verbose)
