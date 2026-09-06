"""Tests for the web flasher's build step.

Pure Python: no board, no browser, no network. Anything needing hardware is on
the integration checklist in WEB_FLASHER_PLAN.md section 9.

The interesting assertions here are the ones pinned to hardware. The digests in
test_device_digest_matches_the_board came off a real micro:bit on 2026-09-06,
read back over the raw REPL, so they tie the host's arithmetic to what the
device actually computes. Getting that wrong would make every board report as
"running something else".
"""
import ast
import hashlib
import re
import json
import os

import pytest

import build_site
from build_site import (
    DEVICE_FILES,
    FILESYSTEM_BYTES,
    GROUP_AVOID,
    GROUP_MAX,
    GROUP_MIN,
    GROUP_PLACEHOLDER,
    MICROPYTHON_BYTES,
    MICROPYTHON_HEX,
    MICROPYTHON_SHA256,
    MONITOR_RX,
    MONITOR_START,
    build_manifest,
    device_code_version,
    device_digest,
    device_sources,
    radio_config_template,
    render_radio_config,
)
from flash import BUNDLED_MICROPYTHON, LATEST_MICROPYTHON, ROLES
from radio_config import RADIO_GROUP


# --- the radio group -------------------------------------------------------

def test_rendering_the_repo_group_reproduces_the_file():
    """The anti-drift test. The browser writes radio_config.py by substituting
    one placeholder, so substituting the group the repo already uses must give
    back the repo's own file, byte for byte. If this fails, the device is being
    sent something other than the code under test."""
    assert render_radio_config(RADIO_GROUP).encode("utf-8") == open("radio_config.py", "rb").read()


def test_template_has_exactly_one_placeholder():
    template = radio_config_template()
    assert template.count(GROUP_PLACEHOLDER) == 1
    assert "RADIO_GROUP = " + GROUP_PLACEHOLDER in template


def test_template_keeps_the_warning_prose():
    """The docstring explaining why 0 and 42 are bad travels to the device. It
    is the only place that reasoning is written down for someone reading the
    board's filesystem."""
    template = radio_config_template()
    assert "0 is the MicroPython default" in template
    assert "42" in template


@pytest.mark.parametrize("group", [1, 16, 23, 99, 255])
def test_rendered_config_is_valid_python_defining_the_group(group):
    source = render_radio_config(group)
    tree = ast.parse(source)
    namespace = {}
    exec(compile(tree, "radio_config.py", "exec"), namespace)  # noqa: S102
    assert namespace["RADIO_GROUP"] == group


@pytest.mark.parametrize("group", list(GROUP_AVOID))
def test_collision_prone_groups_are_refused(group):
    with pytest.raises(ValueError):
        render_radio_config(group)


@pytest.mark.parametrize("group", [-1, 0, 256, 1000])
def test_out_of_range_groups_are_refused(group):
    with pytest.raises(ValueError):
        render_radio_config(group)


@pytest.mark.parametrize("group", ["16", 16.0, None, True])
def test_non_integer_groups_are_refused(group):
    """True is an int in Python and would render 'RADIO_GROUP = True'."""
    with pytest.raises(ValueError):
        render_radio_config(group)


@pytest.mark.parametrize("group", [1, 16, 255])
def test_rendered_config_passes_the_device_code_rules(group):
    """Whatever the browser writes has to satisfy the same checks every other
    device file does: no literal radio group passed to radio.config, and no
    f-strings, which MicroPython on the micro:bit does not have."""
    tree = ast.parse(render_radio_config(group))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.JoinedStr), "f-string in generated device code"
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "config":
            for keyword in node.keywords:
                assert keyword.arg != "group", "generated file passes a literal group"


# --- the device digest, pinned to hardware ---------------------------------

# Read off a micro:bit v2 (serial 9906360200052820726e40a4da840fa7…, MicroPython
# 2.1.2) on 2026-09-06 via the raw REPL, from a board flashed by `make
# flash-hound`. The host function must agree with the device's arithmetic or
# identify is worthless.
BOARD_DIGESTS = {
    "radio_config.py": 3318680731,
    "hound_logic.py": 2215835840,
    "hound.py": 82801265,          # on the board as main.py
    "fox.py": 2507183434,          # measured on the second board, as main.py
    "hound_integration.py": 1394167193,
}


@pytest.mark.parametrize("name,expected", sorted(BOARD_DIGESTS.items()))
def test_device_digest_matches_the_board(name, expected):
    assert device_digest(open(name, "rb").read()) == expected


def test_role_entry_points_are_distinguishable():
    """Identify names a role by matching main.py's digest. Two roles sharing a
    digest would make that ambiguous."""
    entries = {role: [src for src, target in files if target == "main.py"][0]
               for role, files in ROLES.items()}
    digests = {role: device_digest(open(src, "rb").read()) for role, src in entries.items()}
    assert len(set(digests.values())) == len(digests), digests


