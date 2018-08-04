# Doorpanel RaspberryPi Touchscreen Alarm Panels

* components and how they work together
* screenshots
* link to appdaemon app and doorpanels frontend
* docs on each of those
* docs on pi setup

## RaspberryPi Hardware/Software Setup

For my intial test, I'm using a RaspberryPi 3B+ and a cheap [Kuman 3.5 inch 320x480 TFT LCD Touchscreen](https://www.amazon.com/gp/product/B01FXC5ECS/) that I got on Amazon, along with a case that fits the screen and Pi.

### System/Hardware Setup process

__Note:__ Do not attach the touchscreen until instructed!

This is based on a combination of my previous work with the Pi, the [documentation and code](https://github.com/goodtft/LCD-show) for the display I bought, and [this blog post](https://die-antwort.eu/techblog/2017-12-setup-raspberry-pi-for-kiosk-mode/) on running kiosk mode browsers on the Pi.

1. Write the Raspberry Pi Foundation's Raspbian Stretch Lite (2018-06-27) image to SD card.
2. When finished, mount the two partitions of the card (rootfs and boot) somewhere on your system.
3. As root, on the boot partition, ``touch ssh`` to enable SSH login.
4. Find the UID and GID of the ``pi`` user (usually 1000:1000).
5. As root, on the rootfs partition:
   1. ``install -d -m 0700 -o 1000 -g 1000 home/pi/.ssh``
   2. Find the path to your own authorized_keys file
   3. ``install -m 0644 -o 1000 -g 1000 $AUTHKEYS_PATH home/pi/.ssh/authorized_keys``
   4. Set a hostname. Using "rpi5" as an example: ``echo rpi5 > etc/hostname && sed -i "s/raspberrypi/rpi5/g" "etc/hosts"``
6. Umount the partitions and eject the card. Put it in the Pi, connect a HDMI monitor and USB keyboard, and power it up.
7. The Pi should boot, resize the filesystem, then reboot and eventually boot to the Raspbian login prompt.
8. Log in as user "pi" and password "raspberry".
9. Get the MAC address of the network adapter you'll be using. Set up a static lease for it, and add to WiFi ACL (if applicable).
10. ``sudo raspi-config``
   1. Configure WiFi and connect to your network (skip if you're going to be using wired Ethernet).
   2. Set your timezone
   3. Set up any other internationalization / localization options you need.
11. Finish and reboot.
12. SSH to the instance. Assuming this works, you can log out on the console, unplug the keyboard and HDMI, and continue over SSH.
13. Make sure we're running the latest: ``sudo apt-get update && sudo apt-get upgrade`` (note that this took quite some time for me).
14. Install what we'll need to run our kiosk mode browser, plus git: ``sudo apt-get install --no-install-recommends xserver-xorg x11-xserver-utils xinit openbox chromium-browser git xserver-xorg-video-fbturbo xserver-xorg-input-evdev python-xdg``
15. For the touchscreen installation (this code is awful, but it seems safe on a new system):
    1. ``git clone https://github.com/goodtft/LCD-show.git && cd LCD-show`` - it's probably worth looking at everything this does, since it seems to be pretty poorly written and has _lots_ of open issues. When I did this work, master was at [b8c10906a8501b484f98ce410b5dcc8d7aacaa73](https://github.com/goodtft/LCD-show/commit/b8c10906a8501b484f98ce410b5dcc8d7aacaa73) and had just been updated four days ago.
    2. ``cat /boot/cmdline.txt`` and record the contents, since this isn't backed up. Mine was: ``dwc_otg.lpm_enable=0 console=serial0,115200 console=tty1 root=PARTUUID=373b802e-02 rootfstype=ext4 elevator=deadline fsck.repair=yes rootwait``
    3. ``bash -ex LCD35-show``
    4. Wait for the system to reboot. Because of [this incredibly naive bug](https://github.com/goodtft/LCD-show/issues/68) there's some more we'll have to do since we changed the hostname of our Pi. On the positive side, once it reboots, you should see console messages.
    5. Log back in and ``cd LCD-show``.
    6. Trace through the ``if test "$nodeplatform" = "raspberrypi";then`` branch and figure out what it would do, then do it. On my system (Rpi 4 B+) this was: ``sudo cp -rf /usr/share/X11/xorg.conf.d/10-evdev.conf /usr/share/X11/xorg.conf.d/45-evdev.conf``
16. Reboot (again).

At this point ``/boot/cmdline.txt`` is: ``dwc_otg.lpm_enable=0 console=tty1 console=ttyAMA0,115200 root=/dev/mmcblk0p2 rootfstype=ext4 elevator=deadline rootwait fbcon=map:10 fbcon=font:ProFont6x11 logo.nologo``.

Now we should be ready to proceed with the actual software setup.

_Note:_ At this point just as I was beginning the steps below ("Kiosk Browser Setup"), and after getting some ``Under-voltage detected!`` messages, after the Pi was up and running for a few minutes the LCD would go white and the system would lock up, with just the red LED on and immediately dropping off WiFi when the screen went white. I tried reinstalling ``xserver-xorg-input-evdev`` (I'd originally used the binary from LCD-show) and also took part of the case off of the Pi as it was getting very hot. One of those things seems to have helped.

### Kiosk Browser Setup

These instructions are going by [this blog post](https://die-antwort.eu/techblog/2017-12-setup-raspberry-pi-for-kiosk-mode/).

1. ``sudo raspi-config`` - "Boot Options" -> "Desktop / CLI" -> "Console Autologin".
2. For the current chromium version (XXXX), set the contents of ``/etc/xdg/openbox/autostart`` to:
```
# Disable any form of screen saver / screen blanking / power management
xset s off
xset s noblank
xset -dpms

# Allow quitting the X server with CTRL-ATL-Backspace
setxkbmap -option terminate:ctrl_alt_bksp

# Start Chromium in kiosk mode
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' ~/.config/chromium/'Local State'
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]\+"/"exit_type":"Normal"/' ~/.config/chromium/Default/Preferences
chromium-browser --app=http://guarddog:8123/local/doorpanels/index.html
```
3. To start automatically on boot, append to ``/home/pi/.bash_profile``:
```
[[ -z $DISPLAY && $XDG_VTNR -eq 1 ]] && startx -- -nocursor
```
4. To make all this work: ``usermod -a -G tty pi``

For flipping the display around (power cable on top), it was changing ``/boot/config.txt`` ``s/dtoverlay=tft35a/dtoverlay=tft35a:rotate=270`` and then in ``/etc/X11/xorg.conf.d/99-calibration.conf`` at the end of the InputClass section adding two lines, ``Option "InvertX" "true"`` and ``Option "InvertY" "true"``.

Ok, that doesn't work. X never starts, and the error messages aren't helpful.

Per [this comment](https://github.com/goodtft/LCD-show/issues/17#issuecomment-306872877), change the last few lines of ``/boot/config.txt`` to:

```
# Enable audio (loads snd_bcm2835)
dtparam=audio=on
dtoverlay=ads7846,cs=1,penirq=17,penirq_pull=2,speed=1000000,keep_vref_on=1,swapxy=1,pmax=255,xohms=60,xmin=200,xmax=3900,ymin=200,ymax=3900
dtoverlay=tft35a:rotate=270
```

So now, digging into this more, it looks like X and chromium ARE starting up, I just can't see them on the display. All I can see are the console messages prior to boot.

So for one attempt, we try changing the final line of our ``/etc/xdg/openbox/autostart`` to: ``chromium-browser --app=http://guarddog:8123/local/doorpanels/index.html --temp-profile --verbose --no-touch-pinch &> ~/chromium-startup.out``
to attempt to capture the output.

Still no luck. Chromium is running, it's just not visible. And even with the ``--verbose`` flag, ``~/chromium-startup.out`` is empty. All I see is a screen with the console login messages (i.e. warnings about SSH enabled and the default password for the "pi" 
user, etc.) and that's it. I don't even see a prompt, just those login warnings and nothing else.

``sudo apt-get install menu``, to resolve one of the warnings in the Xorg log. Doesn't help.

instead, let's try using https://blockdev.io/raspberry-pi-2-and-3-chromium-in-kiosk-mode/

1. ``sudo apt-get remove openbox``
2. ``sudo apt-get install unclutter lightdm``
3. ``sudo raspi-config`` - Boot Options -> Desktop / CLI -> Desktop Autologin
4. ``sudo reboot``
5. ``rm .bash_profile``
6. ``create ~/.Xsession``:

```
xset s off
xset -dpms
xset s noblank
sed -i 's/"exited_cleanly": false/"exited_cleanly": true/' ~/.config/chromium-browser Default/Preferences
chromium-browser --noerrdialogs --kiosk http://guarddog:8123/local/doorpanels/index.html --incognito --disable-translate --window-size=480,320 --window-position=0,0
```

No luck there. It's all running - chromium-browser included. It seems like we got a little farther... since installing unclutter/lightdm and setting to desktop autologin, the system is now sitting at a black screen with a non-flashing underscore in the top left 
corner... Let's try another alternative...

``sudo apt-get install midori`` (and everything that comes with it...)
``sudo reboot``
Nothing different.
``nano .Xsession`` and change to:

```
xset s off
xset -dpms
xset s noblank
midori -e Fullscreen -e Navigationbar -a http://guarddog:8123/local/doorpanels/index.html
```

and then ``sudo reboot``.

.Xsession is running, unclutter is running, lightdm is running, midori is running... but once again just the steady underscore on the screen
.xsession-errors doesn't show anything after adding localhost:pi to access control list

still nothing

Let's try using this one instead: https://github.com/elalemanyo/raspberry-pi-kiosk-screen#raspbian-jessie

``sudo apt-get remove lightdm && sudo apt-get install lxde && rm .Xsession`` - install LXDE and all of the many, many packages that come with it.

``sudo reboot`` and see what happens. This time it drops me into a console session... which is rather interesting since previously we'd selected Desktop/GUI auto-login. I try ``startx -- -nocursor`` in that console session, from a USB keyboard... I can see 
processes running for Xorg and LXDE and other pieces of the graphical environment, but all I see on the console are the Xorg startup logs. Ctrl+Alt+Backspace doesn't seem to do anything.

``sudo raspi-config``, select Desktop Autologin again, reboot when prompted.

Once again, no desktop environment... just dropped to an autologin console session. This time Xorg isn't running in the background, which is even stranger. ``sudo raspi-config`` again. Select to wait for network at boot, and again select Desktop Autologin. 
Reboot.

Same thing, console prompt. ``startx -- -nocursor`` once again just shows Xorg startup messages and then sits there... I can see xorg, lxsession, unclutter, openbox, lxpanel, etc. running via ``ps aux`` but nothing graphical is visible on screen.

On a hunch, remove the 480x320 LCD and try HDMI instead. Boot up. Boot hangs for a while (presumably waiting for network) after starting D-Bus. Unlike previous attempts, Ctrl+Alt+F-keys actually work... Ctrl+Alt+F2 gives me a console login. Unfortunately trying 
to get back to the primary screen with Ctrl+Alt+F1 doesn't seem to work, and just gives me the same console prompt stuck on screen but without a blinking cursor. I'm able to SSH in and ``ps aux`` shows the system running but Xorg not. 

``sudo update-alternatives --config x-session-manager`` - confirm that ``startlxde`` in auto mode is selected.

reboot again. See what happens.

Nothing. Just hangs after the systemd boot messages, with "Started D-Bus System Message Bus" as the last one. There's nothing new in ``~/``. It doesn't appear that Xorg or anything related is actually running. systemctl tells me that ``graphical.target`` is 
loaded. I don't see any units obviously related to that aside from ``lightdm.service`` which is listed as active and exited. There are no system logs for lightdm.

