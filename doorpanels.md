# Doorpanel RaspberryPi Touchscreen Alarm Panels

## HASS setup

As of somewhere in the 0.80-0.94 releases, HASS now requires an API token for use of the websocket API. This is a bit of a pain. As a result, we have to locally place a file in our clone of this repo at ``homeassistant/www/doorpanels/js/local_apitoken.js`` with content like:

```
export const apiToken = "yourTokenHere";
export const hassBaseUrl = "http://YourHassHostName:8123";
```

## RaspberryPi Hardware/Software Setup

### Newer RPi 4

My newer version ("kitchenpi" hostname), which I currently have in my kitchen (back door to the house) uses a RaspberryPi 4 B, 2019 model, quad core 64-bit, 4GB RAM. It's using a somewhat generic [Jun-Electron 3.5" 320x480 TFT LCD Touchscreen with case from Amazon](https://www.amazon.com/gp/product/B07WQW6H9S/). This seems very similar to the other inexpensive SPI touchscreens and also uses the [goodtft/LCD-show](https://github.com/goodtft/LCD-show) drivers, in this case the [MHS35-show](https://github.com/goodtft/LCD-show/blob/master/MHS35-show).

The process here is largely based on the one I developed for my older 3B+ based display, described below.

#### System/Hardware Setup process

__Note:__ Do not attach the touchscreen until instructed!

1. Write the Raspberry Pi Foundation's Raspberry Pi OS With Desktop (``2021-10-30-raspios-bullseye-armhf.zip``) image to SD card: ``dd bs=4M if=2021-10-30-raspios-bullseye-armhf.img of=/dev/sdX conv=fsync status=progress``
1. When finished, mount the two partitions of the card (rootfs and boot) somewhere on your system.
1. As root, on the boot partition, ``touch ssh`` to enable SSH login.
1. Find the UID and GID of the ``pi`` user (usually 1000:1000).
1. As root, on the rootfs partition:
   1. ``install -d -m 0700 -o 1000 -g 1000 home/pi/.ssh``
   1. Find the path to your own authorized_keys file
   1. ``install -m 0644 -o 1000 -g 1000 $AUTHKEYS_PATH home/pi/.ssh/authorized_keys``
   1. Set a hostname. Using "rpi5" as an example: ``echo kitchenpi > etc/hostname && sed -i "s/raspberrypi/kitchenpi/g" etc/hosts``
