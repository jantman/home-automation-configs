# home-automation-configs

[![Project Status: Unsupported – The project has reached a stable, usable state but the author(s) have ceased all work on it. A new maintainer may be desired.](http://www.repostatus.org/badges/latest/unsupported.svg)](http://www.repostatus.org/#unsupported)

My home automation and home security configuration, scripts and tooling - mainly for [HomeAssistant](https://www.home-assistant.io/) / [AppDaemon](http://appdaemon.readthedocs.io/en/latest/), [ZoneMinder](https://zoneminder.com/), and related things.

__Note:__ This repository is really only provided as an example, and is not really "supported". See [Using It and Important Notes](#using-it-and-important-notes), below, for further information.

## Notice/Disclaimer:

The information I provide on home automation/security and surveillance is based on what I've set up for myself based on a balance of cost, ease of use, and security, and should be considered for hobby purposes only. My current system and code has grown organically over time and is not how I'd approach this if I started over from scratch. My code and system has a few obvious vulnerabilities and probably some non-obvious ones as well; I humbly but sincerely ask that you do not attempt to exploit these. I highly recommend that anyone implementing a similar system - especially if you also publish the details of it - have undocumented backup systems/devices. Finally, the systems that I describe are intended to provide some protection against or notification of crimes of opportunity, not targeted attacks. Please keep in mind that none of this is intended to protect against someone who targets *me* specifically (and takes the time to research me) as opposed to my home at random.

## What's Here?

* [appdaemon apps and configs](appdaemon/) - also includes my appdaemon logging helper
* [homeassistant/](homeassistant/) - my HomeAssistant configs
* [testing/](testing/) - configurations and scripts for testing HomeAssistant and AppDaemon locally using docker-compose
* [zoneminder/](zoneminder/) - some of my scripts and notes related to my ZoneMinder installation, including event image analysis and notifications
* RaspberryPi touchscreen-based alarm control panels - see [doorpanels.md](doorpanels.md)

## Using It and Important Notes

For anyone other than me, this is mainly intended to be a reference and inspiration. Much of this is quite custom to me and my setup. If you do want to use it, a few notes:

1. I generally work off of the ``master`` branch of this repo, since I assume I'm the only person directly using it. Before you take anything from this repo, it's probably best to check the commit history and assume that anything extremely new (i.e. minutes or hours old, maybe a day or two) _might_ not have all the bugs worked out yet or be complete.
2. Paths are hard-coded in some places. I've tried to minimize this or pull it out to configuration or at least constants at the top of files.
3. The actual system that this runs on is managed by Puppet using a private repository. Puppet clones this repo, sets up a bunch of symlinks, installs packages and dependencies, manages systemd services, etc. I'm making every effort to add documentation to this repo describing what's needed to make it work, but some dependencies might be missing. Sorry.
