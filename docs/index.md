---
hide:
  - navigation
  - toc
---

# Nematostella Toolkit

<p class="hero-subtitle">An open-source <a href="https://napari.org">napari</a> toolkit for studying
circadian rhythms and sleep-like behavior in <em>Nematostella vectensis</em> —
from synchronized image capture to automated activity analysis.</p>

<div class="grid cards" markdown>

-   :material-camera-iris:{ .lg .middle } &nbsp; **Recording Plugin**

    ---

    Synchronized timelapse capture with dual-LED illumination (IR + White) and
    ESP32-based hardware synchronization for drift-free, long-term recordings.

    [:octicons-arrow-right-24: Overview](recording.md) ·
    [Hardware](hardware.md) ·
    [Flash firmware](installer.html)

-   :material-chart-line:{ .lg .middle } &nbsp; **Analysis Plugin**

    ---

    Quantify activity and movement from HDF5, Zarr, and AVI recordings, then run
    circadian rhythm and sleep-like state analysis — all inside napari.

    [:octicons-arrow-right-24: Overview](analysis/index.md) ·
    [User Guide](analysis/user-guide.md) ·
    [Circadian analysis](analysis/circadian-analysis.md)

</div>

## How the toolkit fits together

<div class="grid cards" markdown>

-   :material-numeric-1-circle:{ .lg .middle } &nbsp; **Record**

    ---

    Build the imager, flash the ESP32, and capture synchronized light/dark
    time series with the [Recording Plugin](recording.md).

-   :material-numeric-2-circle:{ .lg .middle } &nbsp; **Analyze**

    ---

    Detect ROIs and quantify movement over the recording with the
    [Analysis Plugin](analysis/index.md).

-   :material-numeric-3-circle:{ .lg .middle } &nbsp; **Interpret**

    ---

    Derive circadian rhythms and sleep-like states — see
    [Circadian Analysis](analysis/circadian-analysis.md) and
    [Extended Analysis](analysis/extended-analysis.md).

</div>

## Install

Neither plugin is published on PyPI — both install from source.

=== "Recording Plugin"

    ```bash
    git clone https://github.com/s1alknau/Nematostella-time-series.git
    cd Nematostella-time-series
    pip install -e .
    ```

=== "Analysis Plugin"

    ```bash
    git clone https://github.com/s1alknau/napari-hdf5-activity.git
    cd napari-hdf5-activity
    pip install -e ".[zarr]"
    ```

Both plugins appear under napari's *Plugins* menu after installation.

!!! warning "Recording with the HIK GigE camera needs more than pip"
    The recording plugin takes its frames from the napari layer that **ImSwitch**
    publishes, so ImSwitch, the **Hik Robotics MVS SDK**, a **Qt binding with the
    GUI packages** (`qtpy`, `napari`, `pyqtgraph`, `qdarkstyle` — ImSwitch's own
    install brings none of them) and the camera setup JSON have to be in place
    first — all inside one conda environment (`imswitch21`, Python 3.12), and
    installed *before* ImSwitch is started. See
    [Software Setup](software-setup.md) for the full walkthrough, or
    [Get started](recording.md#get-started) for the short version.

---

<p class="hero-footnote">Built from the
<a href="https://github.com/s1alknau/Nematostella-time-series">recording</a> and
<a href="https://github.com/s1alknau/napari-hdf5-activity">analysis</a>
repositories with <a href="https://www.mkdocs.org/">MkDocs</a> +
<a href="https://squidfunk.github.io/mkdocs-material/">Material</a>.</p>
