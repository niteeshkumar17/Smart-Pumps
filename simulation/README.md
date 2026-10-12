# Online simulation (Wokwi)

Runs the real firmware on a simulated ESP32 DevKit V1 (30-pin) in the browser, with a simulated
A02YYUW sensor on a tank that fills while the pump runs. Free, no account needed.

| Real board | In the simulation |
| --- | --- |
| ESP32 DevKit V1 | `wokwi-esp32-devkit-v1` |
| A02YYUW sensor + tank | custom chip `a02yyuw` (same UART frames, 9600 baud) with a tank display |
| G5NB relay + BC547 driver on GPIO32 | relay module on D32, active HIGH |
| Fused 230 V live | the ESP32 3V3 pin |
| Selector S1 | `s1_on` (left = 0/OFF, right = ON) and `s1_man` (left = AUTO, right = MAN) |
| Contactor KM / lamp H1 | blue LED / green LED |
| House Wi-Fi + HiveMQ Cloud | `Wokwi-GUEST` + public `broker.hivemq.com` (no TLS) |

Timers are shortened for testing: max run 3 min, dry-run window 20 s, rest between starts 10 s.

## Set up (once)

1. Run `.\make_sim.ps1` if you changed the firmware (it regenerates `wokwi\sketch.ino`).
2. Open https://wokwi.com/projects/new/esp32
3. Replace the contents of `sketch.ino` and `diagram.json` with the files from `wokwi\`.
4. File-tab menu (small arrow right of the tabs) > **New file...** > `a02yyuw.chip.json`, paste; again for `a02yyuw.chip.c`.
5. **Library Manager** > **+** > search `PubSubClient` > click it.
6. Press the green **Start** button. The first build takes 30-90 s on the free plan.

Sign in and press **Save** to keep the project.

## Tests

Click the sensor chip while the simulation runs to get its sliders.

| Test | Do | Expect (Serial Monitor) |
| --- | --- | --- |
| Auto start | Just start. Tank starts at 16 % | after 10 s `pump=ON`, relay LED + blue KM + green H1 on, water rises |
| Auto stop | Wait about 1 min | `level` reaches 95 %, `pump=OFF`, LEDs off |
| Restart at 20 % | Set **Water use** to 30 | level falls, pump restarts at 20 % |
| Selector OFF | Slide `s1_on` left | KM/H1 LEDs off even though the relay is on |
| Selector MAN | Slide `s1_man` right | KM/H1 on whatever the firmware says (manual override, tank can overflow) |
| Dry run | While pumping, set **Dry run** to 1 | after 20 s `fault=dry_run`, pump off and stays off |
| Sensor fault | Set **Sensor fault** to 1 | within 3 s `fault=sensor`, pump off |
| Max run | Set **Pump fill speed** to 2 | after 3 min `fault=max_run` |
| App / MQTT | see below | |

Faults `dry_run` and `max_run` stay latched until you send `reset` (or restart the simulation).

## Control it like the app

Open https://www.hivemq.com/demos/websocket-client/ > **Connect** (defaults are fine).

- Subscribe to `home/tanksim-nk7q2/tank/#` to see `level`, `distance`, `pump`, `auto`, `fault`, `status`.
- Publish `ON` / `OFF` to `home/tanksim-nk7q2/tank/pump/set` (manual pump), `.../auto/set` (auto mode),
  or any text to `.../reset` (clear a latched fault).

Your phone app can connect to `broker.hivemq.com`, port 1883, with the same topics.
This broker is public: anyone who knows the topic can see it, so use it only for testing.