def test_digest_is_stable_for_empty_and_short_input():
    assert device_digest(b"") == 0
    assert device_digest(b"A") == 65
    assert device_digest(b"AB") == 65 * 31 + 66


# --- the device code version ------------------------------------------------

def test_device_code_version_ignores_the_radio_group():
    """The group is configuration, not code. A board is not running a different
    version because someone picked group 23, so the version hashes the template
    rather than a rendered file."""
    sources = device_sources()
    assert GROUP_PLACEHOLDER in sources["radio_config.py"].decode("utf-8"), (
        "the served config must be the template, or the version would move "
        "every time someone picked a different group")
    assert device_code_version(sources) == device_code_version()

    # The point of hashing the template: versions computed over *rendered*
    # configs would differ from each other, and the code has not changed.
    rendered = set()
    for group in (1, 23, 255):
        variant = dict(sources)
        variant["radio_config.py"] = render_radio_config(group).encode("utf-8")
        rendered.add(device_code_version(variant))
    assert len(rendered) == 3
    assert device_code_version() not in rendered


def test_device_code_version_changes_when_device_code_changes():
    sources = device_sources()
    sources["hound_logic.py"] += b"\n# nudge\n"
    assert device_code_version(sources) != device_code_version()


def test_device_code_version_is_short_and_hex():
    version = device_code_version()
    assert len(version) == 8
    int(version, 16)


# --- the manifest -----------------------------------------------------------

def test_manifest_covers_every_role_and_file():
    """The guard against the site shipping a stale or missing device file. The
    roles come from flash.ROLES and are never listed again -- AGENTS.md section
    9 says a device file must be in three places, and deriving this keeps it at
    three rather than four."""
    manifest = build_manifest()
    assert set(manifest["roles"]) == set(ROLES)
    for role, files in ROLES.items():
        assert [tuple(pair) for pair in manifest["roles"][role]["files"]] == list(files)


def test_manifest_names_each_role_entry_point():
    manifest = build_manifest()
    for role, files in ROLES.items():
        expected = [src for src, target in files if target == "main.py"][0]
        assert manifest["roles"][role]["entry"] == expected


def test_every_served_file_matches_the_repo():
    """radio_config.py is served as the template, since the group is chosen at
    flash time; everything else is served verbatim."""
    sources = device_sources()
    assert set(sources) == set(DEVICE_FILES)
    for name, data in sources.items():
        if name == "radio_config.py":
            assert data == radio_config_template().encode("utf-8")
        else:
            assert data == open(name, "rb").read()


def test_manifest_is_json_serialisable():
    json.dumps(build_manifest())


def test_manifest_group_bounds_are_sane():
    group = build_manifest()["group"]
    assert group["default"] == RADIO_GROUP
    assert group["default"] not in group["avoid"]
    assert group["min"] <= group["default"] <= group["max"]
    assert group["placeholder"] == GROUP_PLACEHOLDER


def test_manifest_carries_both_stamps():
    manifest = build_manifest()
    for key in ("site", "device"):
        assert len(manifest[key]["commit"]) == 40
        assert manifest[key]["short"]
        assert manifest[key]["date"]
    assert manifest["device"]["version"] == device_code_version()


# --- the monitor ------------------------------------------------------------

def test_monitor_markers_still_exist_in_the_device_file():
    """The browser's monitor parses these. They are string literals in
    hound_integration.py, so renaming one there would silently break the page --
    this is what stops that being silent."""
    source = open("hound_integration.py").read()
    assert MONITOR_START in source
    assert MONITOR_RX in source


def test_monitor_constants_come_from_the_cli_checker():
    """integration_check.py already decides what counts as a pass. The page must
    apply the same rule, not a second copy of it."""
    import integration_check

    monitor = build_manifest()["monitor"]
    assert tuple(monitor["zones"]) == tuple(integration_check.ZONES)
    assert monitor["listen_seconds"] == integration_check.LISTEN_SECONDS


# --- the bundled firmware ---------------------------------------------------

def test_bundled_micropython_is_the_image_we_claim():
    """A re-cut release asset or a truncated download would otherwise reach
    every board the organiser touches."""
    path = os.path.join("web", "micropython", MICROPYTHON_HEX)
    assert os.path.exists(path), "run: see build_site.check_micropython for the URL"
    data = open(path, "rb").read()
    assert len(data) == MICROPYTHON_BYTES
    assert hashlib.sha256(data).hexdigest() == MICROPYTHON_SHA256


