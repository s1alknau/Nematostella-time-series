---
layout: single
title:  "Nematostella Imager"
date:   2026-06-10
author: Alexander Knauss
author_profile: true
---

<table>
  <tr>
    <td width="75%" valign="top">
      <p>The sea anemone <em>Nematostella vectensis</em> possesses conserved clock genes, displays light-entrained circadian locomotor rhythms, and exhibits sleep-like states linked to DNA repair, making it a key model for circadian regulation and sleep evolution. However, no existing platform integrates the timing precision, illumination control for scheduled experimental design, and automated behavioral analysis required for long-term studies.</p>
      <p>We developed an open-source hardware&ndash;software system built around an ESP32 microcontroller-based imaging unit, providing near-infrared and white-light illumination for entrainment, sub-second timing accuracy, and environmental logging at a total cost of ~600&nbsp;&euro;. Two companion napari plugins then automate the full workflow &mdash; from region-of-interest detection and movement quantification through circadian rhythm analysis to sleep-like state classification.</p>
      <h2>Software</h2>
      <ul>
        <li><b>Recording plugin</b> &mdash; <a href="https://github.com/s1alknau/Nematostella-time-series">Nematostella-time-series</a>: synchronized timelapse capture, LED control, ESP32 communication.</li>
        <li><b>Analysis plugin</b> &mdash; <a href="https://github.com/s1alknau/napari-hdf5-activity">napari-hdf5-activity</a>: ROI-based activity extraction and circadian analysis (Chi&sup2; periodogram, FFT, Cosinor, phase clustering).</li>
        <li><b>Web firmware installer</b> &mdash; <a href="https://s1alknau.github.io/Nematostella-time-series/">flash ESP32 firmware from the browser</a> (Chrome/Edge, no toolchain required).</li>
      </ul>
    </td>
    <td width="25%" valign="top" align="center">
      <img src="https://raw.githubusercontent.com/s1alknau/Nematostella-time-series/Nematostella-time-series-IR/docs/images/Nematostella.png" alt="Nematostella vectensis" width="180" />
      <br/>
      <em>An adult</em> Nematostella vectensis.</em>
    </td>
  </tr>
</table>

## Hardware

<p align="center"><img src="https://raw.githubusercontent.com/s1alknau/Nematostella-time-series/Nematostella-time-series-IR/docs/images/Setup.jpg" alt="Imager setup" width="380" /></p>

<p align="center"><em>The assembled imaging chamber: HIK robotics monochrome camera, exchangeable LED lid (IR or white), ESP32 controller and DHT22 temperature sensor.</em></p>

## Recording

<p align="center"><img src="https://raw.githubusercontent.com/s1alknau/Nematostella-time-series/Nematostella-time-series-IR/docs/images/Nematostella_Activity_LD_cycle.png" alt="Activity traces of four Nematostella vectensis under a 12 : 12 LD cycle" width="480" /></p>

<p align="center"><em>Top: snapshot of the 6-well imaging plate with auto-detected ROIs (1&ndash;6). Bottom: corresponding activity signals of the four</em> Nematostella vectensis <em>animals across the 12 : 12 light / dark phases. Activity is the mean absolute per-pixel frame-to-frame difference (MinMax-normalized) within each animal's ROI.</em></p>

---

## Entrainment protocol

*Nematostella vectensis* (or comparable organisms)

!!! info "Protocol metadata"
    **Version:** 1.1 · **Date:** 2026-08-28 · **Plugin:** `napari-hdf5-activity`

This protocol complements the [Circadian Analysis](analysis/circadian-analysis.md) guide:
it describes the *experimental design* (light/dark scheduling) that produces the
recordings analyzed there.

### 1. Scientific background

**Goal:** demonstrate that the animal's endogenous biological clock can be
synchronized (*entrained*) by an external light–dark (LD) cycle acting as a
*Zeitgeber* (time giver).

**Entrainment** means the rhythm is phase-shifted to align with the Zeitgeber and
*persists* in constant conditions (DD) at the new phase — which is why the DD
phase after the LD exposure is the one that carries the evidence.

**Key terminology**

| Term | Meaning |
|------|---------|
| tau (τ) | intrinsic **free-running** period — defined in constant conditions, so it is read from the DD phases only |
| Dominant period | strongest peak of the Chi² periodogram in a given segment. In DD it *is* τ; under LD it is the entrained period the animals actually express, and that is the number reported as their circadian cycle |
| ZT | Zeitgeber Time (ZT0 = lights ON) |
| CT | Circadian Time (CT0 = subjective lights ON in DD) |
| LD 12:12 | 12 h light / 12 h dark |
| DD | constant darkness |
| LL | constant light |
| Acrophase | time of peak activity relative to ZT0 |
| Transient | cycles of gradual phase adjustment after LD onset |

