# home-automation-configs

There's really nothing here anymore, sorry! You can see what used to be here [in this commit](https://github.com/jantman/home-automation-configs/tree/c6db3db63c0273bcb8772ed22cf747fd1f56eae1). What _used to_ be here was a collection of configuration and notes about my ZoneMinder, HomeAssistant / AppDaemon, and related MicroPython ESP32/8266 code. It's all gone now:

* [HomeAssistant](https://www.home-assistant.io/) - I started over from scratch in late 2023, and decided to go the recommended route and configure as much as possible via the UI. Therefore I barely have any configuration files to share anymore. All of my HomeAssistant configs are automatically backed up, and I'm just not concerned with committing the auto-generated configs to git anymore.
  * I'd previously also been using HomeAssistant as a kludgey home alarm system, with some ZWave and ZigBee sensors. In late 2023 I moved into a house that has an actual wired alarm system, so that whole use case is gone.
* [AppDaemon](http://appdaemon.readthedocs.io/en/latest/) - The Automations feature of HASS has gotten good enough that so far I haven't had the need for custom code.
* `wemos_d1_mini` (ESP32 / ESP8266 MicroPython code) - I replaced these former thousands of lines of custom MicroPython code with [ESPHome](https://esphome.io/) and some relatively small YAML config files. Couldn't be happier.
* [ZoneMinder](https://zoneminder.com/) - Previously I had a _pile_ of custom code that was doing object detection and notifications for ZoneMinder. I've now just switched to using the vanilla upstream object detection and notification code in ZMES / MLapi.

## HomeAssistant Notes

* ESPHome "BlueTooth" (BLE) proxy debugging:ca
  * On the ESP side, `DEBUG` level logging is useless. `VERBOSE` level will give you messages like:
        ```
        [07:03:35][V][esp32_ble:314]: (BLE) gap_event_handler - 3
        [07:03:35][V][bluetooth_proxy:058]: Proxying 1 packets
        ```
    To see the actual details on the ESP side, your only option is to set the `VERY_VERBOSE` log level. If you have other things running on the same ESP, like I2C, you may want to quiet them down by setting [tag-specific log levels](https://esphome.io/components/logger.html#manual-tag-specific-log-levels). Unfortunately (and _very_ counter-intuitively, IMO), ESPHome doesn't let you set the log level for a single tag lower than the global level... so you can't really get detailed logs for a single tag, you need to get them for everything, and then if needed silence everything you _don't_ want. Ugh.
  * On the HomeAssistant side, we can luckily set a tag-specific logging level via a service call. By default, the global logger is configured for `warning` level. We can enable debug-level logging for BLE with this service call:
        ```
        service: logger.set_level
        data:
            bleak_esphome: debug
            govee_ble: debug
            inkbird: debug
            bluetooth: debug
            bluetooth_adapters: debug
            bluetooth_le_tracker: debug
            bluetooth_tracker: debug
            habluetooth: debug
            esphome: debug
            homeassistant.components.bluetooth: debug
        ```
    Note that the really important one here is `homeassistant.components.bluetooth` which will give us the actual BLE data.
