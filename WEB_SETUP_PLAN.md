# Web setup tool on GitHub Pages — plan

Status: not started. Written 2026-09-06.

Evidence markers used throughout: **[measured]** — run here on this machine, with the numbers; **[source]** — read out of the shipped library code, not merely its documentation; **[unverified]** — believed from vendor documentation or reasoning, and not yet settled. Section 9 lists everything still in the third category.

## 1. Why

Today the only way to get code onto a board is `make flash-fox` / `make flash-hound`: a checkout, `uv`, a working `microfs`, and a serial port. That is fine for whoever wrote the project and useless for anyone else running a hunt — a scout leader, a teacher, a parent — who needs a dozen hounds ready an hour before the event and has no toolchain.

The goal is a page on GitHub Pages that flashes a fox or a hound from Chrome over WebUSB, deployed by a workflow that runs the tests first and stamps the page with what it built.

## 2. Two pieces of software, two versions

The page carries **the web setup tool** (HTML/JS, changes when the site changes) and **the device code** (`fox.py`, `hound.py`, `hound_logic.py`, `radio_config.py`, changes when the game changes). They already differ here: `HEAD` is `db0b78c` (2026-09-06 15:32) while the last commit to touch a device file is `8d480db` (2026-09-06 15:19).

A board flashed last month runs last month's device code however often the site has been rebuilt since. So the page shows both stamps, and — this is the point — "which version is this board running?" is answered by asking the board, never by reading the site.

| Stamp | Derived from | Changes when |
|---|---|---|
| Site version | `git rev-parse --short HEAD` + committer date | any push to main |
| Device code version | `sha256` over the device files in role order, **with the `RADIO_GROUP` line normalised**, truncated to 8 hex chars; plus the last commit to touch any device file, and its date | the game changes |

Normalising the group line keeps the code version independent of the group, which is configuration and is reported separately. Both stamps go into `manifest.json`, the page footer, and the service worker cache name.

## 3. Flashing

`@microbit/microbit-connection` 1.0.0 (`./usb` entrypoint) with `@microbit/microbit-fs` 0.10.0. Both MIT, both Foundation-maintained.

```js
const fsHex = new MicropythonFsHex([{ hex: mp212, boardId: microbitBoardId.V2 }]);
for (const [src, target] of role.files) fsHex.write(target, sources[src]);
const image = fsHex.getIntelHex(microbitBoardId.V2);

const usb = createUSBConnection({ pauseOnHidden: false });
usb.addEventListener("serialdata", onSerial);   // MUST precede flash() — see below
await usb.connect();
if (usb.getBoardVersion() !== "V2") refuse();
await usb.flash(async () => image, { partial: true, progress });
```

**[measured]** against the stock 2.1.2 hex and this repo's hound files:

* the constructor accepts the stock hex unmodified (164 ms);
* **`getIntelHex(microbitBoardId.V2)` throws `Board ID requested not found.` if the constructor was given a bare hex string.** Construct with `[{hex, boardId}]` so the V2 selection is explicit and cannot be confused with a V1 image;
* the filesystem is **20,480 bytes**; the hound's three files use **9,856** (48%), leaving 10,624. No pressure, but it is a small budget and worth a test;
* the generated image is 1,266,800 chars;
* **round-trip is exact** — importing the filesystem back out of the generated hex returns `radio_config.py` (481 B), `hound_logic.py` (6,455 B) and `main.py` (2,554 B) byte-for-byte identical to the files on disk. That is the property the whole plan rests on.

`microbitBoardId` is `{V1: 0x9900, V2: 0x9903}` **[measured]**.

### Refusing v1 boards

The game is not merely untested on a micro:bit v1, it is **known broken**, for two independent reasons that no amount of care in the setup tool can fix:

* **v1 has no speaker.** The whole coarse-tracking channel is audio, and `hound.py` calls `speaker.on()` / `set_volume()`. On v1 that needs external hardware on an edge-connector pin.
* **`radio.config(power=N)` resets the group on v1.** AGENTS.md §4 records this under "things that are *not* problems" for v2 — the v2 firmware copies the current config and overwrites only the supplied keywords — and warns explicitly: *"The v1 firmware differs — do not carry this assumption backwards."* `fox.py` calls `radio.config(power=...)` three times every 200 ms, so on a v1 fox the group would be reset on every beacon.

