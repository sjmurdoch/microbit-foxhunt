"""Build the web flasher into site/. Host tool, not a test.

Normally driven by the Makefile (`make site`), which depends on `check` -- the
web flasher is a flashing target, so code that fails its tests must not reach a
board through it either.

Two things this file exists to prevent:

* **A second list of device files.** The roles, and the files in them, come from
  `flash.ROLES` and nowhere else. AGENTS.md section 9 says a device file that is
  not in `flash.ROLES`, `DEVICE_SRC` and `DEVICE_FILES` does not exist; deriving
  the manifest keeps that at three places rather than four.
* **A second copy of the radio-group substitution.** The browser has to write
  `radio_config.py` with the group the organiser picked, so the rule for doing
  that lives in exactly one place: this module emits `radio_config.py` with its
  group replaced by a placeholder, and the browser does a single literal
  `.replace()`. The same idiom as `calibrate.py`'s `__GROUP__`. A test asserts
  that substituting the repo's own group reproduces `radio_config.py` byte for
  byte, so the two cannot drift.

The page carries two versions and they move independently -- the flasher itself,
and the device code it writes. See archive/WEB_SETUP_PLAN.md section 2.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

from flash import BUNDLED_MICROPYTHON, ROLES

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
DEFAULT_OUT = os.path.join(HERE, "site")

# The MicroPython image the flasher installs. Pinned deliberately: this is the
# release the field calibration in AGENTS.md section 4 was measured on, and a
# firmware change invalidates those numbers if the radio stack moves. It is NOT
# flash.LATEST_MICROPYTHON, which means "the newest release that exists" and
# only drives a hint -- see the comment there.
MICROPYTHON_HEX = "micropython-microbit-v%s.hex" % BUNDLED_MICROPYTHON
MICROPYTHON_SHA256 = "66fae07b71777e9e3a6b5122a27930b24cc0be5002ab9a67e92494c54a1645ef"
MICROPYTHON_BYTES = 1239726

# MicroPython's filesystem on a v2 board, measured with microbit-fs against the
# 2.1.2 image. The hound's three files use 9856 of it. Carried into the manifest
# so the page can refuse an over-large payload with a real number rather than
# waiting for the hex builder to throw.
FILESYSTEM_BYTES = 20480

# Substituted into radio_config.py in place of the group. A literal token, not a
# regex, so the browser's replace() and this module's cannot disagree.
GROUP_PLACEHOLDER = "__GROUP__"

# 0 is the MicroPython default, so any board whose radio was switched on without
# configuring a group sits there; 42 is what most tutorials use. radio_config.py
# explains both. The device accepts 0-255.
GROUP_MIN, GROUP_MAX = 1, 255
GROUP_AVOID = (0, 42)

# What hound_integration.py prints. Defined here so the browser's monitor can
# parse it without the strings being retyped in JavaScript; test_site.py asserts
# both still appear in the device file, so renaming one fails the suite rather
# than silently breaking the monitor.
MONITOR_START = "HOUND_START"
MONITOR_RX = "HOUND_RX"

# Every source file that can end up on a board, taken from the roles rather than
# listed again.
DEVICE_FILES = sorted({src for files in ROLES.values() for src, _ in files})

# The outdoor field calibration from AGENTS.md section 4, measured 2026-09-06
# with calibrate.py: hound tethered to USB, fox carried out on a battery, 15 s
# per point, figures are the Z1 median. The teaching worksheet plots these, so
# they live here rather than being retyped into HTML -- and test_site.py checks
# them against the hound's own scale, which was derived from them.
#
# (distance m, Z1 dBm, Z1 packets, Z2 packets, Z3 packets), out of 75.
CALIBRATION = (
    (1, -52, 75, 75, 74),
    (3, -59, 75, 74, 74),
    (8, -80, 74, 19, 0),
    (15, -89, 16, 0, 0),
    (20, -87, 56, 0, 0),
)

# Document-shaped pages that accompany the flasher. Same substitutions as
# index.html, so every number a teacher reads comes from the code.
TEACHING_PAGES = ("lesson-plan.html", "worksheet.html", "hunt-card.html")

ROLE_LABELS = {
    "fox": "Treasure",
    "hound": "Hound",
    "integration": "Radio monitor",
}

# --- analytics --------------------------------------------------------------
#
# Off unless an endpoint is configured, and the default is no endpoint, so a
# fork and a local `make site` send nothing without anyone having to remember.
# See ANALYTICS_PLAN.md for the design and web/src/analytics.js for what the
# client will and will not send.
ANALYTICS_SECTION = ("tool", "foxhunt", "analytics")
ANALYTICS_ENV_ENDPOINT = "FOXHUNT_ANALYTICS_ENDPOINT"
ANALYTICS_ENV_HOSTS = "FOXHUNT_ANALYTICS_HOSTS"
ANALYTICS_ENV_PREFIX = "FOXHUNT_ANALYTICS_PREFIX"

# Every path this site reports -- page views and events alike -- goes under this
# one namespace. The counting lands in the personal site's own GoatCounter site
# rather than a separate one, because the hunt is part of that site rather than
# a thing of its own; so the namespace is what keeps it identifiable, and lets
# one filter on the dashboard show the hunt and nothing else.
#
# It sits under that site's real /projects/ section, which is where the hunt
# belongs as one project among others: filtering on projects/ then reads as all
# of them, and on projects/radio-treasure-hunt as this one. Checked 2026-09-08:
# https://murdoch.is/projects/ is a real page (200) and
# https://murdoch.is/projects/radio-treasure-hunt is a 404, so nothing already
# served collides with what is reported here.
ANALYTICS_PREFIX = "projects/radio-treasure-hunt"

# Event names that do not depend on a role. The role-shaped ones are generated
# from flash.ROLES below, so adding a role adds its events rather than needing
# them written out a second time -- AGENTS.md section 9.
ANALYTICS_EVENTS = (
    "connect/ok",
    "connect/refused-v1",
    "connect/failed",
    "flash/offline",
    "identify/unknown",
    "boot-check/failed",
    "monitor/start",
    # Whether this browser can flash at all, feature-detected rather than
    # guessed from the user agent -- Chrome on iOS has no WebUSB, and a Linux
    # Chromium can be missing udev rules. This is the size of the population
    # whose only route is the .hex download (AGENTS.md section 8).
    "webusb/available",
    "webusb/unsupported",
    "group/default",
    "group/other",
    # Reach and impact. Each fires at most once per session -- see the comment
    # on session() in web/src/analytics.js, and "Reading impact" in
    # ANALYTICS_PLAN.md for what these do and do not license anyone to claim.
    "session/boards/1",
    "session/boards/2-4",
    "session/boards/5-9",
    "session/boards/10+",
    "hunt/ready",
) + tuple("print/%s" % os.path.splitext(name)[0] for name in TEACHING_PAGES)


def analytics_events(roles=None):
    """The closed set of event names the site may send.

    A closed set is the guard that matters: the page holds a board's DAPLink
    serial number, and an allowlist is what stops a later edit beaconing it.
    """
    roles = ROLES if roles is None else roles
    names = list(ANALYTICS_EVENTS)
    for role in sorted(roles):
        names += ["flash/%s/ok" % role, "flash/%s/failed" % role,
                  "identify/%s" % role, "download/%s" % role]
    return sorted(names)


def _pyproject_analytics():
    """Read [tool.foxhunt.analytics] out of pyproject.toml, if it is there.

    tomllib is 3.11+, and pyproject says >=3.9. Rather than fail a build on an
    older interpreter, an unreadable file means "unconfigured" -- but a
    configured section that cannot be read would be a silent loss of analytics,
    so that case stops the build instead.
    """
    path = os.path.join(HERE, "pyproject.toml")
    if not os.path.exists(path):
        return {}
    try:
        import tomllib
    except ImportError:
        with open(path, "rb") as fh:
            if b"[tool.foxhunt.analytics]" in fh.read():
                sys.exit("pyproject.toml configures analytics but this Python has no "
                         "tomllib (3.11+). Upgrade, or pass --analytics-endpoint.")
        return {}
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    for key in ANALYTICS_SECTION:
        data = data.get(key, {})
    return data


def analytics_config(endpoint=None, hosts=None, prefix=None, disabled=False, env=None):
    """Resolve the analytics settings.

    Precedence is the project rule for every setting here: command line, then
    environment, then the TOML file, then off.
    """
    env = os.environ if env is None else env
    if disabled:
        return {"endpoint": "", "hosts": [], "prefix": ANALYTICS_PREFIX,
                "events": analytics_events()}

    from_file = _pyproject_analytics()
    if endpoint is None:
        endpoint = env.get(ANALYTICS_ENV_ENDPOINT, from_file.get("endpoint", ""))
    if hosts is None:
        raw = env.get(ANALYTICS_ENV_HOSTS)
        hosts = raw.split(",") if raw else from_file.get("hosts", [])
    if isinstance(hosts, str):
        hosts = hosts.split(",")
    hosts = [h.strip() for h in hosts if h.strip()]
    if prefix is None:
        prefix = env.get(ANALYTICS_ENV_PREFIX, from_file.get("prefix", ANALYTICS_PREFIX))
    prefix = prefix.strip().strip("/")
    if not prefix:
        sys.exit("analytics prefix must not be empty: it is what identifies this "
                 "site's paths inside a shared GoatCounter site.")

    endpoint = (endpoint or "").strip()
    if endpoint and not endpoint.startswith("https://"):
        # http:// would be blocked as mixed content on the deployed page anyway,
        # so a typo here is worth stopping the build for rather than shipping a
        # beacon that silently never arrives.
        sys.exit("analytics endpoint must be https://, got %r" % endpoint)
    if endpoint and not hosts:
        sys.exit("analytics endpoint is set but no hosts are, so nothing would "
                 "ever be sent. Set hosts, or --no-analytics.")
    return {"endpoint": endpoint, "hosts": hosts, "prefix": prefix,
            "events": analytics_events()}


def device_digest(data):
    """The fingerprint the board computes over one of its own files.

    Deliberately trivial arithmetic, because the other half of this function is
    a MicroPython snippet typed into a raw REPL. Streaming a whole file back
    over DAPLink's serial is a fight with a 512-byte ring buffer; sending a
    digest is not. Measured against real hardware on 2026-09-06 -- the three
    values in test_site.py came off a board, not out of this function.
    """
    h = 0
    for c in bytearray(data):
        h = (h * 31 + c) & 0xFFFFFFFF
    return h


def read(name):
    with open(os.path.join(HERE, name), "rb") as fh:
        return fh.read()


def render_radio_config(group, template=None):
    """radio_config.py with RADIO_GROUP set to `group`.

    Pure, so it can be tested without a board or a browser. The template comes
    from the real file, so its docstring -- including the warning about groups 0
    and 42 -- travels to the device unchanged.
    """
    if not isinstance(group, int) or isinstance(group, bool):
        raise ValueError("radio group must be an int, got %r" % (group,))
    if not GROUP_MIN <= group <= GROUP_MAX:
        raise ValueError(
            "radio group %d is outside %d-%d" % (group, GROUP_MIN, GROUP_MAX))
    if group in GROUP_AVOID:
        raise ValueError(
            "radio group %d invites collisions; radio_config.py explains why" % group)
    if template is None:
        template = radio_config_template()
    if GROUP_PLACEHOLDER not in template:
        raise ValueError("template has no %s to substitute" % GROUP_PLACEHOLDER)
    return template.replace(GROUP_PLACEHOLDER, str(group))


def radio_config_template():
    """radio_config.py with its group replaced by the placeholder.

    Rewrites the assignment rather than the number, so a group that happens to
    appear elsewhere in the prose is left alone.
    """
    text = read("radio_config.py").decode("utf-8")
    out, found = [], 0
    for line in text.split("\n"):
        if line.startswith("RADIO_GROUP =") and not found:
            out.append("RADIO_GROUP = " + GROUP_PLACEHOLDER)
            found += 1
        else:
            out.append(line)
    if found != 1:
        raise ValueError(
            "expected exactly one 'RADIO_GROUP =' assignment in radio_config.py, found %d"
            % found)
    return "\n".join(out)


def device_sources():
    """Every device file as it will be served, with radio_config.py templated.

    Keyed by the name the browser fetches. radio_config.py is the template, not
    the repo's copy, because the group is chosen at flash time.
    """
    sources = {}
    for name in DEVICE_FILES:
        if name == "radio_config.py":
            sources[name] = radio_config_template().encode("utf-8")
        else:
            sources[name] = read(name)
    return sources


def device_code_version(sources=None):
    """A short hash over the device code, independent of the radio group.

    The group is configuration and is reported separately -- a board is not
    running different *code* because someone picked group 23. That is why this
    hashes the template rather than a rendered file.
    """
    if sources is None:
        sources = device_sources()
    h = hashlib.sha256()
    for name in sorted(sources):
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(sources[name])
        h.update(b"\0")
    return h.hexdigest()[:8]


def git(*args):
    """Run a git command, or fail loudly.

    Never returns a placeholder on error: a build stamped 'unknown' is worse
    than a build that stopped, because it ships and nobody notices.
    """
    try:
        out = subprocess.run(
            ("git",) + args, cwd=HERE, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        sys.exit("git is not installed; the site cannot be stamped.")
    except subprocess.CalledProcessError as exc:
        sys.exit("git %s failed: %s"
                 % (" ".join(args), exc.stderr.decode("utf-8", "replace").strip()))
    return out.stdout.decode("utf-8").strip()


def commit_stamp(paths=()):
    """The most recent commit, optionally restricted to some paths.

    Restricting it is how the device-code stamp is found. In CI this needs the
    full history: actions/checkout defaults to a shallow clone, where asking for
    the last commit to touch a device file gives the wrong answer or none.
    """
    args = ["log", "-1", "--format=%H%n%h%n%cI"]
    if paths:
        args.append("--")
        args.extend(paths)
    out = git(*args).split("\n")
    if len(out) != 3 or not out[0]:
        sys.exit("git log returned no commit for %s. In CI, set fetch-depth: 0."
                 % (list(paths) or "HEAD"))
    return {"commit": out[0], "short": out[1], "date": out[2]}


def build_manifest(sources=None):
    """Everything the page needs to know that Python already knows."""
    if sources is None:
        sources = device_sources()
    return {
        "site": commit_stamp(),
        "device": dict(commit_stamp(DEVICE_FILES), version=device_code_version(sources)),
        "micropython": {
            "version": BUNDLED_MICROPYTHON,
            "file": MICROPYTHON_HEX,
            "sha256": MICROPYTHON_SHA256,
        },
        "group": {
            "default": default_group(),
            "placeholder": GROUP_PLACEHOLDER,
            "min": GROUP_MIN,
            "max": GROUP_MAX,
            "avoid": list(GROUP_AVOID),
        },
        "roles": {
            role: {
                "label": ROLE_LABELS.get(role, role),
                "files": [list(pair) for pair in files],
                "entry": [src for src, target in files if target == "main.py"][0],
            }
            for role, files in ROLES.items()
        },
        "monitor": dict(
            start=MONITOR_START,
            rx=MONITOR_RX,
            zones=list(monitor_zones()),
            listen_seconds=monitor_listen_seconds(),
            **monitor_timing()
        ),
        "filesystem_bytes": FILESYSTEM_BYTES,
    }


def hound_scale():
    """The bar-graph scale the worksheet explains, taken from the hound.

    Retyping -87 or "7 dB per bar" into a lesson would guarantee it was wrong
    after the next field trip. ATTEN_STEP in particular is derived, not chosen:
    one press of button A must move the display by exactly one bar.
    """
    import hound_logic
    return {
        "min_rssi": hound_logic.MIN_RSSI,
        "max_rssi": hound_logic.MAX_RSSI,
        "span": hound_logic.RSSI_SPAN,
        "bars": hound_logic.BAR_COUNT,
        "db_per_bar": hound_logic.RSSI_SPAN // hound_logic.BAR_COUNT,
        "atten_step": hound_logic.ATTEN_STEP,
        "max_presses": hound_logic.MAX_ATTENUATION // hound_logic.ATTEN_STEP,
    }


def signed(value):
    """A real minus sign, not a hyphen.

    These pages are read by ten-year-olds meeting negative numbers, and the
    worksheet's graph axis is already labelled with U+2212. Mixing the two
    within one page is the kind of detail a teacher notices.
    """
    return ("&minus;%d" % -value) if value < 0 else str(value)


def calibration_rows():
    """The measured table as HTML rows, for the worksheet's data-handling task."""
    return "\n".join(
        "<tr><td>%d m</td><td>%s dBm</td><td>%d/75</td><td>%d/75</td><td>%d/75</td></tr>"
        % (distance, signed(rssi), z1, z2, z3)
        for distance, rssi, z1, z2, z3 in CALIBRATION)


