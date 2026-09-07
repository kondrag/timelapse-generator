"""Tests for scripts/sun.py CLI (run with system python3, as production does)."""

import subprocess
import sys

SUN_PY = "scripts/sun.py"


def run_sun(*args):
    return subprocess.run(
        ["/usr/bin/python3", SUN_PY, *args],
        capture_output=True,
        text=True,
    )


def test_dawn_today_outputs_hh_mm():
    result = run_sun("--dawn")
    assert result.returncode == 0, result.stderr
    assert sys.stdin is not None  # keep linters honest about imports
    out = result.stdout.strip()
    assert len(out) == 5 and out[2] == ":", f"expected HH:MM, got {out!r}"


def test_dusk_on_known_date_matches_evidence():
    # Ground truth: first night image captured 2026-09-06 was
    # AuroraCam_00_20260906203600.jpg (camera starts at dusk).
    result = run_sun("--dusk", "--date", "2026-09-06")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "20:36"


def test_dawn_on_known_date_matches_log_verified_value():
    # Ground truth: dawn in Gilman WI on 2026-09-07 was 05:26.
    result = run_sun("--dawn", "--date", "2026-09-07")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "05:26"


def test_date_shifts_dusk_across_days():
    late_summer = run_sun("--dusk", "--date", "2026-09-06").stdout.strip()
    deep_winter = run_sun("--dusk", "--date", "2026-12-21").stdout.strip()
    assert late_summer != deep_winter, "dusk should differ between Sep and Dec"


def test_invalid_date_exits_nonzero():
    result = run_sun("--dusk", "--date", "not-a-date")
    assert result.returncode != 0


def test_no_position_flag_exits_nonzero():
    result = run_sun("--date", "2026-09-06")
    assert result.returncode != 0


def test_multiple_position_flags_exit_nonzero():
    result = run_sun("--dawn", "--dusk")
    assert result.returncode != 0
