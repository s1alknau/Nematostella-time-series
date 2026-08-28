"""
Windows Defender exclusion helper (used by the napari-timelapse-capture
main widget on first run).

Behaviour:
  - Only active on win32.
  - Silent check via PowerShell (no admin needed) whether the recording
    directory + python.exe + imswitch.exe are already in the exclusion list.
  - If any are missing AND the user hasn't previously declined:
      shows a QMessageBox asking to run scripts/setup_defender_exclusions.ps1
      elevated (single UAC prompt).
  - The user's decline is remembered via QSettings so the dialog doesn't
    reappear every time napari starts.

The exclusion list is defined once (RECORDING_PATHS + PYTHON_PROCESSES)
and shared with setup_defender_exclusions.ps1 — if you change one, change
the other too. In practice they'll differ per install; this module only
checks whether *some* nematostella-related paths/processes are excluded,
not exact-match every entry.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# Markers used to decide whether Defender is already configured for this
# repo. Any exclusion whose path/process contains one of these substrings
# counts as "yes, they've set us up".
PATH_MARKERS = (
    "nematostella-time-series",
    "recordings",
)
PROCESS_MARKERS = (
    r"\.conda\envs\new_imswitch\python.exe",
    r"\.conda\envs\imswitch21\python.exe",
    r"\.conda\envs\new_imswitch\Scripts\imswitch.exe",
)


# QSettings key so a "no thanks" reply survives across sessions.
QSETTINGS_ORG = "nematostella"
QSETTINGS_APP = "timeseries_capture"
QSETTINGS_DECLINED_KEY = "defender_exclusions/user_declined"


def _find_setup_script() -> Path | None:
    """Locate scripts/setup_defender_exclusions.ps1 relative to this file."""
    # this file lives in src/timeseries_capture/defender_setup.py
    # setup script lives in <repo-root>/scripts/setup_defender_exclusions.ps1
    here = Path(__file__).resolve()
    for up in (here.parents[2], here.parents[3]):
        candidate = up / "scripts" / "setup_defender_exclusions.ps1"
        if candidate.exists():
            return candidate
    return None


def _query_defender_exclusions() -> tuple[list[str], list[str]]:
    """
    Run `powershell Get-MpPreference` and return (exclusion_paths, exclusion_processes).

    Requires no admin rights. Returns empty lists on any failure
    (e.g. Get-MpPreference unavailable, Defender disabled, non-Windows).
    """
    if sys.platform != "win32":
        return [], []

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        # Emit two blocks separated by "---SEP---". Convert null to empty.
        "$p = (Get-MpPreference).ExclusionPath; "
        "$e = (Get-MpPreference).ExclusionProcess; "
        "if ($p) { $p -join [Environment]::NewLine }; "
        "'---SEP---'; "
        "if ($e) { $e -join [Environment]::NewLine }",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            # CREATE_NO_WINDOW: don't flash a console window on win32
            creationflags=0x08000000,
        )
    except Exception as e:
        logger.debug(f"Get-MpPreference failed: {e}")
        return [], []

    if result.returncode != 0:
        logger.debug(f"Get-MpPreference nonzero exit: {result.stderr.strip()}")
        return [], []

    out = result.stdout
    if "---SEP---" not in out:
        return [], []

    paths_blob, procs_blob = out.split("---SEP---", 1)
    paths = [ln.strip() for ln in paths_blob.splitlines() if ln.strip()]
    procs = [ln.strip() for ln in procs_blob.splitlines() if ln.strip()]
    return paths, procs


def _missing_exclusions() -> tuple[bool, bool]:
    """
    Return (path_needs_setup, process_needs_setup) — True if no exclusion
    for that category contains any of our markers.
    """
    paths, procs = _query_defender_exclusions()

    path_ok = any(any(marker.lower() in p.lower() for marker in PATH_MARKERS) for p in paths)
    proc_ok = any(any(marker.lower() in p.lower() for marker in PROCESS_MARKERS) for p in procs)
    return (not path_ok, not proc_ok)


def _run_elevated_setup(script_path: Path) -> bool:
    """
    Kick off the setup script via UAC-elevated PowerShell. Returns True if
    the launch call succeeded (does not wait for the user's UAC decision).
    """
    inner = (
        f"Start-Process powershell.exe "
        f"-Verb runAs "
        f"-ArgumentList '-NoProfile', "
        f"'-ExecutionPolicy', 'Bypass', "
        f"'-File', '\"{script_path}\"'"
    )
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        inner,
    ]
    try:
        # Fire-and-forget: the elevated shell will run detached.
        subprocess.Popen(cmd, creationflags=0x08000000)
        return True
    except Exception as e:
        logger.warning(f"Could not launch elevated setup: {e}")
        return False


def _user_previously_declined() -> bool:
    try:
        from qtpy.QtCore import QSettings

        settings = QSettings(QSETTINGS_ORG, QSETTINGS_APP)
        return bool(settings.value(QSETTINGS_DECLINED_KEY, False, type=bool))
    except Exception:
        return False


def _remember_decline() -> None:
    try:
        from qtpy.QtCore import QSettings

        settings = QSettings(QSETTINGS_ORG, QSETTINGS_APP)
        settings.setValue(QSETTINGS_DECLINED_KEY, True)
        settings.sync()
    except Exception as e:
        logger.debug(f"Could not persist decline: {e}")


def maybe_offer_defender_setup(parent_widget=None) -> None:
    """
    Entry point. Call this once from the main widget's __init__ (via
    QTimer.singleShot so the UI is already visible).

    On non-Windows: no-op.
    On Windows: silent check, then dialog if setup is needed and the user
    hasn't declined before.
    """
    if sys.platform != "win32":
        return

    if _user_previously_declined():
        logger.info("Defender exclusion setup skipped (user previously declined)")
        return

    path_missing, proc_missing = _missing_exclusions()
    if not (path_missing or proc_missing):
        logger.info("Defender exclusions already in place — nothing to do")
        return

    script = _find_setup_script()
    if script is None:
        logger.warning(
            "Defender setup script not found (scripts/setup_defender_exclusions.ps1); "
            "skipping auto-offer"
        )
        return

    try:
        from qtpy.QtWidgets import QMessageBox
    except Exception:
        # No Qt available — can't ask. Log and skip.
        logger.info(
            "Defender exclusions missing; Qt not available so skipping the prompt. "
            f"Run manually: {script}"
        )
        return

    missing_parts = []
    if path_missing:
        missing_parts.append("recording folder")
    if proc_missing:
        missing_parts.append("python/imswitch processes")

    msg = QMessageBox(parent_widget)
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Windows Defender — reduce recording timing jitter")
    msg.setText(
        "Windows Defender scans the growing recording file, which causes "
        "sporadic 10-20 s spikes in your frame intervals.\n\n"
        f"Recommended: add Defender exclusions for the {', '.join(missing_parts)}.\n\n"
        "A Windows UAC prompt will appear once — accepting it applies the "
        "exclusions permanently."
    )
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
    yes_btn = msg.button(QMessageBox.Yes)
    yes_btn.setText("Set up now (UAC)")
    no_btn = msg.button(QMessageBox.No)
    no_btn.setText("Not now")
    cancel_btn = msg.button(QMessageBox.Cancel)
    cancel_btn.setText("Never ask again")

    result = msg.exec_()

    if result == QMessageBox.Yes:
        launched = _run_elevated_setup(script)
        if launched:
            logger.info("Launched elevated defender setup (waiting for UAC)")
        else:
            logger.warning("Failed to launch elevated setup")
    elif result == QMessageBox.Cancel:
        _remember_decline()
        logger.info("User chose 'never ask again' for defender setup")
    else:
        logger.info("User postponed defender setup")
