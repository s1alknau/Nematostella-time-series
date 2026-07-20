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
    **Version:** 1.0 · **Date:** 2026-03-10 · **Plugin:** `napari-hdf5-activity`

This protocol complements the [Circadian Analysis](analysis/circadian-analysis.md) guide:
it describes the *experimental design* (light/dark scheduling) that produces the
recordings analyzed there.

### 1. Scientific background

**Goal:** demonstrate that the animal's endogenous biological clock can be
synchronized (*entrained*) by an external light–dark (LD) cycle acting as a
*Zeitgeber* (time giver).

**Entrainment vs. masking**

- **Masking** — the animal responds directly and acutely to light. It
  disappears as soon as light is removed. This is *not* a true clock effect.
- **Entrainment** — the rhythm is phase-shifted to align with the Zeitgeber and
  *persists* in constant conditions (DD) at the new phase.

!!! warning "Only a DD phase AFTER LD exposure can distinguish the two."

**Key terminology**

| Term | Meaning |
|------|---------|
| tau (τ) | intrinsic (free-running) period measured in DD |
| ZT | Zeitgeber Time (ZT0 = lights ON) |
| CT | Circadian Time (CT0 = subjective lights ON in DD) |
| LD 12:12 | 12 h light / 12 h dark |
| DD | constant darkness |
| LL | constant light |
| Acrophase | time of peak activity relative to ZT0 |
| Transient | cycles of gradual phase adjustment after LD onset |

### 2. Full protocol — overview

| Phase | Condition | Purpose | Duration |
|-------|-----------|---------|----------|
| 1 | DD | Free-run (τ determination) | 5–7 days |
| 2 | LD 12:12 | Entrainment | 7 days |
| 3 | DD | Free-run after entrainment | 5–7 days |
| **Total** | | | **≈ 17–21 days** |

Optional extensions:

| Phase | Condition | Purpose | Duration |
|-------|-----------|---------|----------|
| 4 | Phase-response test (single light pulse) | | 2 days |
| 5 | LL | Free-run under constant light | 5 days |

### 3. Phase 1 — DD (free-run, τ determination)

**Duration:** 5–7 days

**Conditions**

- Light: no white light; IR illumination only (for imaging, if required)
- Temperature: constant ± 0.5 °C
- Feeding: daily at a fixed time **or** suspended (feeding is itself a Zeitgeber)

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
- Chi² period range: 16–36 h
- Data source: Fraction Movement **or** Raw Intensity
- → Read off `tau_1` from the periodogram peak

### 4. Phase 2 — LD 12:12 (entrainment)

**Duration:** 7 days (minimum 5; 10 preferred)

**Conditions**

- Lights ON: ZT0 — choose a fixed clock time and keep it consistent across all experiments
- Lights OFF: ZT12 (12 h after ZT0)
- Intensity: consistent across all days (same LED power %)
- Temperature: still constant

!!! note "Start of LD exposure"
    - Animals were previously in DD (no prior light).
    - ZT0 = the very first light exposure = recording start.
    - The first 2–3 cycles are **transient** — the clock is still shifting toward
      the new phase; do not use these cycles alone for Cosinor fitting.
    - Document the exact clock time of ZT0.

**Recording setup**

- White LED: ON during light phase (e.g. 50–100 %) · IR LED: ON continuously
- File naming: `animal01_phase2_LD12_12.hdf5`

**Expected results**

- After 2–3 transient cycles: period converges to 24.0 h
- Stable acrophase relative to ZT
- Nocturnal animals: activity peak in dark phase (ZT12–ZT24)
- Diurnal animals: activity peak in light phase (ZT0–ZT12)

**Plugin settings (Phase 2)**

- Adaptive Illumination Baseline: ON (compensates baseline difference between light and dark)
- Chi² period range: 16–36 h (check for boundary warnings ⚠️)
- ZT mode: ON in plots → X-axis in Zeitgeber Time
- Time Range for Cosinor: day 4–7 only (stable phase) → Start: 72 h, End: 168 h
- Chi² on Full Recording → shows the period transition

**Acrophase calculation**

- If recording started at ZT0: Peak Time = Acrophase directly.
- If recording started at ZT_offset: `Acrophase (ZT) = (Peak Time + ZT_offset) mod 24`.

### 5. Phase 3 — DD after entrainment

**Duration:** 5–7 days · Light OFF again (IR only); all other conditions identical to Phase 1.
File naming: `animal01_phase3_DD_post.hdf5`.

This is the **critical phase** — it determines whether true entrainment occurred:

- **(a)** Rhythm continues at ~24 h with the same acrophase as the end of Phase 2 → **genuine entrainment confirmed**.
- **(b)** Period returns to original `tau_1` → clock was not permanently re-set; masking likely.
- **(c)** Period returns to `tau_1` but with a shifted acrophase → partial phase response.
- **(d)** Arrhythmic in DD → LD may have suppressed or damaged clock function (rare).

**Plugin settings (Phase 3)**

