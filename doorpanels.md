# Doorpanel RaspberryPi Touchscreen Alarm Panels

## HASS setup

As of somewhere in the 0.80-0.94 releases, HASS now requires an API token for use of the websocket API. This is a bit of a pain. As a result, we have to locally place a file in our clone of this repo at ``homeassistant/www/doorpanels/js/local_apitoken.js`` with content like:

```
export const apiToken = "yourTokenHere";
export const hassBaseUrl = "http://YourHassHostName:8123";
```

## RaspberryPi Hardware/Software Setup

For my intial test, I'm using a RaspberryPi 3B+ and a cheap [Kuman 3.5 inch 320x480 TFT LCD Touchscreen](https://www.amazon.com/gp/product/B01FXC5ECS/) that I got on Amazon, along with a case that fits the screen and Pi.

### System/Hardware Setup process

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
1. ``sudo raspi-config`` - Boot Options -> Wait for Network at Boot.
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
1. ``sudo su -`` and ``bin/run_r10k_puppet.sh``

Original install:

1. ``sudo apt-get install unclutter chromium-browser``
1. ``nano ~/.config/lxsession/LXDE-pi/autostart`` and set the contents to:
```
@sed -i 's/"exited_cleanly": false/"exited_cleanly": true/' ~/.config/chromium-browser Default/Preferences
@chromium-browser --noerrdialogs --kiosk http://guarddog:8123/local/doorpanels/index.html --incognito --disable-translate
```
1. ``sudo reboot`` - if all worked well, when the reboot is complete the system should be showing the doorpanel display full-screen.
1. For the touchscreen installation (this code is awful, but it seems safe on a new system):
    1. ``git clone https://github.com/jantman/LCD-show.git && cd LCD-show`` - it's probably worth looking at everything this does, since it seems to be pretty poorly written and has _lots_ of open issues. When I did this work, master was at [b8c10906a8501b484f98ce410b5dcc8d7aacaa73](https://github.com/goodtft/LCD-show/commit/b8c10906a8501b484f98ce410b5dcc8d7aacaa73) and had just been updated four days ago.
    1. ``cat /boot/cmdline.txt`` and record the contents, since this isn't backed up. Mine was: ``dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=PARTUUID=509867d5-02 rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles``
    1. ``bash -ex LCD35-show``
1. When prompted, reboot the system. If everything works well, it should eventually boot into Chrome and show the "doorpanel" display fullscreen. If the display appears upside-down:
    1. ``sudo nano /boot/config.txt`` and change ``dtoverlay=tft35a`` to ``dtoverlay=tft35a:rotate=270``
    1. ``sudo nano /etc/X11/xorg.conf.d/99-calibration.conf`` and before the ``EndSection`` line add lines for ``Option "InvertY" "true"`` and ``Option "InvertX" "true"``