(v1 also has 16 KB of RAM against the v2's 128 KB, which `hound_logic.py` has never been sized against.)

**The check is three-way, not two.** **[source, confirmed measured]** `BoardSerialInfo.parse` takes `device.serialNumber`, uses its first four characters as the board ID, and `BoardId` maps them:

| Board ID | Result |
|---|---|
| `9900`, `9901` | `V1` — refuse, and say why |
| `9903`, `9904`, `9905`, `9906` | `V2` — proceed |
| anything else, or an empty serial | **the `BoardId` constructor throws** — `connect()` fails with `Could not recognise the Board ID`, before any version is available |

So the page needs a distinct third message for an unrecognised board: almost certainly a micro:bit newer than this build of the library knows about, and the fix is to update the setup tool, not the board. A binary `getBoardVersion() !== "V2"` test would report that as "this is a v1 board", which is both wrong and unhelpful.

The board attached here is `9906…` → `V2`, and `normalize()` maps every v2 ID to `0x9903` **[measured]** — which is why building the image with `microbitBoardId.V2` is correct for a 9906 board and not just for a 9903 one.

Two further consequences of the mechanism:

* it reads the **USB serial number burned into the DAPLink interface chip, not the running firmware**. That is the hardware's own view, so a v2 board that `uflash` downgraded to v1 firmware still reports `V2` and the setup tool will repair it. This largely settles Q5 without sacrificing a board — `flash.board_generation()` asks `os.uname().machine`, which is the *firmware's* view, and the two disagree in exactly that case;
* it is a **hard dependency on `device.serialNumber` being populated**. If Chrome ever blanks it for anti-fingerprinting, `connect()` fails outright with "Could not detected ID from connected board" — not a soft degradation. `daplink.js` pointedly offers `readDaplinkUniqueId` as the fingerprinting-proof alternative, which suggests the Foundation has met this. See Q6.

### The download fallback cannot check anything

This is the weak point. The WebUSB path can refuse a v1 board; the **`.hex` download** — the fallback offered to Firefox, Safari and iPad users, who cannot use WebUSB at all — is dragged onto the `MICROBIT` drive with no code of ours involved. A v2-only Intel hex on a v1 board leaves a board that does nothing, which is AGENTS.md's worst case: *a board that looks dead*. A filename and a warning label are not a check.

`MicropythonFsHex` supports the fix directly: construct with both images (`IntelHexWithId[]`) and call `getUniversalHex()`, which DAPLink understands on both generations and from which each board selects its own slot. Put the real game in the V2 slot and, in the V1 slot, MicroPython v1 plus a `main.py` that scrolls something like `NEED V2`. A v1 board then **says why it cannot play** instead of appearing broken — the "never conclude anything from silence" rule applied to the one path we cannot guard interactively.

Costs, which make this a decision rather than an obvious win: it bundles the v1 MicroPython hex as well, roughly doubling the payload that the service worker must cache offline; and the stub is a new device file, so per AGENTS.md §9 it needs its place in `flash.ROLES`, `DEVICE_SRC` and `DEVICE_FILES`, or an explicit exemption. Recommended anyway — mixed fleets of 2016-era v1 boards are exactly what a school or scout group has in the cupboard.

### This writes firmware; `flash.py` does not

`flash.py` copies `.py` files onto whatever MicroPython is already installed. The web setup tool writes a full image. Consequences:

* it erases the filesystem — harmless, we write every file;
* **it removes the entire `ufs put` failure class.** Section 5 of AGENTS.md exists because a board that reboots mid-transfer starts executing a half-written `main.py` and corrupts the rest of the copy, which is why `flash.py` halts the board, deletes `main.py`, verifies each file by hash and writes `main.py` last. None of that machinery is needed here: DAPLink halts the target for the whole flash and the filesystem arrives as one image. **Do not port `main.py`-last ordering or hash verification into the JS.** The `ROLES` mapping still matters (which files, and which one becomes `main.py`); its *order* does not;
* the failure mode changes from silent to loud: a `ufs put` could report success with wrong bytes on the device, whereas an interrupted hex flash leaves a board that visibly does not boot **[unverified — Q7]**;
* it pins the MicroPython version. AGENTS.md §4 warns that a firmware change invalidates the radio measurements if the radio stack changes, and §5 warns that a firmware update erases the filesystem;
* **it can silently downgrade a board.** This is the same harm as the `uflash` trap in gotcha 6, arriving by a different route: a board running a future 2.2.x that is flashed here silently reverts to 2.1.2. The page must read the board's version first and say so before overwriting it.

The bundled hex is pinned to **2.1.2**, the version the field calibration was run on, committed at `web/micropython/micropython-microbit-v2.1.2.hex` with its SHA-256 (`66fae07b7177…`, 1,239,726 bytes **[measured]**) asserted by a test — so the local build needs no network and cannot silently pick up a re-cut release asset.

It gets its own constant, `BUNDLED_MICROPYTHON`. It must **not** reuse `flash.LATEST_MICROPYTHON`, which means "the newest release that exists, used only to hint that a board is behind". Same value today, different meanings, and they diverge on purpose the moment 2.1.3 ships. Giving one constant two meanings is the §6 bug this project has already been bitten by twice.

### Serial runs over CMSIS-DAP, not the CDC port

**[source]** `usb/daplink.js`: serial is DAPLink vendor commands `0x83` (read) and `0x84` (write), polled at **1 ms** with up to 255 bytes per read. It never opens `/dev/cu.usbmodem*`. This has four consequences that reshape section 5:

1. **AGENTS.md's auto-reset gotcha does not apply.** "Opening or closing the USB serial port reboots the micro:bit" is about the CDC port. The browser never opens it, so a browser connection never auto-resets the board — not reliably, not unreliably. There is none of §5's "the first open didn't reset, later ones did" ambiguity to work around; the browser must simply always ask for a reset explicitly. `flash.py` reached the same conclusion by a harder road.
2. **The library already resets after flashing, and captures the startup output.** `connection.js`: *"Start serial before resetting so we capture startup output. For full flash FLASH_CLOSE already reset the target… Partial flash writes pages via SWD without resetting"* — followed by `cortexM.reset()` in the partial case. The DAPLink serial ring buffer is 512 bytes and holds early output until the first read.
3. **The `serialdata` listener must be attached before `flash()` is called.** CDC saturation runs only `if (!this.cdcSaturated && this.hasSerialEventListeners())`. Get the ordering wrong and post-flash serial output is consumed by the CDC side and never seen — silence that looks exactly like a healthy fox. This is precisely the failure mode AGENTS.md §9 warns about, and it is an ordering bug in our code, not the library's.
4. **`softwareReset()` is safe.** It is `cortexM.softwareReset()`, an SWD `SYSRESETREQ` — a real hardware reset of the nRF52, the clean kind under gotcha 10. It is *not* MicroPython's Ctrl-D soft reboot. The name will mislead anyone who has just read gotcha 10, so it needs a comment at the call site.

**[source]** `usb/cdc-saturation.js` runs a Thumb blob on the halted target to push 2,048 dummy bytes through the UART, filling DAPLink's CDC buffers so the CDC side stops consuming — *"Once saturated, the buffers stay full until physical disconnect."* So the browser and a host-side serial reader genuinely contend for the same UART data, in both directions. See Q10 and Q17.

## 4. Radio group, chosen per flash

The highest-value feature for someone actually running a hunt. `RADIO_GROUP` is baked at 16, so two hunts in one park collide, and the symptom is silence — indistinguishable from out of range or a flat fox.

The page offers a group picker (1–255, excluding 0 and 42 for the reasons `radio_config.py` already gives), remembers it in `localStorage`, and shows it in the header and in every success message so boards can be labelled as they are flashed.

Implementation reuses the idiom already in `calibrate.py:53` — a source template with a `__GROUP__` placeholder and `.replace()`, not `%`-formatting. In `build_site.py`:

```python
def render_radio_config(group):   # pure, testable, no I/O
    ...  # radio_config.py with its RADIO_GROUP assignment substituted
```

The template is derived from the real `radio_config.py` by substituting that one line, so the docstring and the 0/42 warning travel with it and there is no second copy to drift. A test asserts `render_radio_config(RADIO_GROUP)` reproduces `radio_config.py` byte-for-byte.

**This feature makes AGENTS.md §5's silent failure easier to hit, so it has to carry its own guard.** "Changing the radio group means reflashing both boards… the symptom is silent." A picker that is easy to change between flashes invites flashing the fox on 23 and the hound on 16. So the page keeps a session log of what it flashed — board unique ID, role, group — and warns loudly when the group differs from the previous board flashed in the same session. One fox per group; the page says so.

## 5. Beyond flashing

### Confirm which board before overwriting it

AGENTS.md §5 is emphatic that silently picking a board is worse than refusing to: *"opening the fox when you meant the hound looks exactly like being out of radio range, and that is a miserable thing to diagnose in a field."* `flash.pick_port` prints both boards with serial numbers and exits rather than guessing.

The browser has the same hazard in a worse form: with two boards attached, Chrome's picker shows **two identical entries** — same name, no way to tell them apart. The mitigation:

* **[source]** `readDaplinkUniqueId` (vendor command `0x80`) returns the same 48-character string `make devices` prints — for the board attached here, `9906360200052820726e40a4da840fa7000000006e052820`. The library notes it *"isn't affected by browser anti-fingerprinting"*, unlike `USBDevice.serialNumber`. Show it on connect, so a board can be matched against `make devices` output and against a physical label;
* after connecting and before flashing, run the identify step below and state what is about to be overwritten: *"this board is currently a FOX on group 16 — flash it as a HOUND on group 23?"* That turns the wrong-board error into a question instead of a silent loss;
* recommend attaching one board at a time, prominently.

### Identify a board

Reads the truth off the board rather than trusting a marker file, so it works on boards flashed by `make flash-*` too and cannot drift.

**The fingerprint is computed on the device, not by streaming files back.** Reading `hound_logic.py` out over the REPL means 12.9 KB of hex through a 512-byte ring buffer, which is a needless fight with the transport. Instead, interrupt to the raw REPL and have MicroPython compute a small checksum over each file, printing only the digest — a few dozen bytes per file, immune to the buffer size. The same checksum is computed in Python at build time and shipped in `manifest.json`, so the comparison is exact. `radio_config.py` is 481 bytes and *is* read back verbatim, because the group is the field-critical fact and is worth seeing in full.

Reported: role (by matching `main.py`'s digest against each role's), device code version or "differs from this site", radio group, MicroPython version (`os.uname().release`), and the DAPLink unique ID.

Sequence: interrupt (`\r\x03\x03`), enter **raw** REPL (`\x01`), run the checksum snippet, leave raw REPL (`\x02`), then `import microbit; microbit.reset()` to put the game back.

**Ctrl-D inside the raw REPL means "execute", not "soft reboot"** — it is not gotcha 10. The thing never to send is Ctrl-D at the friendly prompt. This needs a comment at the call site, because it looks alarming, as does `softwareReset()` (§3).

### Post-flash boot check

A port of `flash.py:boot_check`, with the same three-way test, because `fox.py` and `hound.py` print nothing when healthy:

* a REPL banner or `>>> ` means `main.py` is missing or returned — failure;
* `Traceback`, or `^\w*(Error|Exception):` — failure, shown verbatim;
* otherwise, running.

`flash.py`'s third check — *did the board actually reset?* — exists because the CDC auto-reset was unreliable. Here the library resets the target itself and starts serial first specifically to capture the startup output (§3), so the browser gets the reset for free. What it must not do is skip attaching the serial listener before `flash()`, which would produce the same false pass by a different mechanism.

Framing for the UI: the boot check says *it is running*, the radio monitor says *it works*.

### Live radio monitor

One click flashes the existing `integration` role (`hound_integration.py`, already in `flash.ROLES`) and streams its output. It already prints `HOUND_START` and `HOUND_RX: %r RSSI: %d`, so the browser parses those and applies `integration_check.py`'s criterion — all three of `Z1`/`Z2`/`Z3` heard. `ZONES`, `LISTEN_SECONDS` and the marker strings come from `manifest.json`, emitted by Python, not retyped in JS.

Better than the CLI version, which needs *both* boards on USB: here the fox runs on its battery where it will actually sit, and only the listening board is tethered. A live RSSI readout doubles as a range check, and is the closest thing to positive confirmation that the fox is alive — the fox is dark and silent by design.

**This replaces the game on that board.** The CLI says so and expects you to run `make flash-hound` afterwards; a web page used by a non-expert must be louder. The monitor screen states it up front and ends with a one-click "put the game back" that reflashes the hound with the group it had.

Minor, pre-existing: `hound_integration.py` never constructs a `NeoPixel`, so per the AGENTS.md §8 finding an attached strip keeps its random power-on state while the monitor runs. Worth a line in the UI, or three lines in `hound_integration.py` to match `fox.py` and `hound.py`.

### Organiser and player guidance

Inline on the page, not a link away: pre-hunt checklist (fresh cells, both boards on the same group, fox display dark, range check, boundaries, time limit), the beep and button explanation (since folded in from `PLAYER_GUIDE.md`, which is gone), expected ranges from the field calibration (Z3 gone by 8 m, Z2 fringe at 8 m, Z1 out to 20 m and beyond), and a symptom-to-cause table.

That table must include **"display blank around 15 m while the audio keeps working is expected"** — it is the ground-reflection null against `MIN_RSSI`, documented in `hound_logic.py`, and it looks exactly like a fault.

### Offline

A hunt happens in a field. The site is a PWA whose service worker caches the shell, the hex and the device files, so a board can be reflashed at the event with no signal.

The cache name is the site stamp, with `skipWaiting`/`clients.claim` and a visible "new version — reload" prompt. Getting this wrong pins organisers on a stale site forever, which is exactly the silent-failure class this project exists to avoid.

## 6. Audit against the AGENTS.md flashing gotchas

| AGENTS.md | Handled by |
|---|---|
| §5 `uflash` downgrades a v2 board | Detection reads the hardware USB serial, not the firmware, so such a board still reports `V2` and gets repaired — §3 |
| §4 `radio.config(power=)` resets the group on v1 | One of the two reasons the game is *known broken* on v1, not merely untested — §3 |
| v2-only hardware (speaker) | Three-way board check before flashing; universal hex with a `NEED V2` stub for the unguardable download path — §3 |
| §5 flashing never touches firmware | Explicitly reversed here, §3, with the downgrade warning that follows from it |
| §5 `LATEST_MICROPYTHON` is a hint only | Separate `BUNDLED_MICROPYTHON`; regression test |
| §5 firmware update erases the filesystem | One atomic image, so ordering cannot go wrong; §3 |
| §5 `ufs put` is not safe on its own | Whole class removed; do not port the workaround — §3 |
| §5 silence is what success looks like | Three-way boot check; serial listener attached before `flash()` |
| §5 file lists per role, `main.py` last | Derived from `flash.ROLES`; ordering explicitly not needed |
| §5 changing the group means reflashing both | The group picker makes this easier to hit, so §4 adds a session guard |
| §5 opening the serial port reboots the board | Does not apply — serial is CMSIS-DAP, not CDC (§3) |
| §5 auto-reset is not reliable enough to build a check on | Library resets the target itself and captures startup output |
| §5 `ufs` picks the first board and cannot target one | The picker is *worse* — two identical entries. DAPLink unique ID plus confirm-before-overwrite, §5 |
| §7.4 NeoPixels power on in a random state | Noted for the integration role, which does not blank them |
| §7.10 Ctrl-D after the radio corrupts the heap | Raw-REPL Ctrl-D is "execute", not a soft reboot; `softwareReset()` is SWD. Both need comments |
| §9 a device file must be in three places | Manifest derived from `flash.ROLES`, so still three, not four |
| §9 two copies of a fact will drift | Group template, `ZONES`, markers and checksums all emitted from Python |
| §9 never conclude anything from silence | Boot check, and the listener-ordering trap in §3 |
| §9 run `make check` before claiming a fix | The deploy workflow gates on it |

## 7. Files, workflow, tests

**New:** `build_site.py` (host tool: derives the manifest from `flash.ROLES`, renders `radio_config.py`, computes both stamps and the per-file checksums, templates `index.html`, drives esbuild; inert at import like `calibrate.py` so tests can import it); `test_site.py`; `web/index.html`, `web/app.css`; `web/src/{main,flasher,repl,monitor,sw}.js`; `web/micropython/micropython-microbit-v2.1.2.hex`; `package.json` + lockfile; `.github/workflows/pages.yml`.

**Modified:** `flash.py` (add `BUNDLED_MICROPYTHON`); `Makefile` (`HOST_SRC +=`, new `site` target depending on `check`, and `site-serve`); `pyproject.toml` (`testpaths`); `.gitignore` (`site/`, `node_modules/`); `AGENTS.md` (a web-flasher section, the two-version distinction, and the new gotchas). `site/` is build output and is not committed.

**Workflow** — on push to `main` plus `workflow_dispatch`, `permissions: {contents: read, pages: write, id-token: write}`, `concurrency: {group: pages, cancel-in-progress: false}`. Build job: `actions/checkout` with `fetch-depth: 0` (a shallow clone cannot find the last commit that touched a device file), `setup-uv`, `setup-node`, then `make check`, `make site`, `upload-pages-artifact` on `site/`. Deploy job: `needs: build`, `environment: github-pages`, `deploy-pages@v4`. Tests gate the deploy, mirroring the rule that flashing targets depend on `check` — the web setup tool is a flashing target.

**Tests (`test_site.py`)** — every role and file in `flash.ROLES` reaches the manifest with contents equal to the on-disk bytes; `render_radio_config(RADIO_GROUP)` reproduces `radio_config.py` byte-for-byte, parses with `ast`, defines `RADIO_GROUP == n`, and rejects 0, 42 and anything outside 1–255; the generated file passes the existing `test_radio_group_is_not_hardcoded_in_device_code` and no-f-strings checks; the device-code hash is unchanged across two groups; the checksum algorithm shipped in the manifest matches the one the device snippet computes, exercised against the real files; the bundled hex exists with the recorded SHA-256; `BUNDLED_MICROPYTHON` and `LATEST_MICROPYTHON` are separate names; the hound's files fit the 20,480-byte filesystem with margin.

## 8. What was settled, and how

| | Result |
|---|---|
| Q11 `MicropythonFsHex` accepts the stock 2.1.2 hex | **Yes [measured]**, 164 ms; round-trip byte-exact; 9,856 of 20,480 bytes used by the hound |
| `getIntelHex` call shape | **Constructor needs `[{hex, boardId}]` [measured]** — the bare-string form throws on `getIntelHex(V2)` |
| Q1 transport for serial | **CMSIS-DAP vendor commands `0x83`/`0x84` [source]**, not the CDC port |
| **Q1a does that reach MicroPython's REPL** | **PASS [measured]** — Ctrl-C returned `KeyboardInterrupt`, the banner and `>>> ` |
| **Q2a raw REPL and checksum-on-device** | **PASS [measured]** — raw REPL entered, all three files digested, every digest matching the host |
| **Q6 is `device.serialNumber` populated** | **Yes [measured]** — the full 48 chars, identical to `make devices` |
| Q2 throughput | Polling is **1 ms, 255 bytes/read [source]**, so reading is not the bottleneck; the **512-byte ring buffer** is. Design changed to checksum-on-device, which sidesteps it |
| Q3 does the target reset after flash | **Yes, both paths [source]**, and serial is started first to capture startup output |
| Q4 does the boot check need a reset guard | **No** — but it needs the serial listener attached before `flash()`, or it false-passes the same way |
| Board version detection | **First 4 chars of the USB serial [measured]**: V1 = `9900`/`9901`, V2 = `9903`–`9906`, anything else **throws at connect**. The attached board is `9906` → V2 |
| Q5 does a `uflash`-downgraded v2 still report V2 | **Almost certainly yes** — detection reads the DAPLink-burned USB serial, not `os.uname()`. Confirm on a board if one can be spared |
| Hex board ID for a 9906 board | `normalize()` → `0x9903` **[measured]**, so `microbitBoardId.V2` is correct for every v2 variant |

### The probe, 2026-09-06

Run from a throwaway page against the attached board (v2, `9906…`, MicroPython 2.1.2, DAPLink serial `9906360200052820726e40a4da840fa7000000006e052820`). Nothing was flashed; the board was reset at the end and resumed.

```
usbDevice.serialNumber : 9906360200052820726e40a4da840fa7000000006e052820
manufacturer / product : Arm / BBC micro:bit CMSIS-DAP
getBoardVersion()      : V2          board id (first 4): 9906
getDeviceId()          : 3712166694

Ctrl-C  -> "…KeyboardInterrupt: \r\nMicroPython v1.18 on 2023-10-30;
            micro:bit v2.1.2 with nRF52833\r\nType \"help()\"…\r\n>>> "
Ctrl-A  -> "raw REPL; CTRL-B to exit\r\n>"
snippet -> UNAME 2.1.2 micro:bit with nRF52833
           LS ['radio_config.py', 'hound_logic.py', 'main.py']
           SUM radio_config.py 3318680731
           SUM hound_logic.py  2215835840
           SUM main.py           82801265
```

Every digest matches the host computing the same function over the repo's files, with `hound.py` as `main.py` — and the three roles' entry points digest distinctly (fox 2507183434, hound 82801265, integration 1394167193), so the role is unambiguous. **Identify works end to end, and it works on a board this page never flashed.**

Four things follow for the implementation:

* **Writes must be chunked.** DAPLink's serial write carries a single length byte, so a write is capped at 255 bytes. The probe used 32-byte chunks with a 15 ms gap and lost nothing.
* **Discard whatever arrives before the first deliberate write.** The probe's first read began `"ba.odKeyboardInterrupt: "` — a fragment of stale ring-buffer content. `flash.py` calls `reset_input_buffer()` for exactly this reason and the browser needs the equivalent: write, settle, then start believing what comes back. A boot check that parsed that leading fragment would be reading noise.
* **`flash.py`'s `REPL_MARKERS` are visible over this transport.** Both `Type "help()"` and `>>> ` came through intact, so the boot check's "the board fell through to the REPL" test ports across unchanged.
* **The reset technique ports too.** `import microbit` / `microbit.reset()` echoed exactly as `flash.py:_hard_reset` expects, so the same echo-confirmation trick works.

### The second probe, 2026-09-06 — flashing, two boards, v1, and uflash

Run across two v2 boards (`…436111…` and `…726e40…`) and one v1 board (`9901…`).

**The v1 refusal works, on a real v1 board.** Board id `9901` → `V1`, and the setup tool stopped before writing anything. The v1 board's DAPLink connected over WebUSB without complaint, so the refusal path is reachable rather than masked by a `firmware-update-required` failure. Note the product strings differ cosmetically between generations — v1 reports `ARM / "BBC micro:bit CMSIS-DAP"` (uppercase, with literal quote characters in the name), v2 reports `Arm / BBC micro:bit CMSIS-DAP`. **Never match on these strings**; use the board ID.

**Identify: 20/20 consistent.** Q2a is fully settled, and it identified *two different roles* on boards flashed by the CLI — a fox (`main.py` digest 2507183434, two files) and a hound (82801265, three files).

**Flashing is far faster than estimated, because it is partial from the outset.**

| Case | Result |
|---|---|
| firmware **differs** (board on 2.0.0-beta.5) | **FullFlashing, 22.7 s** |
| firmware matches, role change fox → hound | **PartialFlashing, 2.5 s** |
| firmware matches, identical image | **PartialFlashing, 1.4 s** |
| boot check, every case | startup output `""` → `BOOT OK: running silently` |
| filesystem verified from the board | all three digests **MATCH** |

**A sixteen-fold spread, and it falls along a line the user can predict.** A board whose firmware already matches is effectively instant; a board arriving with anything else costs 22.7 s. So the progress bar and a "do not unplug" state are needed for the first flash of a given board, and the page can say which case it is *before* starting, because it knows the board's version by then. In a hall full of boards from a school cupboard, most will take the slow path once and the fast path forever after.

**The repair is confirmed.** That 22.7 s flash took the `uflash`-ed board from MicroPython 2.0.0-beta.5 back to 2.1.2, verified afterwards by `make devices`. So the web setup tool does fix a board that `uflash` has moved onto old firmware — the claim in §3 now rests on a measurement rather than a mechanism.

The image was 1,266,800 chars using 9,856 of 20,480 filesystem bytes, matching the Node measurement exactly. The group-16 `radio_config.py` rendered by substitution digested to 3318680731, identical to the repo file — the byte-for-byte property the plan's test will assert.

**Q6: exclusion filters work.** With two boards attached, excluding one board's `serialNumber` removed it from the picker; excluding both left the picker empty and `connect()` returned `no-device-selected`. The flash-many-boards flow is viable.

**Q5: confirmed, and AGENTS.md gotcha 6 is wrong.** After deliberately running `uflash` on a v2 board, `getBoardVersion()` still reported **V2** — detection is firmware-independent, as predicted. But `make devices` then showed what `uflash` had actually done:

```
/dev/cu.usbmodem11202  micro:bit v2  MicroPython 2.0.0-beta.5  (2.1.2 available)
```

**`uflash` 2.0.0 did not downgrade the board to v1 firmware.** It installed MicroPython **2.0.0-beta.5** — a genuine *v2* build (`os.uname().machine` still reports nRF52833), three releases old, which is what these boards originally shipped with per §4. Almost certainly it ships a universal hex and DAPLink selected the v2 slot.

So the harm is real but different from what AGENTS.md gotcha 6 describes: **the speaker is not disabled and the board is not made into a v1**; it is silently moved onto old firmware, which §4 warns can invalidate the radio measurements, and which `make devices` correctly flagged. The gotcha needs rewriting, and `describe_firmware`'s "Likely a uflash downgrade; reflash with a v2 hex" hint is aimed at a case that may not occur with this uflash version. **This is a finding about the existing repo, not about the web setup tool**, and it is worth confirming independently before editing AGENTS.md — one `uflash` run is one data point.

The firmware write also emptied the filesystem (`LS []`), exactly as §5 says a firmware update does.

**Two implementation lessons from the noise:**

* **Leading output can be lost, not merely stale.** One raw-exec reply arrived as `".bit with nRF52833…"` — about 28 characters missing from the front. Identify must not parse positionally; print a sentinel before the payload and slice from there. This is the same discipline as gotcha 10b but for loss rather than staleness.
* **`backgrounderror` is noisy and mostly benign.** `No device opened` and `USB read failed` both appeared around connect/disconnect without anything actually failing. The UI must not treat every background error as a flash failure. Separately, **revoking USB permission mid-session kills the connection** (`device-disconnected`) and this harness needed a page reload to recover — the real flasher must handle that path rather than dying.

## 9. Open questions to settle before implementing

AGENTS.md §9 is blunt about what documentation is worth: almost every wrong belief in this project's history survived because someone reasoned instead of measuring. Each of these names the cheapest experiment that settles it.

~~**Q1a.** Does the CMSIS-DAP serial path reach MicroPython's REPL?~~ **Answered 2026-09-06: yes.** See §8. The largest risk in the plan is gone and §5 does not need a Web Serial fallback.

~~**Q2a.** Does checksum-on-device work over this transport?~~ **Answered 2026-09-06: yes**, first try, all three files, digests matching the host exactly. Residual: the probe ran **once**. Before shipping identify, run it twenty times in a loop and record the failure rate — a path that works once and fails one time in ten would produce "this board is running something else", which is worse than no answer at all.

~~**Q5.** Does a `uflash`-ed v2 board still report `V2`?~~ **Answered 2026-09-06: yes** — detection is firmware-independent. The test also showed AGENTS.md gotcha 6 is wrong about what `uflash` 2.0.0 does; see §8. **New follow-up (Q19):** confirm that independently, then correct gotcha 6 and reconsider the `describe_firmware` hint.

~~**Q6.** Do the multi-board exclusion filters work?~~ **Answered 2026-09-06: yes**, on both halves — `device.serialNumber` is populated, and excluding it removes the board from Chrome's picker. The flash-many-boards flow is viable.

**Q18. Should the download fallback ship a universal hex with a `NEED V2` stub?** §3 recommends it; the cost is bundling the v1 MicroPython image and a fourth device file. The alternative is accepting that one path can hand someone a v1 board that looks dead.
*Check:* no measurement needed — but if adopted, verify on an actual v1 board that the stub scrolls, because a stub that fails silently is worse than none.

~~**Q7.** How long is a full flash?~~ **Answered 2026-09-06: 22.7 s full, 1.4–2.5 s partial** — see §8. The 62-byte chunk estimate was about right for the full path.
*Still open:* what an **interrupted** flash leaves behind. Pull the cable mid-flash and confirm the board fails visibly rather than silently — the plan claims the failure mode is loud, and that is still reasoning rather than measurement. Now cheap to test, since recovery is one 23 s reflash.

**Q8. Does a WebUSB-flashed hound behave identically to a `make flash-hound` one?** The web setup tool installs 2.1.2; a board that arrived with something else changes runtime as a side effect, and AGENTS.md §4 warns that can invalidate the calibration.
*Check:* flash one board each way, run both against the same fox at a fixed distance, compare bars and zones.

**Q9. Does the game work on a group other than 16?** In MicroPython the group is address matching rather than RF channel, so propagation should be unaffected — but the entire calibration was taken on 16 and the group picker is a headline feature.
*Check:* flash both boards to another group, confirm they hear each other, spot-check RSSI against the 2026-09-06 figures.

**Q10. Does a host-side serial reader starve the browser's serial?** Sharper than "device-in-use": the two do not fight to *claim* the interface, they fight for the *data*, which is why the library saturates the CDC buffers at all.
*Check:* hold the port with `flash.py list` or `screen`, then read serial from the browser.

**Q17. Does using the browser break the CLI tools until the board is unplugged?** *"Once saturated, the buffers stay full until physical disconnect"* [source]. So after the page has used serial, `make integration` or `calibrate.py` may see stale dummy bytes, or nothing.
**Answered 2026-09-06: transient, not permanent.** Run cleanly this time — a browser flash, then `make devices` with nothing in between and no replug:

```
attempt 1   /dev/cu.usbmodem11202  firmware unknown (board busy?)
attempt 2   /dev/cu.usbmodem11202  micro:bit v2  MicroPython 2.1.2
attempt 3   /dev/cu.usbmodem11202  micro:bit v2  MicroPython 2.1.2
```

So the CLI **does** fail immediately after a browser flash, but it recovers on the next attempt — this is contention while the page is still polling serial at 1 ms, not the permanent buffer saturation the library's *"stay full until physical disconnect"* comment led me to expect. I over-read the first failure; the retry settled it.

Consequences, smaller than feared: the page should say "if a command-line tool reports the board busy just after using this page, close the tab or simply retry", and no unplugging is required. Worth noting that `flash.py:board_info` gives up after `tries=3` and reports `firmware unknown (board busy?)`, which is exactly the confusing-but-honest message it was designed to produce — the listing is the fragile part, while `verified_put` retries six times per file.
*Residual:* `make integration` was not run, because it needs a fox and an integration board and only one board was free. Worth repeating once the two-board field test happens.
*If wrong:* the page must say "unplug and replug before using the command-line tools", and AGENTS.md needs the gotcha. This is a new silent failure the web setup tool would introduce into existing tooling, so it matters more than its position in this list suggests.

~~**Q12.** Does the picker label the board "LPC1768" the first time?~~ **Not observed here.** Permissions were reset and the board still presented as `BBC micro:bit CMSIS-DAP`. Either it is version- or platform-specific, or it no longer happens. **Do not put "it may say LPC1768" in the UI copy on the strength of a support page alone** — say what these boards actually showed, and revisit only if someone reports otherwise.

**Q13. Does the service worker scope work under the `github.io` project subpath?** The site lands at `https://<user>.github.io/radio-treasure-hunt/`, so paths must be relative and the worker's scope is that subpath. A classic way to ship something that works on `localhost` and not in production. Cannot be settled locally.

**Q14. Is WebUSB available on a school Chromebook?** Probably the most common deployment target, and untested.

**Q15. Should `fox.py` and `hound.py` print a startup marker?** They print nothing when healthy, so the boot check can only be negative. AGENTS.md §9 calls a marker the cheapest way to make a flash verifiable, and `hound_integration.py` and the calibration logger both have one. Now that the library is known to capture startup output into a 512-byte buffer [source], `print("FOX_READY")` / `print("HOUND_READY")` would make the check positive for one line each, invisible in the field. It changes device code, so it sits outside the scope above — but it is the single cheapest improvement to the flow and worth deciding early.

**Q16. Where does the repo live?** There is no git remote and no tags. Before anything deploys: create the GitHub repo, push `main`, set Settings → Pages → Source to *GitHub Actions*.

**Q19. Correct AGENTS.md gotcha 6.** Measured once: `uflash` 2.0.0 on a v2 board installed MicroPython **2.0.0-beta.5**, a genuine v2 build, not v1 firmware — so it does not disable the speaker and does not make the board a v1. The documented gotcha, and `flash.describe_firmware`'s "Likely a uflash downgrade; reflash with a v2 hex" hint, both describe a failure that this version of `uflash` may not produce.
*Check:* repeat on another board to confirm it was not a one-off, and check whether `uflash` ships a universal hex. Then rewrite the gotcha to the real harm — a silent move onto three-releases-old firmware, which §4 warns can invalidate the radio measurements.
*Scope:* this is a correction to the existing repo, independent of the web setup tool, and should probably land as its own commit.

## 10. Gotchas found in research

Sources: the Micro:bit Foundation's developer and support sites, and the shipped library code, read 2026-09-06.

**Browser and platform**

1. WebUSB is Chrome/Edge 79+ only, on a secure context. No Firefox, no Safari, **none at all on iOS or iPadOS**. Feature-detect `navigator.usb` and explain, rather than offering a button that fails.
2. Every role therefore also gets a **download `.hex`** button, which works in any browser by dragging onto the `MICROBIT` drive — and which **cannot check the board version**, since nothing of ours runs. Label it clearly, and preferably ship a universal hex whose v1 slot scrolls `NEED V2` (§3, Q18). A v2-only image on a v1 board just looks dead.
3. Linux needs udev rules on some distributions; Chromium from snap needs `snap connect chromium:raw-usb`.
4. Windows: an old mbed Composite Device driver blocks the automatic WebUSB driver.
5. The picker must be opened from a user gesture, and **cannot be automated** — which is why Q1a needs a human.

**Hardware**

6. DAPLink **0249 or newer** for WebUSB; surfaces as `firmware-update-required` or an empty picker. Current: 0253 (v1), 0255 (v2.00), 0257 (v2.2x). The board attached here is v2 on MicroPython 2.1.2 **[measured]**.
7. The board may appear as **"LPC1768"** in the picker the first time (Q12).
8. Charging-only USB cables are the commonest field failure: the board never appears at all.
9. `pauseOnHidden` defaults to **true** — switching tabs mid-flash pauses the connection and `pauseAfterFlash` disconnects instead of resetting [source]. Set it false.
10. Attach the `serialdata` listener **before** `flash()`, or CDC saturation never runs and startup output is lost (§3).
10a. Serial **writes cap at 255 bytes** (a single length byte in the vendor command); chunk them. 32 bytes with a 15 ms gap was lossless **[measured]**.
10b. **The first read after connecting can contain stale ring-buffer bytes** — the probe saw `"ba.od"` before its real output. Write, settle, then start believing the stream, exactly as `flash.py` calls `reset_input_buffer()` **[measured]**.
11. V1 DAPLink defaults to 9600 baud and changing the baud rate resets the target [source]; v2 is already 115200, so this is a no-op on our boards.
12. Partial flashing is best-effort — too many changed blocks, or a failure, falls back to a full flash.

**Deployment**

13. Pages serves at `https://<user>.github.io/radio-treasure-hunt/`, so every asset path must be relative (Q13).
14. A shallow checkout breaks the device-code stamp; `fetch-depth: 0`.
15. Pages cannot set custom headers. Nothing here needs any, but cache-bust by putting the stamp in asset filenames.
16. A service worker keyed on anything but the build stamp serves a stale site indefinitely.

## 11. Staging

Each step verified on hardware before the next. Flashing is the part that must work; the rest is additive.

1. `build_site.py`, manifest, group templating, checksums, `test_site.py`. Tests only, no UI.
2. ~~Settle Q1a before building anything on serial.~~ **Done 2026-09-06** — serial, raw REPL and checksum-on-device all work (§8). Identify can be built with confidence; only its repeat-reliability is still unmeasured.
3. Minimal page: connect, show the DAPLink unique ID and current firmware, **three-way board check (V1 / V2 / unrecognised)**, confirm-before-overwrite, flash fox and hound, progress, `.hex` fallback. Answers Q5, Q6, Q7.
4. Workflow, Pages deploy, stamps. Answers Q13.
5. Boot check. 6. Identify — answers Q2a. 7. Radio monitor — answers Q8, Q9, Q17.
8. Guidance, service worker, offline.
9. Write the measured results into `AGENTS.md` with dates and firmware versions, and archive this file.

## 12. Verification

1. `make check` — the existing suite plus `test_site.py`.
2. `make site && make site-serve`, then `http://localhost:8000/`. WebUSB works on `localhost` without HTTPS.
3. On hardware, recording results with the date and firmware version as AGENTS.md §9 requires: flash a hound and confirm the boot check and bar graph; flash a fox and confirm the display stays dark; monitor hears all three zones; identify reports the right role, group and code match, and the board resumes the game; flash both boards to a group other than 16 and confirm they hear each other, then move one and confirm the hound goes silent; confirm a `make flash-hound` board still identifies correctly; then run `make devices` and `make integration` on a board the browser has just talked to (Q17).
4. Offline: load the page, disconnect the network, flash a board.
5. Push; confirm the workflow deploys and the footer stamps match `git log`.