### 2. Full protocol — overview

Every phase is recorded over **three days** (72 h) — three full cycles per
condition:

| Phase | Condition | Purpose | Duration |
|-------|-----------|---------|----------|
| 1 | DD | Free-run (τ determination) | 3 days |
| 2 | LD 12:12 | Entrainment | 3 days |
| 3 | DD | Free-run after entrainment | 3 days |
| **Total** | | | **9 days** |

!!! note "Three cycles is the floor for the Chi² periodogram"
    The periodogram needs at least three cycles of the period it is asked to
    find; a 72 h recording is exactly that for a ~24 h rhythm. Peaks stay
    broader than they would be over a longer run, and the Cosinor amplitude is
    less well constrained — read the numbers with that in mind.

### 3. Phase 1 — DD (free-run, τ determination)

**Duration:** 3 days

**Conditions**

- Light: no white light; IR illumination only (for imaging)
- Temperature: constant ± 0.5 °C

**Recording setup**

- Frame rate: 1 frame every 5 s (default)
- White LED: OFF (0 %) · IR LED: ON (for imaging)
- File naming: `animal01_phase1_DD.hdf5`

**Expected results**

- Activity pattern drifts slowly (typical τ: 20–28 h)
- Chi² periodogram: sharp peak at τ ≠ 24 h
- No stable phase relationship to external time

**Plugin settings (Phase 1)**

- Adaptive Illumination Baseline: OFF (no LD transitions)
- Detrending: OFF
- Chi² period range: **Circadian (20–28 h)** preset, or 12–36 h when you want
  the wider window
- Data source: Fraction Movement **or** Raw Intensity
- → Read off `tau_1` from the periodogram peak

### 4. Phase 2 — LD 12:12 (entrainment)

**Duration:** 3 days

**Conditions**

- Lights ON: ZT0 — choose a fixed clock time and keep it consistent across all experiments
- Lights OFF: ZT12 (12 h after ZT0)
- Intensity: consistent across all days (same LED power %)
- Temperature: still constant

!!! note "Start of LD exposure"
    - Animals were previously in DD (no prior light).
    - ZT0 = the very first light exposure = recording start.
    - The first cycles are **transient** — the clock is still shifting toward the
      new phase. Over a 3-day phase the transients are part of the recording, so
      read the Cosinor acrophase as an estimate that still carries the shift,
      and compare it against the acrophase at the end of the phase.
    - Document the exact clock time of ZT0.

**Recording setup**

- White LED: ON during light phase (e.g. 50–100 %) · IR LED: ON continuously
- File naming: `animal01_phase2_LD12_12.hdf5`

**Expected results**

- Dominant period converges toward 24 h as the transients fade
- Stable acrophase relative to ZT
- Nocturnal animals: activity peak in dark phase (ZT12–ZT24)
- Diurnal animals: activity peak in light phase (ZT0–ZT12)

!!! warning "This is not τ"
    Under LD the animals are driven by the Zeitgeber, so the periodogram peak is
    the **dominant period** of entrained animals — the circadian cycle they
    express under the light regime. τ stays reserved for the DD phases, where
    nothing external sets the pace.

**Plugin settings (Phase 2)**

- Adaptive Illumination Baseline: ON (compensates baseline difference between light and dark)
- Chi² period range: **Circadian (20–28 h)** preset, or 12–36 h when you want
  the wider window (check for boundary warnings ⚠️)
- ZT mode: ON in plots → X-axis in Zeitgeber Time
- Time Range: Full Recording — all three cycles
- Chi² on Full Recording → shows the period transition

**Acrophase calculation**

- If recording started at ZT0: Peak Time = Acrophase directly.
- If recording started at ZT_offset: `Acrophase (ZT) = (Peak Time + ZT_offset) mod 24`.

### 5. Phase 3 — DD after entrainment

**Duration:** 3 days · Light OFF again (IR only); all other conditions identical to Phase 1.
File naming: `animal01_phase3_DD_post.hdf5`.

This is the **critical phase** — it determines whether true entrainment occurred:

- **(a)** Rhythm continues at ~24 h with the same acrophase as the end of Phase 2 → **genuine entrainment confirmed**.
- **(b)** Period returns to original `tau_1` → the clock was not permanently re-set.
- **(c)** Period returns to `tau_1` but with a shifted acrophase → partial phase response.
- **(d)** Arrhythmic in DD → LD may have suppressed or damaged clock function (rare).

**Plugin settings (Phase 3)**

- Identical to Phase 1 (DD, no Adaptive Baseline)
- Chi² on Full Recording → read off `tau_2`
- Compare `tau_1` (Phase 1) vs. `tau_2` (Phase 3); compare acrophase CT (Phase 3) vs. ZT (Phase 2)

