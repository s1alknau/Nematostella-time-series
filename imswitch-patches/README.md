# Welches ImSwitch dieses Plugin braucht

`napari-timelapse-capture` und `napari-lsft` laufen **nicht** mit ImSwitch aus
der Vorlage `openUC2/ImSwitch`. Nötig ist der Fork mit dem Branch
`nematostella-rig`.

## Der Weg: Fork klonen

```bash
git clone -b nematostella-rig https://github.com/s1alknau/ImSwitch.git
cd ImSwitch
pip install -e .
```

Ohne `[PyQt5]`, wenn du Qt 6 willst — siehe unten.

| | |
|---|---|
| Fork | `s1alknau/ImSwitch` |
| Branch | **`nematostella-rig`** (Standard-Branch des Forks) |
| Basis | `openUC2/ImSwitch` @ `8b424d51` |
| Commits darüber | 3 |

## Warum die Vorlage nicht reicht

**Der Qt-Modus startet gar nicht.** Signale werden in `CheckUpdatesThread` und
zwei View-Klassen im `__init__` zugewiesen. `pyqtSignal` wird aber nur als
*Klassen*-Attribut gebunden; als Instanz-Attribut fehlt `.connect`:

    AttributeError: 'PyQt5.QtCore.pyqtSignal' object has no attribute 'connect'

**Unter Windows fehlt `fcntl`.** `imcontrol/model/io/session.py` importiert es
unbedingt; der Branch stellt einen `msvcrt`-Ersatz bereit.

**`setLaserGalvo()` fehlt.** `napari-lsft` braucht diesen `APIExport`, um den
Lichtblatt-Galvo zum Messbeginn zu setzen, während er per Holo-Widget bedienbar
bleibt.

**Die Metaklasse ist unvollständig.** Die sip/Shiboken-Metaklasse ruft
`ABCMeta.__new__` nicht auf, `_abc_impl` fehlt daher und `issubclass()` liefert
falsche Ergebnisse.

**Unter Qt 6 stürzt der Start ab.** `AA_ShareOpenGLContexts` stand im Block für
PyQt5/PySide2. QtWebEngine — nachgezogen von `imnotebook`, das `__main__` erst
nach `prepareApp()` importiert — braucht das Attribut aber in jeder Qt-Version,
und es wirkt nur vor dem `QApplication`-Konstruktor. Unter PySide6 starb der
Prozess dadurch beim Start der Event-Loop:

    Fatal Python error: Segmentation fault
      File ".../imswitch/imcommon/applaunch.py", line 169 in launchApp

## Qt 5 oder Qt 6

Der zweite Commit macht die Wahl frei — vorher war PyQt5 fest verdrahtet.

| | Qt-Version | Anzeige |
|---|---|---|
| `pip install -e ".[PyQt5]"` | 5.15.2 | **geschert** auf Rechnern mit zwei GPUs |
| `pip install -e .` + `pip install "PySide6==6.8.*"` | 6.8.3 | sauber |

PyQt5 liefert über PyPI unter Windows nur Qt 5.15.2 (Stand 2020); neuere
Wheels gibt es dort nicht. Diese Version stellt die Client-Fläche auf
Hybrid-GPU-Systemen geschert dar — mit Qt 6.8 tritt das nicht auf.

Bei PySide6 zusätzlich beachten: PyQt5 muss **vollständig** entfernt werden,
auch ein leergeräumter `site-packages/PyQt5`-Ordner. `pyqtgraph` erkennt ihn
sonst als vorhandenes Paket und wählt das falsche Binding.

## Die Patch-Dateien

`0001-*.patch` bis `0003-*.patch` sind die Rückfallebene, falls der Fork einmal
nicht erreichbar ist:

```bash
git clone https://github.com/openUC2/ImSwitch.git
cd ImSwitch
git checkout -b nematostella-rig 8b424d51
git am ../Nematostella-time-series/imswitch-patches/000*.patch
```

Patches veralten, sobald sich die Vorlage bewegt. Der Fork ist der Weg, über
den sich Upstream nachziehen lässt — und über den `setLaserGalvo()` irgendwann
als Pull Request nach oben wandern kann.
