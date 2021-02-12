# bedpi

RaspberryPi touchscreen-based HASS interface on the nightstand next to my bed. Almost identical to [couchpi](couchpi.md).

## Hardware

* RaspberryPi 4B, 2019 Model, 4GB from [Amazon](https://www.amazon.com/gp/product/B07TC2BK1X/ref=ppx_yo_dt_b_asin_title_o01_s00?ie=UTF8&psc=1)
* RaspberryPi official 7" touchscreen display from [Amazon](https://www.amazon.com/gp/product/B0153R2A9I/ref=ppx_yo_dt_b_asin_title_o01_s00?ie=UTF8&psc=1)
* SmartPi Touch 2 case from [Amazon](https://www.amazon.com/gp/product/B07WXK38YM/ref=ppx_yo_dt_b_asin_title_o01_s02?ie=UTF8&psc=1)
* Sandisk Ultra 16GB MicroSD card from [Amazon](https://www.amazon.com/gp/product/B089DPCJS1/ref=ppx_yo_dt_b_asin_title_o01_s00?ie=UTF8&psc=1)

## Installation

1. Download [Raspberry Pi OS](https://www.raspberrypi.org/software/operating-systems/) with Desktop, 2021-01-11, kernel 5.4.
1. Write to the microSD card with: ``dd bs=4M if=2021-01-11-raspios-buster-armhf.img of=/dev/sdX conv=fsync status=progress``
1. mount the boot partition, ``cd`` to it
1. ``touch ssh`` to enable SSH access
1. write ``wpa_supplicant.conf`` to it
1. unmount
1. Place SD in the pi; assemble display and case
1. Log in with keyboard and monitor, get MAC address, add to wifi. Reboot. Should join the wifi. SSH in.
1. ``sudo apt-get update && sudo apt-get upgrade && sudo reboot`` - this upgrades to Debian 10.8 and kernel 5.10.11
1. ``sudo raspi-config``
   1. System Options -> Hostname
   1. Localisation Options -> Locale
   1. Localisation Options -> Timezone
   1. System Options -> Network at Boot -> wait for network at boot
   1. If the filesystem was not already expanded: Advanced Options -> Expand Filesystem
   1. Finish, Reboot
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
