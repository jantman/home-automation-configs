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
from zmevent_image_analysis import YoloAnalyzer, ImageAnalyzer
from zmevent_models import MonitorZone


FORMAT = '%(asctime)s %(levelname)s:%(name)s:%(message)s'
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger()

ANALYZERS = [YoloAnalyzer()]


class ZMEventAnalysisServer(BaseHTTPRequestHandler):

    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        self._set_headers()
        self.wfile.write('{"status": "ok"}'.encode('utf-8'))

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
        """
        returns a list of ObjectDetectionResult instances

        Sample event:

        {
            "EventId": 192843,
            "monitor_zones": {
                "36": {
                    "Type": "Active",
                    "Name": "DrivewayFar",
                    "point_list": [
                        [781, 264],
                        [1128, 412],
                        [877, 491],
                        [648, 297]
                    ],
                    "MonitorId": 9,
                    "Id": 36
                },
            },
            "hostname": "guarddog",
            "frames": {
                "119": "/usr/share/zoneminder/www/events/9/19/06/30/13/34/19/00119-capture.jpg"
            }
        }
        """
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
        return results


def run():
    server_address = ('0.0.0.0', 8008)
    httpd = HTTPServer(server_address, ZMEventAnalysisServer)
    print('Starting ZMEventAnalysisServer on port 8008...')
    httpd.serve_forever()


if __name__ == "__main__":
    run()