def substitutions(manifest):
    """Everything the static pages need stamped into them."""
    scale = hound_scale()
    return {
        "__SITE_SHORT__": manifest["site"]["short"],
        "__SITE_DATE__": manifest["site"]["date"],
        "__DEVICE_VERSION__": manifest["device"]["version"],
        "__DEVICE_SHORT__": manifest["device"]["short"],
        "__DEVICE_DATE__": manifest["device"]["date"],
        "__MIN_RSSI__": signed(scale["min_rssi"]),
        "__MAX_RSSI__": signed(scale["max_rssi"]),
        "__BAR_COUNT__": str(scale["bars"]),
        "__DB_PER_BAR__": str(scale["db_per_bar"]),
        "__ATTEN_STEP__": str(scale["atten_step"]),
        "__MAX_PRESSES__": str(scale["max_presses"]),
        "__RSSI_SPAN__": str(scale["span"]),
        "__CALIBRATION_ROWS__": calibration_rows(),
        "__GROUP_DEFAULT__": str(default_group()),
    }


def apply(text, values):
    for token, value in values.items():
        text = text.replace(token, value)
    return text


def default_group():
    from radio_config import RADIO_GROUP
    return RADIO_GROUP


def monitor_zones():
    import integration_check          # inert at import; opens a port only in main()
    return integration_check.ZONES