def test_bundled_and_latest_micropython_are_separate_constants():
    """Regression for AGENTS.md section 6: a constant may not carry a second
    meaning. LATEST_MICROPYTHON means 'the newest release that exists' and only
    drives a hint; BUNDLED_MICROPYTHON is what lands on a board. They agree
    today and must be free to diverge."""
    source = open("flash.py").read()
    assert "BUNDLED_MICROPYTHON = " in source
    assert "LATEST_MICROPYTHON = " in source
    assert BUNDLED_MICROPYTHON in MICROPYTHON_HEX


def test_bundled_version_matches_the_hex_filename():
    assert MICROPYTHON_HEX == "micropython-microbit-v%s.hex" % BUNDLED_MICROPYTHON


def test_latest_is_not_older_than_bundled():
    """Bundling something newer than the newest known release means one of the
    two constants was updated and the other forgotten."""
    from flash import parse_version

    assert parse_version(BUNDLED_MICROPYTHON) <= parse_version(LATEST_MICROPYTHON)


# --- filesystem budget ------------------------------------------------------

@pytest.mark.parametrize("role", sorted(ROLES))
def test_each_role_fits_the_device_filesystem(role):
    """MicroPython's filesystem on a v2 is 20480 bytes, measured with
    microbit-fs against the 2.1.2 image. The hound uses about half. This fails
    before a build does, with a number rather than a hex-builder exception."""
    total = sum(len(device_sources()[src]) for src, _ in ROLES[role])
    assert total < FILESYSTEM_BYTES, "%s needs %d of %d bytes" % (role, total, FILESYSTEM_BYTES)


def test_the_hound_leaves_room_to_grow():
    """Measured at 9856 bytes on hardware. If this trips, the budget is real and
    someone needs to look at it rather than nudge the number."""
    total = sum(len(device_sources()[src]) for src, _ in ROLES["hound"])
    assert total < FILESYSTEM_BYTES * 0.75


# --- device file rules the site must not break ------------------------------

def test_device_files_are_derived_not_listed():
    """DEVICE_FILES is computed from flash.ROLES. If someone re-lists them, this
    catches the copy drifting."""
    from_roles = sorted({src for files in ROLES.values() for src, _ in files})
    assert DEVICE_FILES == from_roles


def test_build_site_is_inert_at_import():
    """Like calibrate.py and integration_check.py, this module must define
    constants at import and do work only in main(), so tests can import it."""
    tree = ast.parse(open("build_site.py").read())
    for node in tree.body:
        assert isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign,
                                 ast.AnnAssign, ast.FunctionDef, ast.ClassDef,
                                 ast.Expr, ast.If)), ast.dump(node)[:80]


# --- the JavaScript half ----------------------------------------------------
#
# device.js reimplements two things Python also implements: the file digest and
# the radio-group substitution. AGENTS.md section 9 is blunt that two copies of
# a fact will drift, and these copies are in different languages, so neither
# compileall nor the suite above would notice. Both are executed under node here
# and compared against the Python originals.
#
# The digest actually exists three times -- here, in build_site.py, and as the
# MicroPython snippet in serial.js that runs on the board. The third copy is
# pinned by BOARD_DIGESTS above, which came off real hardware.

import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DEVICE_JS = os.path.join(HERE, "web", "src", "device.js")
SERIAL_JS = os.path.join(HERE, "web", "src", "serial.js")


