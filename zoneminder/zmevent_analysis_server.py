#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import cgi
import logging
import json
import sys
import os

# This is running from a git clone, not really installed
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

from zmevent_config import DateSafeJsonEncoder
from zmevent_image_analysis import YoloAnalyzer
from zmevent_models import MonitorZone

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

FORMAT = '%(asctime)s %(levelname)s:%(name)s:%(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger()

ANALYZERS = [YoloAnalyzer]


class ZMEventAnalysisServer(BaseHTTPRequestHandler):

    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_POST(self):
        ctype, pdict = cgi.parse_header(self.headers.get('content-type'))

        # refuse to receive non-json content
        if ctype != 'application/json':
            self.send_response(400)
            self.end_headers()
            return
        # read the message and convert it into a python dictionary
        length = int(self.headers.get('content-length'))
        message = json.loads(self.rfile.read(length).decode())

        response = self.analyze_event(message)

        # send the message back
        self._set_headers()
        self.wfile.write(
            json.dumps(response, cls=DateSafeJsonEncoder).encode('utf-8')
        )

    def analyze_event(self, msg):
        """returns a list of ObjectDetectionResult instances"""
        results = []
        for a in ANALYZERS:
            logger.debug('Running object detection with: %s', a)
            cls = a(
                {
                    x: MonitorZone(**msg['monitor_zones'][x])
                    for x in msg['monitor_zones'].keys()
                },
                msg['hostname']
            )
            for frame in [msg['frame_path']]:
                res = cls.analyze(
                    msg['EventId'],
                    msg['FrameId'],
                    frame
                )
                results.append(res)
        return results


def run():
    server_address = ('0.0.0.0', 8008)
    httpd = HTTPServer(server_address, ZMEventAnalysisServer)
    print('Starting ZMEventAnalysisServer on port 8008...')
    httpd.serve_forever()


if __name__ == "__main__":
    run()