def monitor_listen_seconds():
    import integration_check
    return integration_check.LISTEN_SECONDS


def monitor_timing():
    """How long the monitor holds a zone before dropping it, and when it decides
    it has lost the fox entirely.

    Taken from the hound rather than chosen here. AGENTS.md section 6 records
    why the game holds a zone for a window instead of latching it: latching made
    the tone a coin flip on packet loss. A monitor that latches has the same bug
    in a worse form, because nothing ever clears it -- a fox heard at 1 m still
    shows all three zones from 20 m away. Sharing the constant also means a
    recalibration moves both together.
    """
    import hound_logic
    return {
        "zone_hold_ms": hound_logic.ZONE_HOLD_MS,
        "signal_timeout_ms": hound_logic.SIGNAL_TIMEOUT_MS,
    }


def check_micropython():
    """The bundled image must be the version we claim, byte for byte.

    A re-cut release asset, or a truncated download, would otherwise be flashed
    to every board the organiser touches.
    """
    path = os.path.join(WEB, "micropython", MICROPYTHON_HEX)
    if not os.path.exists(path):
        sys.exit(
            "Missing %s.\nDownload it from\n"
            "  https://github.com/microbit-foundation/micropython-microbit-v2"
            "/releases/download/v%s/%s"
            % (path, BUNDLED_MICROPYTHON, MICROPYTHON_HEX))
    data = open(path, "rb").read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MICROPYTHON_SHA256:
        sys.exit("%s has sha256 %s, expected %s" % (path, digest, MICROPYTHON_SHA256))
    return path, data