### 6. Analysis workflow — segment by segment

!!! note "Fit each phase separately"
    A Cosinor assumes a single constant period, so fit DD and LD segments
    separately — never across a condition change.

**Recommended analysis plan**

- **Phase 1 (DD):** Chi² full → `tau_1`; Cosinor full (3 days) → `tau_1`, R², amplitude baseline.
- **Phase 2 (LD):** Chi² full → **dominant period** (the entrained circadian cycle, expected near 24 h — not τ); Cosinor full → Acrophase (ZT), amplitude under LD. The Z-score includes the transients.
- **Phase 3 (DD):** Chi² full → `tau_2`; Cosinor full → `tau_2`, compare amplitude to Phase 1.

**Summary table (fill in per animal)**

| Animal | tau_1 (h, DD) | Dominant period LD (h) | Acrophase ZT (h) | tau_2 (h, DD) | Entrained? |
|--------|---------------|------------------------|------------------|---------------|------------|
| 01 | | | | | |
| 02 | | | | | |

### 7. Controls

**Negative control (empty well)** — include wells with no animal in each recording; should show no significant rhythm (the plugin auto-detects inactive ROIs).

**Positive control (stable LD throughout)** — animals kept under LD 12:12 for the entire experiment; should show a stable 24 h period and consistent acrophase, confirming the LD cycle works.

**Technical controls**

- Verify no temperature cycle in the incubator (log temperature).
- Verify no mechanical vibrations at fixed times.
- Confirm LED power is identical between light phases.

### 8. Data management

```
experiment_YYYY-MM-DD/
  phase1_DD/
    animal01_phase1_DD.hdf5
    animal02_phase1_DD.hdf5
  phase2_LD/
    animal01_phase2_LD12_12.hdf5
  phase3_DD_post/
    animal01_phase3_DD_post.hdf5
  notes.txt   # manual log of any deviations
```

**Metadata to document per file**

- Animal ID, age, origin, housing conditions
- Recording start: clock time **and** ZT value; ZT0: clock time of lights-on
- Frame rate and image resolution
- Temperature (mean ± SD); LED power (%)

### 9. Expected outcomes and interpretation

- **Scenario A — full entrainment (ideal):** `tau_1` ≠ 24 h → dominant period ≈ 24 h with a stable acrophase in LD → `tau_2` ≈ `tau_1`. The animal has a genuine free-running clock that phase-locks to the LD cycle and returns to its own τ in DD.
- **Scenario B — no entrainment:** `tau_1` ≠ 24 h → dominant period stays off 24 h and no stable acrophase in LD → `tau_2` ≈ `tau_1`. LD has no synchronizing effect; check light intensity and conditions.
- **Scenario C — phase shift (entrainment in progress):** `tau_2` ≈ `tau_1` but acrophase is shifted relative to `tau_1`. LD caused a permanent phase shift; the phase angle ψ (acrophase ZT relative to ZT0) describes the new clock–environment relationship.

### 10. Plugin settings cheat sheet

**Phase 1 & 3 (DD)**

| Setting | Value |
|---------|-------|
| Adaptive Illumination Baseline | OFF |
| Jump Correction | OFF (unless hardware artefacts) |
| Detrending | OFF |
| Period range | **Circadian (20–28 h)** preset, or 12–36 h |
| Data source | Raw Intensity or Fraction Movement |
| Time Range | Full Recording (3 days) |
| Cosinor period | fix to estimated τ (e.g. 21 h) |

**Phase 2 (LD)**

| Setting | Value |
|---------|-------|
| Adaptive Illumination Baseline | ON |
| Jump Correction | OFF |
| Detrending | OFF |
| Period range | **Circadian (20–28 h)** preset, or 12–36 h |
| Data source | Raw Intensity (Cosinor) / Fraction Movement (Chi²) |
| Time Range | Full Recording (3 days) |
| ZT mode | ON |

### 11. References

- Pittendrigh, C. S., & Daan, S. (1976). A functional analysis of circadian pacemakers in nocturnal rodents. *J. Comp. Physiol.*, 106, 223–252.
- Aschoff, J. (1965). *Circadian Clocks.* North-Holland Publishing.
- Sokolove, P. G., & Bushell, W. N. (1978). The chi square periodogram: its application to the analysis of circadian rhythms. *J. Theor. Biol.*, 72(1), 131–160.
- Nelson, W., et al. (1979). Methods for cosinor rhythmometry. *Chronobiologia*, 6(4), 305–323.
- Hendricks, J. C., et al. (2000). Rest in Drosophila is a sleep-like state. *Neuron*, 25, 129–138.
