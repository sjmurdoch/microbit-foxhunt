# Radio Treasure Hunt

Hide-and-seek where the hidden thing gives itself away by radio. One BBC micro:bit — the **Treasure** — is hidden somewhere and quietly transmits. Everyone else carries a **Hound**, which cannot see the Treasure and cannot point at it, but can hear how strong its signal is, and beeps faster the closer you get. Radio amateurs do this as a sport, on foot and over several kilometres; it is called *amateur radio direction finding*, or a "fox hunt", after the hidden transmitter. This is a small version for a playground, a park or a school field.

**→ [Set your boards up in the browser](https://sjmurdoch.github.io/radio-treasure-hunt/)**

## Most people do not need this repository

That page does the whole job: pick a radio group, plug a micro:bit in over USB, and press *Set up as Treasure* or *Set up as Hound*. It writes MicroPython and the game together as one image, so there is no checkout, no Python, no toolchain — just Chrome or Edge, which are the only browsers with WebUSB. On anything else, including iPads, the page can still build a ready-made `.hex` to drag onto the board, but it cannot check the board is a V2 first. It also has a button that turns a spare board into a listener, so you can check the Treasure is transmitting before a session, and the three sheets to print: a 20-minute hunt card, a full worksheet, and a plan for whoever is running it.

## What you need

* **Two or more BBC micro:bit V2 boards.** V2 only, and this is not a preference: the Hound's feedback is a beep, and V1 has no speaker. The setup page refuses a V1 board.
* **A battery pack for each**, 2×AAA. Rechargeable NiMH cells of roughly 800–1000 mAh are what this was built around.
* **A computer running Chrome or Edge** to set the boards up. After that a board needs nothing but its battery.

## How it plays

The Treasure transmits three signals over and over — loud, medium and quiet — rather than one. The loud one carries a long way and the quiet one only a few metres, so *which* of them a Hound can hear says roughly how close you are, and the Hound turns that into a beep rate: slow, medium, then a rapid alarm when you are nearly on top of it. The LED matrix shows raw signal strength as a bar graph for the fine work.

The micro:bit's antenna is omnidirectional, so a Hound can never show a bearing — only a strength. Players find the Treasure by walking and watching whether the reading rises, and by turning on the spot: a human body absorbs enough 2.4 GHz to make the signal dip when the Treasure is behind you. Close in, the bar graph saturates and every bar looks the same at five metres as at one, so **button A** turns the Hound's sensitivity down a notch and **button B** puts it back.

Both boards must be on the same radio group, and a mismatch is completely silent — a Hound on the wrong group simply never hears anything. The setup page picks the group for you and warns when it changes between boards; pressing either button on the Treasure shows the group it is on.

## Working on the code

Everything goes through the Makefile, and you need [uv](https://docs.astral.sh/uv/):

```sh
make help            # every target
make check           # parse every source file, then run the tests
make devices         # list attached micro:bits and their firmware
make flash-fox       # write the Treasure (PORT= if two boards are attached)
make flash-hound     # write the Hound, both its files
make site            # build the site into site/
make site-serve      # serve it on localhost, where WebUSB works without HTTPS
```

Flashing targets depend on `check`, so code that fails its tests never reaches a board. Use `microfs` (`ufs`) and never `uflash`, which writes its own bundled firmware over whatever the board is running. The command line copies files onto whatever MicroPython is already installed; the browser writes the firmware too, which is the main way the two differ.

| | |
|---|---|
| On the device | `fox.py` (the Treasure), `hound.py`, `hound_logic.py` (the Hound's state machine, pure Python so it can be tested on a desktop), `hound_integration.py`, `radio_config.py` |
| Host tools | `flash.py` (writes and then verifies by hash), `calibrate.py` (outdoor RSSI calibration), `integration_check.py` (radio round trip over two boards) |
| The site | `build_site.py` and `web/` — the setup tool, the worksheet, the hunt card and the lesson plan |
| Tests | `test_hound.py`, `test_flash.py`, `test_site.py`; `make check` runs all three |

### "Fox" in the code, "Treasure" on the page

The hidden board is the `fox` everywhere it is machinery — `fox.py`, `make flash-fox`, the role key in `flash.ROLES` — and the **Treasure** in everything a player, a teacher or a scout leader reads. To a child who has not met the hobby, "fox hunt" is the blood sport, and a school should not have to explain that before anyone has switched a board on. `ROLE_LABELS` in `build_site.py` is the single place that translation happens.

## Documentation

[`AGENTS.md`](AGENTS.md) is the real documentation: the design, the radio characteristics measured on actual boards, the hardware gotchas that cost the most time, and the rules this codebase is maintained by. Read it before changing anything — several of the things it records look like details and are load-bearing. `CLAUDE.md` is a symlink to it. [`WEB_SETUP_PLAN.md`](WEB_SETUP_PLAN.md) and [`COGNITIVE-WALKTHROUGHS.md`](COGNITIVE-WALKTHROUGHS.md) cover the browser setup tool and the teaching materials; `archive/` holds superseded working documents.

## Licence

MIT — see [LICENSE](LICENSE).