def bundle(out, stamp, entry="main.js", prefix="app", analytics=None):
    """Bundle one JavaScript entry point with esbuild.

    Fails loudly rather than quietly producing a site with no flasher in it.

    Two entry points share this: the setup page and the teaching pages. They
    have one file in common, analytics.js, and bundling the second is what keeps
    that at one copy -- the teaching pages used to load a hand-copied script.

    The analytics settings arrive through --define rather than a fetch, so there
    is no configuration request to fail on a field laptop, and a build with no
    endpoint compiles the beacon away to a constant false.
    """
    source = os.path.join(WEB, "src", entry)
    target = os.path.join(out, "%s.%s.js" % (prefix, stamp))
    npx = shutil.which("npx")
    if npx is None:
        sys.exit("npx not found. Install Node, then run 'npm ci'.")
    if not os.path.isdir(os.path.join(HERE, "node_modules")):
        sys.exit("node_modules is missing. Run 'npm ci' first.")
    # es2019 rather than esbuild's default of "whatever the source says". The
    # bundle carried optional chaining, which is ES2020, so Safari 13.0 and
    # older Firefox failed to parse the whole file -- and a parse error is not a
    # degraded page, it is no JavaScript at all: dead controls, an empty group
    # box, no .hex download and no analytics, on exactly the browsers whose only
    # route is the .hex download. WebUSB itself stays a runtime check.
    cmd = [npx, "esbuild", source, "--bundle", "--format=iife", "--target=es2019",
           "--outfile=" + target, "--log-level=warning",
           "--define:__ANALYTICS__=" + json.dumps(analytics or analytics_config(disabled=True))]
    result = subprocess.run(cmd, cwd=HERE)
    if result.returncode != 0:
        sys.exit("esbuild failed (%d)." % result.returncode)
    if not os.path.exists(target):
        sys.exit("esbuild reported success but %s does not exist." % target)
    return os.path.basename(target)