1. Umount the partitions and eject the card. Put it in the Pi, connect a HDMI monitor and USB keyboard, and power it up.
1.  The Pi should boot, resize the filesystem, then reboot and eventually boot to the Raspbian graphical desktop auto-logged-in as the "pi" user.
1. Go through the first two screens of the configuration "wizard"; set localization and timezone settings and password.
1. Get the MAC address of the network adapter you'll be using. Set up a static lease for it, and add to WiFi ACL (if applicable).
1. Configure WiFi and let the installer run updates.
1. Finish and reboot.
1. SSH to the instance. Assuming this works, you can log out on the console, unplug the keyboard and HDMI, and continue over SSH.
1. ``sudo raspi-config`` - System Options -> Network at Boot. Also set to automatic graphical login
1. ``sudo apt-get install puppet git ruby``
1. ``sudo gem install --no-user-install r10k``
1. ``sudo ln -s /usr/local/bin/r10k /usr/bin/r10k``
1. ``sudo su -``
   1. ``ssh-keygen``
   1. ``cat /root/.ssh/id_rsa.pub``
   1. Add as a [privatepuppet deploy key](https://github.com/jantman/privatepuppet/settings/keys)
   1. ``cd /root && git clone https://github.com/jantman/workstation-bootstrap.git && cd workstation-bootstrap``
   1. ``echo -e "Host github.com\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n" >> ~/.ssh/config && chmod 0600 ~/.ssh/config``
   1. ``vim /etc/fstab`` and set the last field of all partitions to ``0`` to prevent fsck at boot.
   1. ``./bin/run_r10k_puppet.sh``
   1. ``reboot``
1. ``sudo su -`` and ``bin/run_r10k_puppet.sh``; reboot once that's done

### Older RPi 3B+

For my intial test ("rpi5" hostname), I'm using a RaspberryPi 3B+ and a cheap [Kuman 3.5 inch 320x480 TFT LCD Touchscreen](https://www.amazon.com/gp/product/B01FXC5ECS/) that I got on Amazon, along with a case that fits the screen and Pi.

#### System/Hardware Setup process

__Note:__ Do not attach the touchscreen until instructed!

This is based on a combination of my previous work with the Pi, the [documentation and code](https://github.com/goodtft/LCD-show) for the display I bought, and [this blog post](https://blockdev.io/raspberry-pi-2-and-3-chromium-in-kiosk-mode/).

I [originally](https://github.com/jantman/home-automation-configs/blob/dec867a6a84f28824e2aa77a7f55d49ebf2c787d/doorpanels.md) tried this using the Raspbian Stretch Lite (no GUI) variant according to [this blog post](https://die-antwort.eu/techblog/2017-12-setup-raspberry-pi-for-kiosk-mode/) but was unable, over the course of two days, to get it working. I decided that since I'm using a Pi 3B+, I might as well just use the default Raspbian desktop environment and save some trouble.

1. Write the Raspberry Pi Foundation's Raspbian Stretch (2018-06-27) image to SD card.
1. When finished, mount the two partitions of the card (rootfs and boot) somewhere on your system.
1. As root, on the boot partition, ``touch ssh`` to enable SSH login.
1. Find the UID and GID of the ``pi`` user (usually 1000:1000).
1. As root, on the rootfs partition:
   1. ``install -d -m 0700 -o 1000 -g 1000 home/pi/.ssh``
   1. Find the path to your own authorized_keys file
   1. ``install -m 0644 -o 1000 -g 1000 $AUTHKEYS_PATH home/pi/.ssh/authorized_keys``
   1. Set a hostname. Using "rpi5" as an example: ``echo rpi5 > etc/hostname && sed -i "s/raspberrypi/rpi5/g" etc/hosts``
1. Umount the partitions and eject the card. Put it in the Pi, connect a HDMI monitor and USB keyboard, and power it up.
1. The Pi should boot, resize the filesystem, then reboot and eventually boot to the Raspbian graphical desktop auto-logged-in as the "pi" user.
1. Go through the first two screens of the configuration "wizard"; set localization and timezone settings and password.
1. Get the MAC address of the network adapter you'll be using. Set up a static lease for it, and add to WiFi ACL (if applicable).
1. Configure WiFi and let the installer run updates.
1. Finish and reboot.
1. SSH to the instance. Assuming this works, you can log out on the console, unplug the keyboard and HDMI, and continue over SSH.
1. ``sudo raspi-config`` - Boot Options -> Wait for Network at Boot. Also set to automatic graphical login
1. ``sudo apt-get install puppet git ruby``
1. ``sudo gem install --no-user-install r10k``
1. ``sudo ln -s /usr/local/bin/r10k /usr/bin/r10k``
1. ``sudo su -``
   1. ``ssh-keygen``
   1. ``cat /root/.ssh/id_rsa.pub``
   1. Add as a [privatepuppet deploy key](https://github.com/jantman/privatepuppet/settings/keys)
   1. ``cd /root && git clone https://github.com/jantman/workstation-bootstrap.git && cd workstation-bootstrap``
   1. ``./bin/run_r10k_puppet.sh``
      * If you get a "host key verification failed" message, then ``echo -e "Host github.com\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n" >> ~/.ssh/config && chmod 0600 ~/.ssh/config`` and retry
   1. ``reboot``
1. ``sudo su -`` and ``bin/run_r10k_puppet.sh``; reboot once that's done
