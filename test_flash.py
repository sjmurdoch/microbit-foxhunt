"""Tests for the flashing helper's pure logic.

Anything needing a board is exercised by `make flash-*` itself, which verifies
each file by hash and boot-checks the result.
"""
import pytest

from flash import (
    LATEST_MICROPYTHON,
    ROLES,
    board_generation,
    describe_firmware,
    parse_version,
)

V2_MACHINE = "micro:bit with nRF52833"
V1_MACHINE = "micro:bit with nRF51822"


@pytest.mark.parametrize("text,expected", [
    ("2.1.2", (2, 1, 2, 1)),
    ("2.0.0", (2, 0, 0, 1)),
    ("2.1.0-beta.1", (2, 1, 0, 0)),   # trailing 0 marks a pre-release
    ("1.0.1", (1, 0, 1, 1)),
    ("2.1", (2, 1, 0, 1)),            # short forms pad out
])
def test_parse_version(text, expected):
    assert parse_version(text) == expected


def test_versions_order_correctly():
    assert parse_version("2.0.0") < parse_version("2.1.2")
    assert parse_version("1.0.1") < parse_version("2.0.0")


def test_prerelease_sorts_below_its_release():
    """Plain tuple comparison gets this backwards: '2.1.0-beta.1' has more
    components than '2.1.0' and would otherwise look newer."""
    assert parse_version("2.1.0-beta.1") < parse_version("2.1.0")
    assert parse_version("2.1.0-beta.1") > parse_version("2.0.0")


@pytest.mark.parametrize("machine,expected", [
    (V2_MACHINE, "v2"),
    (V1_MACHINE, "v1"),
    ("something else", "?"),
    (None, "?"),
])
def test_board_generation(machine, expected):
    assert board_generation(machine) == expected


def test_v1_firmware_is_called_out():
    """A v2 board flashed with uflash silently becomes a v1 board with no
    speaker. That must be visible at a glance."""
    text = describe_firmware("1.0.1", V1_MACHINE)
    assert "v1" in text
    assert "uflash" in text


def test_outdated_firmware_is_flagged():
    assert LATEST_MICROPYTHON in describe_firmware("2.0.0", V2_MACHINE)


def test_current_firmware_is_not_nagged_about():
    text = describe_firmware(LATEST_MICROPYTHON, V2_MACHINE)
    assert "available" not in text
    assert "uflash" not in text


def test_unreachable_board_does_not_break_the_listing():
    assert "unknown" in describe_firmware(None, None)


def test_main_py_is_written_last():
    """Nothing on the board should be runnable until its dependencies are
    there, so main.py must be the final file copied."""
    for role, files in ROLES.items():
        targets = [target for _, target in files]
        assert targets[-1] == "main.py", role
        assert targets.count("main.py") == 1, role


def test_both_roles_ship_the_shared_radio_config():
    for role, files in ROLES.items():
        assert "radio_config.py" in [target for _, target in files], role