def write(path, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)


def build(out=DEFAULT_OUT, run_bundle=True, analytics=None):
    sources = device_sources()
    manifest = build_manifest(sources)
    stamp = manifest["site"]["short"]
    if analytics is None:
        analytics = analytics_config(disabled=True)

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "micropython"))

    for name, data in sources.items():
        write(os.path.join(out, name), data)

    hex_path, hex_data = check_micropython()
    write(os.path.join(out, "micropython", MICROPYTHON_HEX), hex_data)

    write(os.path.join(out, "manifest.json"), json.dumps(manifest, indent=1) + "\n")

    values = substitutions(manifest)
    if run_bundle:
        script = bundle(out, stamp, analytics=analytics)
        teaching_script = bundle(out, stamp, entry="teaching.js", prefix="teaching",
                                 analytics=analytics)
    else:
        script, teaching_script = "app.js", "teaching.js"

    page = apply(open(os.path.join(WEB, "index.html")).read(), values)
    write(os.path.join(out, "index.html"), page.replace("__SCRIPT__", script))

    for name in TEACHING_PAGES:
        page = apply(open(os.path.join(WEB, name)).read(), values)
        write(os.path.join(out, name), page.replace("__TEACHING_SCRIPT__", teaching_script))

    for name in ("app.css", "teaching.css"):
        shutil.copyfile(os.path.join(WEB, name), os.path.join(out, name))

    sw = open(os.path.join(WEB, "src", "sw.js")).read().replace("__STAMP__", stamp)
    write(os.path.join(out, "sw.js"), sw)

    return manifest, out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--no-bundle", action="store_true",
                    help="skip esbuild (the page will not work; for checking the rest)")
    # Command line beats environment beats pyproject.toml beats off.
    ap.add_argument("--analytics-endpoint", metavar="URL",
                    help="GoatCounter /count endpoint (overrides $%s)" % ANALYTICS_ENV_ENDPOINT)
    ap.add_argument("--analytics-hosts", metavar="HOST,HOST",
                    help="only beacon when served from these hostnames (overrides $%s)"
                         % ANALYTICS_ENV_HOSTS)
    ap.add_argument("--analytics-prefix", metavar="NAME",
                    help="namespace every reported path (overrides $%s)" % ANALYTICS_ENV_PREFIX)
    ap.add_argument("--no-analytics", action="store_true",
                    help="build with no beacon at all, whatever is configured")
    args = ap.parse_args()

    analytics = analytics_config(endpoint=args.analytics_endpoint,
                                 hosts=args.analytics_hosts,
                                 prefix=args.analytics_prefix,
                                 disabled=args.no_analytics)
    manifest, out = build(args.out, run_bundle=not args.no_bundle, analytics=analytics)
    print("site      %s" % out)
    print("flasher   %s  %s" % (manifest["site"]["short"], manifest["site"]["date"]))
    print("device    %s  (%s  %s)" % (manifest["device"]["version"],
                                      manifest["device"]["short"],
                                      manifest["device"]["date"]))
    print("roles     %s" % ", ".join(sorted(manifest["roles"])))
    # Printed so a build that quietly lost its analytics shows up in the CI log
    # rather than only on a dashboard that stops moving.
    print("analytics %s" % (("%s (%s) under %s/" % (analytics["endpoint"],
                                                    ", ".join(analytics["hosts"]),
                                                    analytics["prefix"]))
                            if analytics["endpoint"] else "off"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