def run_node(body, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; the JavaScript half cannot be checked")
    script = tmp_path / "check.mjs"
    script.write_text(
        "const device = await import(%s);\n"
        "const serial = await import(%s);\n"
        "%s\n" % (json.dumps("file://" + DEVICE_JS), json.dumps("file://" + SERIAL_JS), body))
    done = subprocess.run([node, str(script)], capture_output=True, cwd=HERE)
    if done.returncode != 0:
        pytest.fail(done.stderr.decode("utf-8", "replace"))
    return json.loads(done.stdout.decode("utf-8"))


def test_javascript_digest_matches_python(tmp_path):
    """The browser decides whether a board is running this code by comparing
    digests. If its arithmetic differs from Python's by so much as a truncation,
    every board reports as 'running something else'."""
    got = run_node(
        "const fs = await import('node:fs');\n"
        "const out = {};\n"
        "for (const name of %s) out[name] = device.deviceDigest(fs.readFileSync(name));\n"
        "console.log(JSON.stringify(out));" % json.dumps(DEVICE_FILES),
        tmp_path)
    expected = {name: device_digest(open(name, "rb").read()) for name in DEVICE_FILES}
    assert got == expected


def test_javascript_digest_matches_the_board(tmp_path):
    """And therefore also matches what MicroPython computed on real hardware."""
    got = run_node(
        "const fs = await import('node:fs');\n"
        "const out = {};\n"
        "for (const name of %s) out[name] = device.deviceDigest(fs.readFileSync(name));\n"
        "console.log(JSON.stringify(out));" % json.dumps(sorted(BOARD_DIGESTS)),
        tmp_path)
    assert got == BOARD_DIGESTS


def test_javascript_digest_handles_high_bytes(tmp_path):
    """JavaScript numbers are doubles and >>> is a 32-bit operation; a long file
    of high bytes is where a mismatch with Python's masking would show."""
    payload = bytes(range(256)) * 40
    (tmp_path / "blob.bin").write_bytes(payload)
    got = run_node(
        "const fs = await import('node:fs');\n"
        "console.log(JSON.stringify(device.deviceDigest(fs.readFileSync(%s))));"
        % json.dumps(str(tmp_path / "blob.bin")),
        tmp_path)
    assert got == device_digest(payload)


@pytest.mark.parametrize("group", [1, 16, 23, 255])
def test_javascript_render_radio_config_matches_python(group, tmp_path):
    """The file the browser writes to the board must be the file Python's tests
    checked. A mismatch here puts the fox and the hound on different groups, and
    the only symptom of that is silence."""
    # The template handed to node is the one build_site.py serves, so this
    # tests the bytes that actually ship rather than a reconstruction.
    got = run_node(
        "console.log(JSON.stringify(device.renderRadioConfig(%s, %d, %s)));"
        % (json.dumps(radio_config_template()), group, json.dumps(build_manifest()["group"])),
        tmp_path)
    assert got == render_radio_config(group)


@pytest.mark.parametrize("group", [0, 42, 256, -1])
def test_javascript_refuses_the_same_groups_python_does(group, tmp_path):
    got = run_node(
        "let err = null;\n"
        "try { device.renderRadioConfig('RADIO_GROUP = ' + %s, %d, %s); }\n"
        "catch (e) { err = e.message; }\n"
        "console.log(JSON.stringify(err));"
        % (json.dumps(GROUP_PLACEHOLDER), group, json.dumps(build_manifest()["group"])),
        tmp_path)
    assert got is not None, "JavaScript accepted group %d that Python refuses" % group
    with pytest.raises(ValueError):
        render_radio_config(group)


def test_javascript_group_readback_round_trips(tmp_path):
    """Identify reads the group back off the board out of radio_config.py."""
    got = run_node(
        "const out = {};\n"
        "for (const g of [1, 16, 23, 255]) {\n"
        "  const text = 'RADIO_GROUP = ' + g + '\\n';\n"
        "  out[g] = device.groupFromConfig(text);\n"
        "}\n"
        "console.log(JSON.stringify(out));",
        tmp_path)
    assert got == {"1": 1, "16": 16, "23": 23, "255": 255}


def test_javascript_repl_markers_match_flash_py(tmp_path):
    """The boot check treats a REPL banner as failure. flash.py decided which
    strings mean that; the browser must not invent its own list."""
    from flash import REPL_MARKERS

    got = run_node("console.log(JSON.stringify(device.REPL_MARKERS));", tmp_path)
    assert tuple(got) == tuple(REPL_MARKERS)


def test_javascript_boot_verdict_agrees_with_flash_py(tmp_path):
    """Same inputs, same verdicts as flash.py:boot_check."""
    from flash import ERROR_RE, REPL_MARKERS

    cases = [
        "",                                        # healthy: prints nothing
        "HOUND_START\r\n",                         # healthy and announces itself
        'Traceback (most recent call last):\r\n',  # raised
        "IndentationError: unexpected indent\r\n",  # raised, no traceback header
        '>>> ',                                    # fell through to the REPL
        'Type "help()" for more information.',     # ditto
    ]
    got = run_node(
        "console.log(JSON.stringify(%s.map((t) => device.bootVerdict(t, null).ok)));"
        % json.dumps(cases),
        tmp_path)
    expected = [
        not ("Traceback" in c or ERROR_RE.search(c)
             or any(m in c for m in REPL_MARKERS))
        for c in cases
    ]
    assert got == expected


def test_device_snippet_uses_the_same_digest_arithmetic():
    """The third copy: MicroPython running on the board. It is a string literal
    in serial.js, so neither compileall nor node ever sees it -- the same trap
    calibrate.LOGGER_SRC has, and the same reason there is a test for it."""
    source = open(SERIAL_JS).read()
    assert "(_h * 31 + _c) & 0xFFFFFFFF" in source, (
        "the on-device digest no longer matches build_site.device_digest")
    assert "SUM" in source and "UNAME" in source


def test_device_snippet_is_valid_python():
    """It is device code held in a string literal. A typo would flash cleanly
    and fail in a field, exactly as AGENTS.md says of calibrate.LOGGER_SRC."""
    source = open(SERIAL_JS).read()
    start = source.index("export const SURVEY_SNIPPET = [")
    end = source.index("].join(", start)
    lines = []
    for raw in source[start:end].split("\n")[1:]:
        raw = raw.strip().rstrip(",")
        if raw.startswith('"') and raw.endswith('"'):
            lines.append(json.loads(raw))
    assert lines, "could not extract the snippet"
    ast.parse("\n".join(lines))


def test_device_snippet_avoids_fstrings():
    """MicroPython on the micro:bit is not a full CPython."""
    source = open(SERIAL_JS).read()
    start = source.index("export const SURVEY_SNIPPET = [")
    end = source.index("].join(", start)
    lines = [json.loads(r.strip().rstrip(","))
             for r in source[start:end].split("\n")[1:]
             if r.strip().rstrip(",").startswith('"')]
    tree = ast.parse("\n".join(lines))
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]


