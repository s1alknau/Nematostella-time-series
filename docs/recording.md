# Recording Plugin — Overview

[![PyPI](https://img.shields.io/pypi/v/nematostella-time-series.svg?color=teal)](https://pypi.org/project/nematostella-time-series)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/nematostella-time-series)](https://napari-hub.org/plugins/nematostella-time-series)

**`nematostella-time-series`** is a [napari](https://napari.org) plugin for
synchronized timelapse recording of *Nematostella vectensis* with dual-LED
illumination (IR + White) and ESP32-based hardware synchronization.

## Key features

<div class="grid cards" markdown>

-   :material-sync:{ .lg .middle } &nbsp; **Hardware-synchronized LEDs**

    ---

    Camera exposure and LED illumination are synchronized via the ESP32 for
    precise, repeatable timing.

-   :material-lightbulb-on:{ .lg .middle } &nbsp; **Dual-LED illumination**

    ---

    Independent IR (850 nm) and White (broad-spectrum) channels for oblique
    lighting and light stimulation.

-   :material-clock-outline:{ .lg .middle } &nbsp; **Drift-compensated timing**

    ---

    Frame timing measured from absolute recording start — no cumulative drift
    over multi-day runs.

-   :material-database:{ .lg .middle } &nbsp; **Zarr & HDF5**

    ---

    Concurrent read-while-write enables live analysis during an ongoing
    recording.

</div>

## Get started

1. **Install**

    ```bash
    pip install nematostella-time-series
    ```

2. **Build the imager** — see [Hardware & Assembly](hardware.md), the
   [Hardware Photos](images/README.md) and the [3D-Printed Parts](3D_Druck/README.md).

3. **Flash the ESP32** — open the [Firmware Installer](installer.html) in
   Chrome/Edge (no toolchain required). The
   [ESP32-S3-BOX-3 (Alternative)](ESP32-S3-BOX-3_CONFIGURATION.md) board is also
   supported.

4. **Record** — launch napari and open *Plugins → Nematostella Timelapse
   Recording*.

!!! tip "Full assembly instructions"
    The complete, step-by-step hardware assembly guide lives in the
    [project README on GitHub](https://github.com/s1alknau/Nematostella-time-series#readme).
    The [Hardware & Assembly](hardware.md) page here summarizes the wiring and
    pinout you need most often.

## Next steps

- Analyze your recordings with the [Analysis Plugin](analysis/index.md).
- Review the light/dark [Circadian Protocol](circadian.md).
- See the [Changelog](changelog.md) for release history.
