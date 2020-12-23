# couchpi

RaspberryPi touchscreen-based remote control on the end table next to my living room couch

## Hardware

* RaspberryPi 4B, 2019 Model, 4GB from [Amazon](https://www.amazon.com/gp/product/B07TC2BK1X/ref=ppx_yo_dt_b_asin_title_o01_s00?ie=UTF8&psc=1)
* RaspberryPi official 7" touchscreen display from [Amazon](https://www.amazon.com/gp/product/B0153R2A9I/ref=ppx_yo_dt_b_asin_title_o01_s00?ie=UTF8&psc=1)
* SmartPi Touch 2 case from [Amazon](https://www.amazon.com/gp/product/B07WXK38YM/ref=ppx_yo_dt_b_asin_title_o01_s02?ie=UTF8&psc=1)
* Sandisk Ultra 16GB MicroSD card from [Amazon](https://www.amazon.com/gp/product/B089DPCJS1/ref=ppx_yo_dt_b_asin_title_o01_s00?ie=UTF8&psc=1)

## Installation

1. Download [Raspberry Pi OS](https://www.raspberrypi.org/software/operating-systems/) with Desktop, 2020-12-02, kernel 5.4.
1. Write to the microSD card with: ``dd bs=4M if=2020-12-02-raspios-buster-armhf.img of=/dev/sdX conv=fsync status=progress``
1. mount the boot partition, ``cd`` to it
1. ``touch ssh`` to enable SSH access
1. write ``wpa_supplicant.conf`` to it
1. unmount
1. Place SD in the pi; assemble display and case
1. Log in with keyboard and monitor, get MAC address, add to wifi. Reboot. Should join the wifi. SSH in.
1. ``sudo apt-get update && sudo apt-get upgrade && reboot`` - this upgrades to Debian 10.7 and kernel 5.4.79