def test_stale_device_errors_are_recognised(tmp_path):
    """A board that has been unplugged is still 'known' to microbit-connection,
    so reconnecting fails inside a USB transfer rather than falling through to
    the picker. Getting this classification wrong strands the page on a board
    that is not there -- the exact symptom reported on 2026-09-06.

    The first string is the one a real unplug produced."""
    stale = [
        "Failed to execute 'transferOut' on 'USBDevice': The device was disconnected.",
        "Failed to execute 'transferIn' on 'USBDevice': The device was disconnected.",
        "No device opened",
    ]
    fresh = [
        "No device selected.",
        "Could not recognise the Board ID 9907",
        "Unable to claim interface.",
    ]
    got = run_node(
        "const out = {stale: [], fresh: []};\n"
        "for (const m of %s) out.stale.push(device.isStaleDevice(new Error(m)));\n"
        "for (const m of %s) out.fresh.push(device.isStaleDevice(new Error(m)));\n"
        "out.byCode = ['device-disconnected', 'connection-error', 'no-device-selected']\n"
        "  .map((code) => device.isStaleDevice(Object.assign(new Error('x'), {code})));\n"
        "out.nothing = device.isStaleDevice(null);\n"
        "console.log(JSON.stringify(out));" % (json.dumps(stale), json.dumps(fresh)),
        tmp_path)
    assert got["stale"] == [True] * len(stale)
    assert got["fresh"] == [False] * len(fresh)
    assert got["byCode"] == [True, True, False]
    assert got["nothing"] is False


# --- the monitor holds zones, it does not latch them ------------------------

def test_monitor_timing_comes_from_the_hound():
    """Regression: the monitor invented its own idea of how long a zone lasts.
    AGENTS.md section 6 already settled that question for the game -- a zone is
    held for a window, not latched -- and the window was tuned against real
    packet loss. Sharing the constant means a recalibration moves both."""
    import hound_logic

    monitor = build_manifest()["monitor"]
    assert monitor["zone_hold_ms"] == hound_logic.ZONE_HOLD_MS
    assert monitor["signal_timeout_ms"] == hound_logic.SIGNAL_TIMEOUT_MS


def test_monitor_drops_a_zone_once_it_stops_arriving(tmp_path):
    """The reported bug: a fox heard close up still showed all three zones after
    it moved away, because zones accumulated and nothing ever expired them."""
    got = run_node(
        "const cfg = {zones: ['Z1','Z2','Z3'], holdMs: 1000, timeoutMs: 1000};\n"
        "// Everything heard at t=0, then only Z1 keeps arriving.\n"
        "const state = {lastSeen: {Z1: 5000, Z2: 0, Z3: 0}, everHeard: ['Z1','Z2','Z3'],\n"
        "               lastPacketAt: 5000, lastRssi: -80, count: 42};\n"
        "const out = {};\n"
        "out.atClose = device.monitorState(\n"
        "  {...state, lastSeen: {Z1: 0, Z2: 0, Z3: 0}, lastPacketAt: 0}, 0, cfg).current;\n"
        "out.afterMoving = device.monitorState(state, 5000, cfg).current;\n"
        "out.everStillKnown = device.monitorState(state, 5000, cfg).ever;\n"
        "out.stillPasses = device.monitorState(state, 5000, cfg).ok;\n"
        "console.log(JSON.stringify(out));",
        tmp_path)
    assert got["atClose"] == ["Z1", "Z2", "Z3"], "close up, all three are audible"
    assert got["afterMoving"] == ["Z1"], "the weak beacons must drop out once they stop arriving"
    # But the fact that they were once heard is a different fact, and is kept:
    # it is what integration_check.py's pass rule is about.
    assert got["everStillKnown"] == ["Z1", "Z2", "Z3"]
    assert got["stillPasses"] is True


