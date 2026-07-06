# Analysis Plugin — Overview

[![PyPI](https://img.shields.io/pypi/v/napari-hdf5-activity.svg?color=teal)](https://pypi.org/project/napari-hdf5-activity)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/napari-hdf5-activity)](https://napari-hub.org/plugins/napari-hdf5-activity)

**`napari-hdf5-activity`** is a [napari](https://napari.org) plugin for analyzing
activity and movement behavior from **HDF5, Zarr, and AVI** timelapse
recordings — the companion to the [Recording Plugin](../recording.md).

## Key features

<div class="grid cards" markdown>

-   :material-target:{ .lg .middle } &nbsp; **ROI detection**

    ---

    Automatic region-of-interest detection and per-animal movement
    quantification across the recording.

-   :material-weather-night:{ .lg .middle } &nbsp; **Circadian analysis**

    ---

    Activity over light/dark cycles, rhythm detection, and sleep-like state
    classification.

-   :material-file-video:{ .lg .middle } &nbsp; **Multiple formats**

    ---

    Reads HDF5, Zarr, and AVI — analyze live recordings or archived data.

-   :material-speedometer:{ .lg .middle } &nbsp; **Fast**

    ---

    Multiprocessing pipeline tuned for large multi-ROI, multi-day datasets.

</div>

## Get started

1. **Install**

    ```bash
    pip install napari-hdf5-activity
    ```

2. **Follow the [User Guide](user-guide.md)** — a walkthrough of the GUI tabs.

3. **Analyze rhythms** — see [Circadian Analysis](circadian-analysis.md) and the
   in-depth [Extended Analysis](extended-analysis.md) reference.

## Documentation

- [User Guide](user-guide.md) — step-by-step walkthrough of the GUI tabs.
- [Circadian Analysis](circadian-analysis.md) — activity over light/dark cycles.
- [Entrainment Protocol](entrainment-protocol.md) — experimental LD/DD design for entrainment studies.
- [Extended Analysis](extended-analysis.md) — in-depth analysis reference.
- [Performance Optimizations](performance.md) — multiprocessing & tuning.
- [AVI Integration](avi-integration.md) — working with AVI recordings.

!!! note
    These pages are pulled automatically from the
    [`napari-hdf5-activity`](https://github.com/s1alknau/napari-hdf5-activity)
    repository when the site is built.
