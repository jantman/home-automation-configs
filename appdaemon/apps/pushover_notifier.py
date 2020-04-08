"""
AppDaemon app mixin for Pushover notification
"""

import logging
import os
import requests
import smtplib

from yaml import load as load_yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


class PushoverNotifier(object):

    def _get_hass_secrets(self):
        """
        Return the dictionary contents of HASS ``secrets.yaml``.
        """
        # get HASS configuration from its API
        apiconf = self.get_plugin_config()
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
        # return the full dict
        return conf

    def _do_notify_pushover(self, title, message, sound=None, image=None,
                            image_name='frame.jpg',
                            url='https://redirect.jasonantman.com/hass'):
        """Build Pushover API request arguments and call _send_pushover"""
        d = {
            'data': {
                'token': self._hass_secrets['pushover_api_key'],
                'user': self._hass_secrets['pushover_user_key'],
                'title': title,
                'message': message,
                'url': url,
                'retry': 300  # 5 minutes
            },
            'files': {}
        }
        if sound is not None:
            d['data']['sound'] = sound
        if image is None:
            self._log.info('Sending Pushover notification: %s', d)
        else:
            self._log.info('Sending Pushover notification with image: %s', d)
            d['files']['attachment'] = (image_name, image, 'image/jpeg')
        for i in range(0, 2):
            try:
                self._send_pushover(d)
                return
            except Exception:
                self._log.critical(
                    'send_pushover raised exception', exc_info=True
                )
        if self._hass_secrets.get('proxies', {}) == {}:
            self._log.critical(
                'send_pushover failed on all attempts and proxies is empty!'
            )
            return
        # try sending through proxy
        if 'files' in d:
            del d['files']
        d['proxies'] = self._hass_secrets['proxies']
        for i in range(0, 2):
            try:
                self._send_pushover(d)
                return
            except Exception:
                self._log.critical(
                    'send_pushover via proxy raised exception', exc_info=True
                )

    def _send_pushover(self, params):
        """
        Send the actual Pushover notification.

        We do this directly with ``requests`` because python-pushover still
        doesn't have support for images or some other API options.
        """
        url = 'https://api.pushover.net/1/messages.json'
        if 'proxies' in params:
            self._log.debug(
                'Sending Pushover notification with proxies=%s',
                params['proxies']
            )
        else:
            self._log.debug('Sending Pushover notification')
        r = requests.post(url, **params)
        self._log.debug(
            'Pushover POST response HTTP %s: %s', r.status_code, r.text
        )
        r.raise_for_status()
        if r.json()['status'] != 1:
            raise RuntimeError('Error response from Pushover: %s', r.text)
        self._log.info('Pushover Notification Success: %s', r.text)

    def _do_notify_email(self, message):
        addr = self._hass_secrets['gmail_username']
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
        s.sendmail(addr, addr, message)
        self._log.info('EMail sent.')
        s.quit()