def test_monitor_goes_quiet_when_the_signal_stops(tmp_path):
    """Losing the fox entirely must clear the reading rather than freeze on the
    last one. The display is driven by a clock for this reason -- no packet ever
    arrives to trigger the update."""
    got = run_node(
        "const cfg = {zones: ['Z1','Z2','Z3'], holdMs: 1000, timeoutMs: 1000};\n"
        "const state = {lastSeen: {Z1: 0}, everHeard: ['Z1'], lastPacketAt: 0,\n"
        "               lastRssi: -70, count: 9};\n"
        "const out = {};\n"
        "for (const t of [0, 500, 1500, 60000]) {\n"
        "  const s = device.monitorState(state, t, cfg);\n"
        "  out[t] = {live: s.live, rssi: s.rssi, current: s.current};\n"
        "}\n"
        "console.log(JSON.stringify(out));",
        tmp_path)
    assert got["0"] == {"live": True, "rssi": -70, "current": ["Z1"]}
    assert got["500"] == {"live": True, "rssi": -70, "current": ["Z1"]}
    assert got["1500"]["live"] is False
    assert got["1500"]["rssi"] is None, "a stale reading is worse than none"
    assert got["1500"]["current"] == []
    assert got["60000"]["live"] is False


def test_monitor_reports_nothing_before_the_first_packet(tmp_path):
    got = run_node(
        "const cfg = {zones: ['Z1','Z2','Z3'], holdMs: 1000, timeoutMs: 1000};\n"
        "const s = device.monitorState(\n"
        "  {lastSeen: {}, everHeard: [], lastPacketAt: null, lastRssi: null, count: 0}, 0, cfg);\n"
        "console.log(JSON.stringify({live: s.live, current: s.current, ok: s.ok, missing: s.missing}));",
        tmp_path)
    assert got == {"live": False, "current": [], "ok": False, "missing": ["Z1", "Z2", "Z3"]}


def test_monitor_zone_order_follows_the_manifest(tmp_path):
    """The display reads the last entry as 'closest', so the order must be the
    zones' own order rather than whatever order packets happened to arrive in."""
    got = run_node(
        "const cfg = {zones: ['Z1','Z2','Z3'], holdMs: 1000, timeoutMs: 1000};\n"
        "const s = device.monitorState(\n"
        "  {lastSeen: {Z3: 0, Z1: 0, Z2: 0}, everHeard: ['Z3','Z1','Z2'],\n"
        "   lastPacketAt: 0, lastRssi: -50, count: 3}, 0, cfg);\n"
        "console.log(JSON.stringify({current: s.current, ever: s.ever}));",
        tmp_path)
    assert got["current"] == ["Z1", "Z2", "Z3"]
    assert got["ever"] == ["Z1", "Z2", "Z3"]


# --- the teaching materials -------------------------------------------------
#
# The lesson plan and worksheet quote real numbers -- the bar-graph scale, the
# attenuator step, the outdoor calibration. Retyping those into HTML would
# guarantee they were wrong after the next field trip, so they are substituted
# at build time and checked here.

TEACHING = ("lesson-plan.html", "worksheet.html", "hunt-card.html")


def render(name):
    from build_site import apply, substitutions
    return apply(open(os.path.join("web", name)).read(), substitutions(build_manifest()))


@pytest.mark.parametrize("name", TEACHING)
def test_teaching_pages_have_no_unsubstituted_placeholders(name):
    """A worksheet that goes to a class reading __MIN_RSSI__ is worse than no
    worksheet."""
    leftover = re.findall(r"__[A-Z_]+__", render(name))
    assert not leftover, sorted(set(leftover))


def test_index_is_well_formed():
    from build_site import apply, substitutions

    page = apply(open(os.path.join("web", "index.html")).read(),
                 substitutions(build_manifest())).replace("__SCRIPT__", "app.js")
    problems, unclosed = check_html_balance(page)
    assert not problems, problems
    assert not unclosed, unclosed


def test_index_introduces_the_game():
    """The page is the entry point for someone who has never heard of a fox hunt
    or held a micro:bit, so the introduction is load-bearing rather than
    decorative. These are the things they cannot proceed without knowing."""
    page = open(os.path.join("web", "index.html")).read()
    intro = page[page.index('id="intro"'):page.index('id="setup"')]
    for essential in (
        "hide-and-seek",          # what the game is
        "amateur radio direction finding",  # what it is really called
        "Fox", "Hound",           # the two roles
        "V2",                     # the hardware requirement that bites
        "charge-only", "Charge-only",  # the commonest practical failure
        "Button A",               # why the attenuator exists
    ):
        assert essential.lower() in intro.lower(), essential
    assert 'href="lesson-plan.html"' in intro and 'href="worksheet.html"' in intro


