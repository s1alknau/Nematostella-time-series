# MkDocs-Website – Einrichtung & Betrieb

Diese Doku-Website wird mit [MkDocs](https://www.mkdocs.org/) +
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) gebaut und
deckt **beide** Plugins ab:

- **Recording Plugin** – dieses Repo (`Nematostella-time-series`)
- **Analysis Plugin** – `napari-hdf5-activity` (wird beim Build automatisch mitgezogen)

## Wie es aufgebaut ist

- `mkdocs.yml` – Konfiguration (Theme, Navigation, Extensions).
- `docs/` – Quellordner der Website. Enthält bereits `installer.html`
  (Firmware-Installer), `firmware/`, `images/`, `3D_Druck/`. Diese werden 1:1
  in die Website kopiert – der Installer funktioniert also weiter, jetzt unter
  `…/installer.html` (vorher unter der Root-URL).
- `docs/index.md` – Startseite. `docs/analysis/index.md` – Startseite des
  Analyse-Abschnitts.
- `scripts/sync_docs.py` – kopiert Markdown-Dateien in den `docs/`-Ordner, die
  woanders liegen (Changelog, Circadian-Doku, sowie die Doku des Analyse-Repos).
  Diese Kopien sind in `.gitignore` und werden **nicht** committet – die
  Originale bleiben die einzige Quelle.
- `.github/workflows/deploy_docs.yml` – baut die Website bei jedem Push und
  veröffentlicht sie auf dem `gh-pages`-Branch.

## Lokal ansehen

```bash
pip install -r requirements-docs.txt
python scripts/sync_docs.py      # zieht Changelog + Analyse-Doku in docs/
mkdocs serve                     # http://127.0.0.1:8000
```

`sync_docs.py` erwartet das Analyse-Repo als Nachbarordner
(`../napari-hdf5-activity`) oder über die Umgebungsvariable `ANALYSIS_REPO`.
Fehlt es, wird nur das Recording-Plugin gebaut (mit Warnung).

## Veröffentlichen (einmalig einrichten)

1. Änderungen committen und pushen (Branch `Nematostella-time-series-IR`).
   Der Workflow läuft automatisch und schiebt die gebaute Seite nach `gh-pages`.
   Manuell auslösen: Actions → *Deploy MkDocs site* → *Run workflow*.
2. **GitHub Pages umstellen:** Repo → *Settings* → *Pages* →
   *Build and deployment* → *Source* auf **Deploy from a branch**, Branch
   **`gh-pages`** / `/ (root)`. (Bisher stand dort der `docs/`-Ordner – das ist
   der einzige manuelle Schritt.)
3. Nach ~1 Minute ist die Seite unter
   <https://s1alknau.github.io/Nematostella-time-series/> live.

## Wichtige Hinweise

- **Installer-URL geändert:** von `…/Nematostella-time-series/` zu
  `…/Nematostella-time-series/installer.html`. Verweise in `README.md` wurden
  bereits angepasst.
- **Analyse-Doku aktualisieren:** Änderungen im Repo `napari-hdf5-activity`
  erscheinen erst, wenn der Deploy-Workflow hier erneut läuft
  (Push in dieses Repo oder *Run workflow* manuell). Optional lässt sich im
  Analyse-Repo ein `repository_dispatch` einrichten, der diesen Workflow triggert.
- **Firmware & STL-Previews:** Die bestehenden Workflows `firmware_build.yml`
  und `render_stl_previews.yml` schreiben nach `docs/…`; deren Pushes lösen den
  Doku-Deploy automatisch mit aus.
- **Material-Lizenzhinweis:** Neuere Material-Versionen zeigen beim Build einen
  Hinweis auf die kommende 2.0-Lizenz. Die hier gepinnte 9.x-Linie ist
  MIT-lizenziert und frei nutzbar.
