import machine
import os
import network
import sys
import esp
import time
from binascii import hexlify

from config import GLPI_URL

try:
    from urequests import post
except ImportError:
    from requests import post


def send_glpi(wlan, boot_time):
    if GLPI_URL is None:
        return
    print('Prepping data for GLPI')
    t = time.gmtime(time.time())
    boot_t = time.gmtime(boot_time)
    mac = hexlify(network.WLAN(network.STA_IF).config('mac')).decode()
    mac_colons = ':'.join([mac[i:i+2] for i in range(0, len(mac), 2)])
    netconf = wlan.ifconfig()
    data = f"""<?xml version="1.0" encoding="UTF-8" ?>
<REQUEST>
  <CONTENT>
    <ACCESSLOG>
      <LOGDATE>{t[0]}-{t[1]:02}-{t[2]:02} {t[3]:02}:{t[4]:02}:{t[5]:02}</LOGDATE>
    </ACCESSLOG>
    <BIOS>
      <ASSETTAG>{mac}</ASSETTAG>
      <BMANUFACTURER>Espressif</BMANUFACTURER>
      <MMANUFACTURER>Espressif</MMANUFACTURER>
      <MMODEL>{sys.platform}</MMODEL>
      <MSN>{mac}</MSN>
      <SMANUFACTURER>Espressif</SMANUFACTURER>
      <SMODEL>{sys.platform}</SMODEL>
      <SSN>{mac}</SSN>
    </BIOS>
    <CPUS>
      <CORE>1</CORE>
      <CORECOUNT>1</CORECOUNT>
      <EXTERNAL_CLOCK>100</EXTERNAL_CLOCK>
      <FAMILYNAME>Xtensa</FAMILYNAME>
      <MANUFACTURER>Tensilica</MANUFACTURER>
      <MODEL>LX6</MODEL>
      <NAME>Tensilica Xtensa</NAME>
      <SPEED>{int(machine.freq() / 1000000)}</SPEED>
    </CPUS>
    <HARDWARE>
      <CHASSIS_TYPE>{sys.platform}</CHASSIS_TYPE>
      <DEFAULTGATEWAY>{netconf[2]}</DEFAULTGATEWAY>
      <DNS>{netconf[3]}</DNS>
      <IPADDR>{netconf[0]}</IPADDR>
      <MEMORY>{int(esp.flashsize() / 1000000)}</MEMORY>
      <NAME>{network.hostname()}/NAME>
      <OSCOMMENTS>{os.uname().machine}</OSCOMMENTS>
      <OSNAME>micropython</OSNAME>
      <OSVERSION>{os.uname().release}</OSVERSION>
      <PROCESSORN>1</PROCESSORN>
      <PROCESSORS>{int(machine.freq() / 1000000)}</PROCESSORS>
      <PROCESSORT>{sys.platform}</PROCESSORT>
      <VMSYSTEM>Physical</VMSYSTEM>
    </HARDWARE>
    <NETWORKS>
      <DESCRIPTION>wifi0</DESCRIPTION>
      <IPADDRESS>{netconf[0]}</IPADDRESS>
      <IPGATEWAY>{netconf[2]}</IPGATEWAY>
      <IPMASK>{netconf[1]}</IPMASK>
      <MACADDR>{mac_colons}</MACADDR>
      <STATUS>Up</STATUS>
      <TYPE>wifi</TYPE>
      <VIRTUALDEV>0</VIRTUALDEV>
    </NETWORKS>
    <OPERATINGSYSTEM>
      <BOOT_TIME>{boot_t[0]}-{boot_t[1]:02}-{boot_t[2]:02} {boot_t[3]:02}:{boot_t[4]:02}:{boot_t[5]:02}</BOOT_TIME>
      <FULL_NAME>micropython {os.uname().version} on {sys.platform} {os.uname().machine}</FULL_NAME>
      <KERNEL_NAME>micropython</KERNEL_NAME>
      <KERNEL_VERSION>{os.uname().release}</KERNEL_VERSION>
      <NAME>micropython</NAME>
      <VERSION>{os.uname().release}</VERSION>
    </OPERATINGSYSTEM>
    <VERSIONCLIENT>github.com/jantman/home-automation-configs/wemos_d1_mini</VERSIONCLIENT>
    <VERSIONPROVIDER>
      <NAME>Home-Automation-Configs</NAME>
    </VERSIONPROVIDER>
  </CONTENT>
  <DEVICEID>{mac}</DEVICEID>
  <QUERY>INVENTORY</QUERY>
</REQUEST>
"""
    print('Sending data to GLPI')
    r = post(
        'http://192.168.0.18:8088/', data=data,
        headers={'Content-Type': 'application/xml'}
    )
    print('GLPI responded HTTP %s: %s' % (r.status_code, r.content))