@pytest.mark.parametrize("name", TEACHING)
def test_teaching_pages_are_well_formed(name):
    """They are printed and handed to children; an unclosed tag is not
    acceptable."""
    problems, unclosed = check_html_balance(render(name))
    assert not problems, problems
    assert not unclosed, unclosed


def check_html_balance(markup):
    """Tag balance, via an HTML parser rather than an XML one: these pages are
    HTML5, with a bare doctype and named entities that XML rejects."""
    from html.parser import HTMLParser

    void = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    class Balanced(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []
            self.problems = []

        def handle_starttag(self, tag, attrs):
            if tag not in void:
                self.stack.append((tag, self.getpos()[0]))

        def handle_endtag(self, tag):
            if tag in void:
                return
            if not self.stack:
                self.problems.append("</%s> with nothing open" % tag)
            elif self.stack[-1][0] != tag:
                self.problems.append(
                    "</%s> at line %d closes <%s> opened at line %d"
                    % (tag, self.getpos()[0], self.stack[-1][0], self.stack[-1][1]))
                self.stack.pop()
            else:
                self.stack.pop()

    parser = Balanced()
    parser.feed(markup)
    return parser.problems, ["<%s> at line %d never closed" % t for t in parser.stack]


def test_worksheet_quotes_the_hounds_real_scale():
    from build_site import hound_scale

    scale = hound_scale()
    page = render("worksheet.html")
    assert ">%d</strong> bars" % scale["bars"] in page or "<strong>%d</strong>" % scale["bars"] in page
    assert "press A up to __MAX__".replace("__MAX__", str(scale["max_presses"])) in page


def test_lesson_plan_quotes_the_derived_attenuator_step():
    """ATTEN_STEP is derived so that one press moves the display by exactly one
    bar. The lesson plan explains it that way, so the two must agree."""
    from build_site import hound_scale

    scale = hound_scale()
    assert scale["atten_step"] == scale["db_per_bar"], (
        "one press of A must be exactly one bar, or the lesson plan is wrong")
    page = render("lesson-plan.html")
    assert "subtracts %d&nbsp;dB" % scale["atten_step"] in page
    assert "about %d&nbsp;dB" % scale["db_per_bar"] in page


def test_calibration_table_agrees_with_the_hounds_scale():
    """MAX_RSSI is the strongest reading in the field calibration. MIN_RSSI is
    deliberately *not* the weakest: the 15 m reading is a ground-reflection null
    and only 21% of packets arrive there, so the hound uses the 20 m figure
    instead (see hound_logic.py). Both facts are asserted, because the worksheet
    asks pupils to explain that very anomaly."""
    from build_site import CALIBRATION, hound_scale

    scale = hound_scale()
    readings = [rssi for _, rssi, _, _, _ in CALIBRATION]
    assert max(readings) == scale["max_rssi"]
    assert scale["min_rssi"] in readings
    assert min(readings) < scale["min_rssi"], "the null should sit below the floor"


def test_worksheet_challenge_data_is_the_measured_data():
    from build_site import CALIBRATION, signed

    page = render("worksheet.html")
    for distance, rssi, _, _, _ in CALIBRATION:
        assert "<td>%d m</td><td>%s dBm</td>" % (distance, signed(rssi)) in page


def test_minus_signs_are_typographic_not_hyphens():
    """The graph axes are labelled with U+2212; the table must match."""
    page = render("worksheet.html")
    assert "&minus;52 dBm" in page
    assert "-52 dBm" not in page


@pytest.mark.parametrize("statement", [
    "recognise that light appears to travel in straight lines",
    "recognise that sounds get fainter as the distance from the sound source increases",
    "notice that light is reflected from surfaces",
    "interpret and construct pie charts and line graphs and use these to solve problems",
])
def test_lesson_plan_quotes_the_curriculum_verbatim(statement):
    """These are quoted from the 2014 programmes of study and were checked
    against the published text. A paraphrase in a curriculum-mapping table is
    worse than useless to a teacher completing planning paperwork."""
    page = render("lesson-plan.html").replace("&ldquo;", "").replace("&rdquo;", "")
    assert statement in page


def test_teaching_pages_link_to_each_other_and_the_flasher():
    for name in TEACHING:
        page = render(name)
        assert 'href="index.html"' in page
        others = [n for n in TEACHING if n != name]
        for other in others:
            assert 'href="%s"' % other in page
    assert 'href="lesson-plan.html"' in open("web/index.html").read()
    assert 'href="worksheet.html"' in open("web/index.html").read()


@pytest.mark.parametrize("name", TEACHING)
def test_teaching_pages_are_printable(name):
    """Teachers print these. The stylesheet must be attached and carry rules for
    paper, or the worksheet arrives with navigation on it and tables split
    across pages."""
    assert 'href="teaching.css"' in render(name)
    css = open(os.path.join("web", "teaching.css")).read()
    assert "@media print" in css
    assert "@page" in css
    assert "break-inside: avoid" in css


def test_worksheet_carries_the_player_guide():
    """PLAYER_GUIDE.md was folded into the worksheet and deleted. A pupil handed
    only this sheet must still know how to play and how to stay safe, so the
    parts that used to live in that file are pinned here."""
    page = render("worksheet.html")
    for essential in ("Slow beep", "Medium beep", "Fast alarm",
                      "button A", "button B",
                      "Walk, do not run", "never swing it by the battery wire",
                      "Stay inside the boundary"):
        assert essential in page, essential
    assert not os.path.exists("PLAYER_GUIDE.md"), (
        "the worksheet subsumed it; two copies would drift")


def test_lesson_plan_asks_for_feedback():
    page = render("lesson-plan.html")
    assert "s.murdoch@ucl.ac.uk" in page
    assert "mailto:s.murdoch@ucl.ac.uk" in page


@pytest.mark.parametrize("page,terms", [
    ("worksheet.html", ("omnidirectional", "behind you", "listens in every direction")),
    ("lesson-plan.html", ("omnidirectional", "Yagi", "cannot indicate a bearing")),
])
def test_pages_explain_why_there_is_no_direction(page, terms):
    """The single most counter-intuitive thing about the game: the receiver
    reports strength and never bearing, so the only way to get a direction is to
    block the signal with your own body. Pupils who miss this wander. It is
    explained at three different depths across the site, and each needs to keep
    saying it."""
    rendered = render(page)
    for term in terms:
        assert term in rendered, "%s: %s" % (page, term)


def test_index_explains_the_aerial_too():
    page = open(os.path.join("web", "index.html")).read()
    intro = page[page.index('id="intro"'):page.index('id="setup"')]
    assert "omnidirectional" in intro
    assert "Directional aerials do exist" in intro


# --- the short-form hunt card ----------------------------------------------

def test_hunt_card_is_playable_on_its_own():
    """It is handed out for a 20-minute game with a three-minute briefing, so a
    team holding only this card must be able to play and stay safe without a
    teacher reading anything else out."""
    page = render("hunt-card.html")
    for essential in ("Slow beep", "Medium beep", "Fast alarm",
                      "button A", "turn slowly all the way round",
                      "Walk, do not run", "boundary", "battery wire"):
        assert essential in page, essential


def test_hunt_card_carries_the_learning_as_tactics():
    """The point of this sheet is that the science is implicit. The three tricks
    are the three learning objectives in disguise, so each must still be there
    even though none is labelled as science."""
    page = render("hunt-card.html")
    assert "Walk and watch" in page and "fades the further" in page      # distance
    assert "Turn on the spot" in page and "does not go through people" in page  # blocking
    assert "Sunglasses" in page and "only changes the Hound" in page     # saturation


def test_hunt_card_asks_the_reflection_questions():
    """Learning is implicit during play, but it is surfaced at the end -- that is
    what makes it a lesson rather than a game."""
    page = render("hunt-card.html")
    assert "Quick think" in page
    assert "which way" in page
    assert "what did pressing A actually change" in page


def test_hunt_card_stays_short():
    """One side of A4 is the whole design constraint. This will not catch a
    layout that overflows, but it does catch someone quietly turning it into a
    second full worksheet."""
    page = render("hunt-card.html")
    body = page[page.index("<body"):]
    assert body.count("<h2") <= 6, "too many sections for one side of A4"
    assert len(re.findall(r'class="write"', body)) <= 14, "too much writing for a 20-minute game"


def test_lesson_plan_covers_the_short_version():
    page = render("lesson-plan.html")
    assert "If you only have 20 minutes" in page
    assert 'href="hunt-card.html"' in page


def test_both_pupil_sheets_are_offered_on_the_flasher():
    page = open(os.path.join("web", "index.html")).read()
    teaching = page[page.index('id="teaching"'):page.index('id="guide"')]
    assert 'href="worksheet.html"' in teaching
    assert 'href="hunt-card.html"' in teaching
    assert "20-minute" in teaching


def test_the_hound_is_a_dog():
    """It was a horse. Numeric character references are unreadable in source, so
    nothing catches this by eye -- U+1F434 HORSE FACE and U+1F436 DOG FACE are
    two apart."""
    import unicodedata

    page = open(os.path.join("web", "index.html")).read()
    used = {int(m) for m in re.findall(r"&#(1[0-9]{5});", page)}
    names = {unicodedata.name(chr(cp)) for cp in used}
    assert "DOG FACE" in names, sorted(names)
    assert "FOX FACE" in names, sorted(names)
    assert not any("HORSE" in n for n in names), sorted(names)
