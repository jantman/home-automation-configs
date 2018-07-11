# home-automation-configs

[![Project Status: Unsupported – The project has reached a stable, usable state but the author(s) have ceased all work on it. A new maintainer may be desired.](http://www.repostatus.org/badges/latest/unsupported.svg)](http://www.repostatus.org/#unsupported)

My home automation and home security configuration, scripts and tooling - mainly for [HomeAssistant](https://www.home-assistant.io/) / [AppDaemon](http://appdaemon.readthedocs.io/en/latest/), [ZoneMinder](https://zoneminder.com/), and related things.

__Note:__ This repository is really only provided as an example, and is not really "supported". See below for further information.

## What's Here?

Foo.

## Using It and Important Notes

For anyone other than me, this is mainly intended to be a reference and inspiration. Much of this is quite custom to me and my setup. If you do want to use it, a few notes:

1. I generally work off of the ``master`` branch of this repo, since I assume I'm the only person directly using it. Before you take anything from this repo, it's probably best to check the commit history and assume that anything extremely new (i.e. minutes or hours old, maybe a day or two) _might_ not have all the bugs worked out yet or be complete.
2. Paths are hard-coded in some places. I've tried to minimize this or pull it out to configuration or at least constants at the top of files.
3. The actual system that this runs on is managed by Puppet using a private repository. Puppet clones this repo, sets up a bunch of symlinks, installs packages and dependencies, manages systemd services, etc. I'm making every effort to add documentation to this repo describing what's needed to make it work, but some dependencies might be missing. Sorry.
