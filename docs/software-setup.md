# Software Setup — ImSwitch, HIK SDK & Plugin

This page is the long form of the [Get started](recording.md#get-started) list on
the overview page: everything that has to be installed, in which order, and how
to verify each step before moving on.

## How the pieces fit together

The recording plugin does **not** talk to the camera directly. ImSwitch owns the
camera and publishes every live frame into the napari viewer; the plugin reads
its frames from that napari layer and drives the ESP32 (LEDs, sensors) itself
over the serial port:

```
HIK MV-CS013-60GN ──GigE──▶ MVS SDK ──▶ ImSwitch (HikCamManager)
                                             │
                                             ▼  live image
                                        napari layer
                                             │  layer.data
                                             ▼
                            Nematostella Timelapse Recording  ──▶ HDF5 / Zarr
                                             │
                                             ▼  USB serial (COMx)
                                          ESP32  ──▶ IR / White LED, DHT22
```

Two consequences drive the whole installation:

1. **ImSwitch, napari and the plugin run in the same Python process**, so they
   must be installed into the **same environment** — here the conda environment
   `imswitch21`.
2. **All requirements must be installed before ImSwitch is started for the first
   time.** Installing packages into a running environment does not retrofit them
   into the running ImSwitch/napari session, and a half-installed environment is
   the most common cause of "the plugin does not show up in the Plugins menu".

## Prerequisites

| Component | Requirement |
| --- | --- |
| Operating system | Windows 10/11, Linux or macOS (Windows is the reference setup) |
| Python | 3.11 in a dedicated conda environment (the plugin itself needs ≥ 3.10) |
| Camera | Hik Robotics MV-CS013-60GN (GigE, NIR) — see [Hardware & Assembly](hardware.md) |
| Camera driver | Hikrobot **MVS SDK** (provides the runtime the `HikCamManager` binds to) |
| Network | Gigabit NIC for the camera, camera and adapter in the same subnet |
| Controller | ESP32 DevKit with the project [firmware](installer.html) flashed |

---

## Step 1 — Create the `imswitch21` conda environment

```bash
conda create -n imswitch21 python=3.11 -y
conda activate imswitch21
```

Verify that the environment is really the active one before installing anything:

=== "Windows"

    ```powershell
    python -V          # Python 3.11.x
    where python       # ...\envs\imswitch21\python.exe
    ```

=== "macOS / Linux"

    ```bash
    python -V          # Python 3.11.x
    which python       # .../envs/imswitch21/bin/python
    ```

!!! warning "Activate before every start"
    `conda activate imswitch21` is required for every later start of ImSwitch,
    napari and for every `pip install` that belongs to this setup. A second
    environment with a partial install is the usual reason the plugin or the HIK
    camera silently disappears.

---

## Step 2 — Install the Hik Robotics SDK (MVS)

ImSwitch's `HikCamManager` is a thin wrapper around Hikrobot's machine-vision
runtime. Without the SDK installed, ImSwitch starts but the detector stays empty.

1. Download the **MVS** package for your operating system from the
   [Hikrobot download center](https://www.hikrobotics.com/en/machinevision/service/download)
   (Windows installer, Linux `.tar.gz`/`.deb`, macOS `.pkg`).
2. Install it **before** ImSwitch. The package provides the MVS client
   application, the GenICam runtime, the GigE driver and the Python bindings
   (`MvImport`), and sets the SDK environment variables (`MVCAM_COMMON_RUNENV`,
   `MVCAM_SDK_PATH`) through which the runtime is located.
3. Reboot (Windows) or open a new shell so those variables are visible inside
   the conda environment.

### Verify the camera before touching ImSwitch

Open the **MVS client** that ships with the SDK. The camera must be listed and
must open in live view there. If it does not, ImSwitch cannot open it either —
fix it here first:

| Symptom | Check |
| --- | --- |
| Camera not listed | Camera IP and NIC IP in the same subnet (e.g. NIC `192.168.1.10`, camera `192.168.1.101`, mask `255.255.255.0`) |
| Listed but unreachable | Firewall blocking GigE discovery, or a second NIC on the same subnet |
| Frames drop or tear | Enable jumbo frames (MTU 9000) on the camera NIC, use a Cat-6 cable, disable NIC power saving |
| Very dark image | Expected — the IR imager is dark without the LEDs running; use the plugin's LED control |

!!! note "macOS on Apple Silicon"
    The MVS SDK for macOS is x86_64-only. Run the whole stack in an x86_64
    environment (Rosetta 2), otherwise the SDK libraries will not load.

---

## Step 3 — Install ImSwitch

This setup uses **our own fork** of ImSwitch, branch `nematostella-rig`. It is
openUC2's ImSwitch 2.1.191 (commit `8b424d5`) plus three commits this rig needs,
and it provides both the `HikCamManager` detector and the UC2 `ESP32Manager`:

```bash
conda activate imswitch21
git clone -b nematostella-rig https://github.com/s1alknau/ImSwitch.git
cd ImSwitch
pip install -e .
```

!!! warning "Do not clone `openUC2/ImSwitch` directly"
    Three things fail with upstream:

    - The Qt GUI aborts on startup. Signals are assigned in `__init__`, but
      `pyqtSignal` only binds as a class attribute:
      `AttributeError: 'pyqtSignal' object has no attribute 'connect'`
    - `fcntl` is missing on Windows (`imcontrol/model/io/session.py`).
    - `setLaserGalvo()` does not exist.
      [napari-lsft](https://github.com/s1alknau/napari-lsft) calls this endpoint
      over the HTTP API to start the light-sheet galvo at acquisition start.

    Every change is documented commit by commit and mirrored as patch files
    under [`imswitch-patches/`](https://github.com/s1alknau/Nematostella-time-series/tree/Nematostella-time-series-IR/imswitch-patches).

### Choose a Qt binding and install the GUI stack

`pip install -e .` installs **no GUI packages at all** — neither a Qt binding
nor the layers ImSwitch's windows are built on. Pick a binding:

```bash
pip install "PySide6==6.8.3"   # Qt 6.8.3 - recommended
# or: pip install -e ".[PyQt5]"  # Qt 5.15.2, pulls the GUI stack below with it
```

PyQt5 shears the client area diagonally on some dual-GPU machines. With PySide6,
`site-packages/PyQt5` must be **fully removed** - `pyqtgraph` treats even an
emptied directory as an installed binding and then picks the wrong one.

The binding alone is not enough. On the **PySide6** path, add the packages
ImSwitch imports on startup (the `PyQt5` extra already contains them):

```bash
pip install qtpy napari pyqtgraph qdarkstyle
```

| Package | Where ImSwitch needs it |
| --- | --- |
| `qtpy` | `imcommon/framework/qt.py` — the abstraction layer over the binding, imported before anything else |
| `napari` | `imcommon/view/guitools/naparitools.py` — the camera view *is* an embedded napari viewer, and it is the layer this plugin reads |
| `pyqtgraph` | plot widgets in `imcontrol/view/widgets/` |
| `qdarkstyle` | `imcommon/view/MultiModuleWindow.py` — the main window stylesheet |

!!! danger "`ModuleNotFoundError: No module named 'qtpy'`"
    This is what a missing GUI stack looks like — ImSwitch starts, prints its
    version and then dies during the import chain:

    ```
    Starting ImSwitch using version:  2.1.191
      File ".../imswitch/imcommon/framework/qt.py", line 2, in <module>
        from qtpy import QtCore
    ModuleNotFoundError: No module named 'qtpy'
    ```

    Install the packages above (Step 5 also brings `qtpy` and `napari` in as
    plugin dependencies) and start ImSwitch again.

!!! note "Linux: Qt platform plugin"
    If the imports succeed but the GUI aborts with
    `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`, install the
    system libraries the binding links against and make sure a display is
    available (`echo $DISPLAY`):

    ```bash
    sudo apt install libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0 libegl1
    ```

!!! warning "Do not start ImSwitch yet"
    Install the plugin (**Step 5**) first — every requirement has to be in place
    before the first start. ImSwitch creates its configuration folder on that
    first start; create it now so the setup file from Step 4 can already be
    placed:

    ```bash
    mkdir -p ~/Documents/ImSwitchConfig/imcontrol_setups
    ```

```
Documents/
└── ImSwitchConfig/
    ├── imcontrol_setups/     ← the setup JSON goes here (Step 4)
    ├── imcontrol_options/
    └── ...
```

!!! tip "Ready-made configurations"
    The [openUC2/ImSwitchConfig](https://github.com/openUC2/ImSwitchConfig)
    repository contains further example setups. You can clone it into the
    `ImSwitchConfig` folder and drop the file from Step 4 in next to the others.

---

## Step 4 — Add the camera setup JSON to `imcontrol_setups`

The setup file for this imager lives in the repository at
[`Json+cam_manager/example_uc2_ddorf_hik_imager_IR.json`](https://github.com/s1alknau/Nematostella-time-series/blob/Nematostella-time-series-IR/Json%2Bcam_manager/example_uc2_ddorf_hik_imager_IR.json):

```json
{
  "rs232devices": {
    "ESP32": {
      "managerName": "ESP32Manager",
      "managerProperties": {
        "host_": "192.168.43.129",
        "serialport": "COM4",
        "debug": 0,
        "baudrate": 115200
      }
    }
  },
  "detectors": {
    "WidefieldCamera": {
      "managerName": "HikCamManager",
      "managerProperties": {
        "isRGB": false,
        "cameraListIndex": 0,
        "cameraEffPixelsize": 3.45,
        "hikcam": {
          "exposure": 50.0,
          "gain": 0.0,
          "blacklevel": 0,
          "trigger_source": "Continous",
          "exposure_mode": "manual",
          "frame_rate": 30
        }
      },
      "forAcquisition": true
    }
  },
  "availableWidgets": ["Settings", "View", "Recording", "Image"]
}
```

Copy it into the setups folder:

=== "Windows"

    ```powershell
    copy "Json+cam_manager\example_uc2_ddorf_hik_imager_IR.json" "$env:USERPROFILE\Documents\ImSwitchConfig\imcontrol_setups\"
    ```

=== "macOS / Linux"

    ```bash
    cp "Json+cam_manager/example_uc2_ddorf_hik_imager_IR.json" \
      ~/Documents/ImSwitchConfig/imcontrol_setups/
    ```

Then select it in ImSwitch as the active setup (*Settings → setup file*) and
restart ImSwitch so the setup is loaded.

### What the fields mean

| Field | Meaning |
| --- | --- |
| `detectors.WidefieldCamera.managerName` | `HikCamManager` — the MVS-SDK-backed detector. The napari layer that shows up later is named after this detector. |
| `cameraListIndex` | Index into the list of detected HIK cameras. `0` is correct for a single camera; increase it if several are attached. |
| `cameraEffPixelsize` | Effective pixel size in µm (3.45 µm for the MV-CS013), used for scale bars. |
| `isRGB` | `false` — the NIR sensor is monochrome. |
| `hikcam.exposure` | Exposure in **ms**. The plugin reads the live value back from ImSwitch, so set exposure in ImSwitch, not in the plugin. |
| `hikcam.gain` / `blacklevel` | Keep at `0` for calibrated recordings — LED calibration assumes a fixed camera response. |
| `hikcam.trigger_source` | `Continous` (free-running). LED/exposure synchronization is done by the ESP32 sync pulse, not by a hardware camera trigger. |
| `hikcam.exposure_mode` | `manual` — auto exposure would defeat the brightness validation during recording. |
| `rs232devices.ESP32.serialport` | Serial port of the ESP32 — `COMx` on Windows, `/dev/ttyUSB0` on Linux. |
| `rs232devices.ESP32.baudrate` | `115200`, matching the project firmware. |
| `availableWidgets` | Which ImSwitch panels are shown. `Settings`, `View`, `Recording` and `Image` are enough for this workflow. |

!!! warning "Only one process can hold the ESP32 serial port"
    The plugin opens the ESP32 port itself, and serial ports are exclusive: if
    ImSwitch's `ESP32` rs232 device already holds `COM4`, the plugin's
    **Connect** fails (and vice versa). If you drive the ESP32 exclusively from
    the plugin — the normal case for this workflow — either point ImSwitch's
    `serialport` at an unused port or remove the `rs232devices` block from your
    copy of the setup file. Also close any serial monitor (Arduino IDE, PuTTY)
    before connecting.

---

## Step 5 — Install the recording plugin and its requirements

!!! warning "Before the first ImSwitch start"
    Do this step **before** starting ImSwitch for the first time. The plugin
    brings `qtpy` and `napari` in as dependencies, so a missing step here is the
    usual cause of the `No module named 'qtpy'` crash in
    [Step 3](#choose-a-qt-binding-and-install-the-gui-stack).

The plugin is **not published on PyPI** - install it from source:

```bash
conda activate imswitch21
git clone https://github.com/s1alknau/Nematostella-time-series.git
cd Nematostella-time-series
pip install -e .
```

Optional extras:

```bash
pip install -e ".[opencv]"   # Live Analysis tab (HoughCircles ROI detection)
```

`zarr` (Zarr recording format, read-while-write live analysis) is already part
of the core dependencies. Verify the install:

```bash
python -c "import timeseries_capture, napari; print('ok')"
```

---

## Step 6 — First launch

1. Activate the environment and start ImSwitch:

    ```bash
    conda activate imswitch21
    imswitch
    ```

2. Load the `example_uc2_ddorf_hik_imager_IR` setup.
3. Start the **live view** — a napari layer with the camera image appears
   (`Live: WidefieldCamera` or similar). The plugin auto-detects layers whose
   name contains `Live:`, `Widefield`, `Camera` or `Detector`.
4. Open *Plugins → Nematostella Timelapse Recording* in the napari viewer.
5. In the **ESP32 Connection** tab, click **Connect** — the status turns green.
6. Run an **LED calibration** before the first recording; for light/dark
   experiments follow the [Circadian Protocol](circadian.md).
7. Configure duration, interval and output folder, then start the recording.

!!! note "Without a HIK camera"
    Steps 2–4 are only needed for the ImSwitch/HIK GigE path. The plugin also
    runs in a plain `napari` session with the other supported camera adapters —
    only the ESP32 is mandatory.

### Optional: multi-camera configuration

If a `camera_system.json` is present, the plugin adds its multi-camera panels on
startup. It is searched for in this order:

1. `camera_system.json` in the current working directory
2. `~/.imswitch/camera_system.json`
3. `camera_system.json` next to the installed package

Use [`camera_system_example.json`](https://github.com/s1alknau/Nematostella-time-series/blob/Nematostella-time-series-IR/camera_system_example.json)
as a template — it lists per-camera IP, ESP32 port and the default recording
configuration. Without such a file the plugin runs in single-camera mode.

---

## Troubleshooting

| Message / symptom | Cause and fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'qtpy'` while starting ImSwitch | The GUI stack is missing — `pip install -e .` installs no Qt packages. Install the binding **and** `qtpy napari pyqtgraph qdarkstyle`, see [Step 3](#choose-a-qt-binding-and-install-the-gui-stack). |
| `ModuleNotFoundError` for `napari`, `pyqtgraph` or `qdarkstyle` | Same cause, same fix — or simply run Step 5 (the plugin pulls `qtpy` and `napari` in) before starting ImSwitch. |
| `Fatal Python error: Segmentation fault` in `launchApp` | QtWebEngine without a shared GL context — fixed in `nematostella-rig`, `git pull` the ImSwitch clone. See [Segfault when the GUI starts](#segfault-when-the-gui-starts-linux-pyside6). |
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` (Linux) | Missing system libraries or no display — see the note in [Step 3](#choose-a-qt-binding-and-install-the-gui-stack). |
| Plugin missing in the *Plugins* menu | Installed into a different environment. `conda activate imswitch21`, reinstall, restart napari/ImSwitch. |
| `No camera layer found (ensure live view is started in ImSwitch)` | The live view is not running, or the layer name contains none of `Live:`, `Widefield`, `Camera`, `Detector`. Start the live view or rename the layer. |
| `Zero frame from napari layer (n consecutive)` | The HIK acquisition buffer is in an inconsistent state. The plugin flushes the ImSwitch detector buffer automatically after 5 consecutive zero frames; if it keeps recurring, check MTU/cabling and restart the live view. |
| Camera missing in ImSwitch but visible in MVS | Wrong `cameraListIndex`, or the MVS client still holds the camera — close it, only one application can open a GigE camera at a time. |
| Camera missing in MVS as well | Subnet or firewall problem — see the table in [Step 2](#verify-the-camera-before-touching-imswitch). |
| ESP32 **Connect** fails, port busy | Another process holds the port (ImSwitch rs232 device, serial monitor) — see the warning in [Step 4](#what-the-fields-mean). |
| Exposure in the plugin looks wrong | The plugin reads the exposure back from ImSwitch in ms; change it in ImSwitch's settings, not in the plugin. |
| Frames too dark or too bright | Run an LED calibration and keep `gain` and `blacklevel` at `0` so the calibration stays valid. |

### Segfault when the GUI starts (Linux, PySide6)

ImSwitch loads, the window appears for a moment, then the process dies without a
Python exception:

```
Fatal Python error: Segmentation fault

Current thread (most recent call first):
  File ".../qtpy/_utils.py", line 53 in possibly_static_exec
  File ".../imswitch/imcommon/applaunch.py", line 169 in launchApp
Extension modules: ... PySide6.QtWebEngineCore, PySide6.QtWebEngineWidgets ...
```

**Fixed in the fork — update your clone.** QtWebEngine requires
`Qt.AA_ShareOpenGLContexts`, and the attribute only takes effect while no
`QApplication` exists yet. It used to sit in a `PyQt5`/`PySide2`-only block,
while `imnotebook` — which pulls `QtWebEngineWidgets` in — is imported *after*
the application object is created. On Qt 6 the web engine then came up without a
shared GL context and took the process down as soon as `app.exec_()` ran.
`nematostella-rig` now sets the attribute for every binding
([patch `0003`](https://github.com/s1alknau/Nematostella-time-series/blob/Nematostella-time-series-IR/imswitch-patches/0003-AA_ShareOpenGLContexts-auch-unter-Qt-6-setzen.patch)):

```bash
cd ImSwitch
git pull
```

If the clone was installed with `pip install .` instead of `pip install -e .`,
reinstall afterwards — a plain install copies the code into `site-packages` and
does not follow the clone:

```bash
pip install -e .
```

!!! tip "Workaround without updating"
    The rig does not need the Jupyter notebook module, and without it QtWebEngine
    is never imported. Set `~/Documents/ImSwitchConfig/config/modules.json` to:

    ```json
    {
        "enabled": ["imcontrol"]
    }
    ```

    The default is `["imcontrol", "imscripting", "imnotebook"]`; `imscripting` is
    dropped by ImSwitch at startup anyway.

If it still segfaults, the display stack is the next suspect:

```bash
echo $XDG_SESSION_TYPE              # "wayland" is worth ruling out
QT_QPA_PLATFORM=xcb imswitch        # force X11 instead of Wayland
LIBGL_ALWAYS_SOFTWARE=1 imswitch    # software OpenGL (napari/vispy on old iGPUs)
```

Whichever of the two makes the crash go away identifies the cause: the first
points at the Wayland platform plugin, the second at the OpenGL driver.