- Identical to Phase 1 (DD, no Adaptive Baseline)
- Chi² on Full Recording → read off `tau_2`
- Compare `tau_1` (Phase 1) vs. `tau_2` (Phase 3); compare acrophase CT (Phase 3) vs. ZT (Phase 2)

### 6. Analysis workflow — segment by segment

!!! danger "Do not analyze transient + stable data in a single Cosinor fit."
    A Cosinor assumes a single constant period; mixed data degrades R² and blurs
    the acrophase estimate.

**Recommended analysis plan**

- **Phase 1 (DD):** Chi² full → `tau_1`; Cosinor full (7+ days) → `tau_1`, R², amplitude baseline.
- **Phase 2 (LD) — full recording Chi²:** shows period convergence from `tau_1` toward 24 h (overview only; Z-score includes transients).
- **Phase 2 (LD) — stable segment (day 4–7):** Chi² → confirms ~24 h; Cosinor → Acrophase (ZT), amplitude under LD.
- **Phase 3 (DD):** Chi² full → `tau_2`; Cosinor full → `tau_2`, compare amplitude to Phase 1.

**Summary table (fill in per animal)**

| Animal | tau_1 (h) | Acrophase ZT (h) | tau_2 (h) | Entrained? |
|--------|-----------|------------------|-----------|------------|
| 01 | | | | |
| 02 | | | | |

### 7. Controls

**Negative control (empty well)** — include wells with no animal in each recording; should show no significant rhythm (the plugin auto-detects inactive ROIs).

**Positive control (stable LD throughout)** — animals kept under LD 12:12 for the entire experiment; should show a stable 24 h period and consistent acrophase, confirming the LD cycle works.

**Technical controls**

- Verify no temperature cycle in the incubator (log temperature).
- Verify no mechanical vibrations at fixed times.
- Document all feeding times (potential Zeitgeber).
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

- **Scenario A — full entrainment (ideal):** `tau_1` ≠ 24 h → stable acrophase in LD → `tau_2` ≈ `tau_1`. The animal has a genuine free-running clock that phase-locks to the LD cycle and returns to its own τ in DD.
- **Scenario B — no entrainment:** `tau_1` ≠ 24 h → no stable acrophase in LD → `tau_2` ≈ `tau_1`. LD has no synchronizing effect; check light intensity and conditions.
- **Scenario C — masking only:** period ≈ 24 h in Phase 2, but `tau_2` reverts to `tau_1` in Phase 3. The animal responds acutely to light but the clock is not re-entrained.
- **Scenario D — phase shift (entrainment in progress):** `tau_2` ≈ `tau_1` but acrophase is shifted relative to `tau_1`. LD caused a permanent phase shift; the phase angle ψ (acrophase ZT relative to ZT0) describes the new clock–environment relationship.

### 10. Minimum protocol (time-constrained)

If the full 17–21 day protocol is not feasible:

- Day 1–2: DD (coarse τ estimate)
- Day 3–10: LD 12:12 (entrainment attempt)

**Limitations**

- 2 days of DD: only a rough τ estimate (low R² in Cosinor).
- No DD after LD: cannot distinguish entrainment from masking.
- Not suitable for publication without additional evidence.
- Use the Chi² periodogram only; Cosinor is unreliable with < 7 cycles.

!!! example "Status of current recordings (2026-03-03)"
    - 3 days of LD 12:12 available.
    - Chi² shows τ = 20–25 h (not yet 24 h) — transient phase likely.
    - Recommendation: extend LD recording by 4–5 more days, then append 5–7 days of DD.

### 11. Plugin settings cheat sheet

**Phase 1 & 3 (DD)**

| Setting | Value |
|---------|-------|
| Adaptive Illumination Baseline | OFF |
| Jump Correction | OFF (unless hardware artefacts) |
| Detrending | OFF |
| Period range | 16–36 h |
| Data source | Raw Intensity or Fraction Movement |
| Time Range | Full Recording |
| Cosinor period | fix to estimated τ (e.g. 21 h) |

**Phase 2 (LD stable segment, day 4–7)**

| Setting | Value |
|---------|-------|
| Adaptive Illumination Baseline | ON |
| Jump Correction | OFF |
| Detrending | OFF |
| Period range | 20–28 h |
| Data source | Raw Intensity (Cosinor) / Fraction Movement (Chi²) |
| Time Range | Start: 72 h, End: 168 h |
| ZT mode | ON |

### 12. References

- Pittendrigh, C. S., & Daan, S. (1976). A functional analysis of circadian pacemakers in nocturnal rodents. *J. Comp. Physiol.*, 106, 223–252.
- Aschoff, J. (1965). *Circadian Clocks.* North-Holland Publishing.
- Sokolove, P. G., & Bushell, W. N. (1978). The chi square periodogram: its application to the analysis of circadian rhythms. *J. Theor. Biol.*, 72(1), 131–160.
- Nelson, W., et al. (1979). Methods for cosinor rhythmometry. *Chronobiologia*, 6(4), 305–323.
- Hendricks, J. C., et al. (2000). Rest in Drosophila is a sleep-like state. *Neuron*, 25, 129–138.
