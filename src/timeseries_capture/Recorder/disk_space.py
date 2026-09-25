"""Free-space check for a planned recording.

A 72 h run at 5 s intervals writes ~120 GB of uncompressed frames. When the
target disk cannot hold that, nothing today notices: the writer keeps going
until the disk is full, then dies without a usable error -- and the recording
log, which lives on the same disk, cannot record that either. One run lost
40 of its 72 hours that way, and the abrupt end of the log was the only trace.

So the size is computed up front and compared against what is actually free.
Both data managers write uncompressed (compression=None / compressors=None),
which makes the estimate exact rather than optimistic.
"""

import logging
import shutil
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Keep a reserve free so the disk never actually reaches zero: a full volume
# breaks far more than this recording.
MARGIN_FRACTION = 0.03
MIN_MARGIN_BYTES = 2 * 1024**3  # 2 GiB

# Per-frame telemetry (timestamps, LED state, temperature, ...) next to the
# image data. Tiny against a 2.4 MB frame, but counted rather than ignored.
TELEMETRY_BYTES_PER_FRAME = 256


@dataclass
class SpaceEstimate:
    """What a planned recording needs, and what the target disk offers."""

    frames: int
    frame_bytes: Optional[int]
    required_bytes: Optional[int]
    free_bytes: int
    margin_bytes: int
    # Recordings writing to this disk at the same time. With several cameras
    # every unit writes its own file to the same volume, so each of them
    # checking alone would see the full free space and all of them would
    # happily start -- and together overrun it.
    streams: int = 1

    @property
    def known(self) -> bool:
        """False when the frame size could not be determined."""
        return self.required_bytes is not None

    @property
    def fits(self) -> bool:
        """True when the recording fits with the safety margin kept free."""
        if not self.known:
            return True  # never block on a guess
        return self.required_bytes + self.margin_bytes <= self.free_bytes

    @property
    def shortfall_bytes(self) -> int:
        if self.fits or not self.known:
            return 0
        return self.required_bytes + self.margin_bytes - self.free_bytes

    def describe(self) -> str:
        """One-line summary for the log and the GUI."""
        if not self.known:
            return (
                f"Free space not verified: frame size unknown "
                f"({self.frames} frames planned, {_gb(self.free_bytes)} free)"
            )
        verdict = "fits" if self.fits else "DOES NOT FIT"
        per_stream = f"{self.frames} frames x {_mb(self.frame_bytes)}"
        if self.streams > 1:
            per_stream += f" x {self.streams} cameras"
        text = (
            f"{per_stream} = {_gb(self.required_bytes)} needed, "
            f"{_gb(self.free_bytes)} free "
            f"(reserve {_gb(self.margin_bytes)}): {verdict}"
        )
        if not self.fits:
            text += f", short by {_gb(self.shortfall_bytes)}"
        return text


def _gb(n: float) -> str:
    return f"{n / 1024**3:.1f} GB"


def _mb(n: float) -> str:
    return f"{n / 1024**2:.2f} MB"


def planned_frame_count(duration_min: float, interval_sec: float) -> int:
    """Frames a run of this length produces. Matches the recorder's own loop."""
    if interval_sec <= 0:
        return 0
    return int(duration_min * 60 / interval_sec)


def frame_bytes_from_camera(camera: Any, save_as_uint8: bool = False) -> Optional[int]:
    """Bytes one stored frame takes, or None when the camera won't say.

    Returning None is a real answer: the caller warns instead of blocking,
    because refusing a recording over a guessed frame size would be worse
    than the problem being solved.
    """
    if camera is None:
        return None

    width = height = None
    itemsize = None

    # The adapter's own report is the first choice.
    try:
        info = camera.get_camera_info() or {}
        width = info.get("width")
        height = info.get("height")
        dtype = info.get("dtype")
        if dtype:
            import numpy as np

            try:
                itemsize = np.dtype(dtype).itemsize
            except TypeError:
                itemsize = None
    except Exception as exc:
        logger.debug(f"Camera info unavailable for space estimate: {exc}")

    # Before the first capture the adapter has no frame to report, so fall
    # back to the shape the ImSwitch detector already knows.
    if not (width and height):
        shape = _detector_shape(camera)
        if shape and len(shape) >= 2:
            height, width = shape[0], shape[1]

    if not (width and height):
        return None

    if itemsize is None:
        # HIK sensors here deliver 12 bit in a uint16 container unless the
        # writer is told to downconvert.
        itemsize = 1 if save_as_uint8 else 2
    elif save_as_uint8:
        itemsize = 1

    return int(width) * int(height) * int(itemsize)


def _detector_shape(camera: Any) -> Optional[tuple]:
    """Frame shape straight from the ImSwitch detector, if reachable."""
    manager = getattr(camera, "camera_manager", None)
    name = getattr(camera, "detector_name", None)
    if manager is None or not name:
        return None
    try:
        shape = getattr(manager[name], "shape", None)
        return tuple(shape) if shape else None
    except Exception as exc:
        logger.debug(f"Detector shape unavailable: {exc}")
        return None


def estimate_recording_space(
    output_dir: str,
    duration_min: float,
    interval_sec: float,
    frame_bytes: Optional[int],
    streams: int = 1,
) -> SpaceEstimate:
    """Measure what the planned run needs against the target disk.

    ``streams`` is the number of recordings writing to this disk at the same
    time -- one per camera. Every one of them writes its own file of the same
    size, so the requirement scales with it.
    """
    frames = planned_frame_count(duration_min, interval_sec)
    streams = max(1, int(streams))

    try:
        free_bytes = shutil.disk_usage(output_dir).free
    except OSError as exc:
        logger.warning(f"Cannot read free space for {output_dir}: {exc}")
        free_bytes = 0

    required = None
    if frame_bytes:
        required = frames * (frame_bytes + TELEMETRY_BYTES_PER_FRAME) * streams

    margin = max(MIN_MARGIN_BYTES, int(free_bytes * MARGIN_FRACTION))

    return SpaceEstimate(
        frames=frames,
        frame_bytes=frame_bytes,
        required_bytes=required,
        free_bytes=free_bytes,
        margin_bytes=margin,
        streams=streams,
    )
