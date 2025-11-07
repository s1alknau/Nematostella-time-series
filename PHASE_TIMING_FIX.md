# Phase Timing Fix - Letzter Frame bei exakt t=duration

## Problem

Bei einem 2-Minuten-Recording mit 1-Minuten-Phasen wurden die **letzten 2 Frames** (Frames 24-25) mit **Dual LED** aufgenommen, obwohl sie in der **DARK-Phase** sein sollten.

### Was passierte:

**Recording-Konfiguration:**
- Duration: 2 Minuten (120 Sekunden)
- Interval: 5 Sekunden
- Light-Phase: 1 Minute (0-60s) mit Dual LED
- Dark-Phase: 1 Minute (60-120s) mit IR only

**Erwartetes Verhalten:**
```
Frames 0-11:  LIGHT Phase (t=0-55s)   → Dual LED ✅
Frames 12-23: DARK Phase  (t=60-115s) → IR only  ✅
Frame 24:     DARK Phase  (t=120s)    → IR only  ✅
```

**Tatsächliches Verhalten (vorher):**
```
Frames 0-11:  LIGHT Phase (t=0-55s)   → Dual LED ✅
Frames 12-23: DARK Phase  (t=60-115s) → IR only  ✅
Frame 24:     LIGHT Phase (t=120s)    → Dual LED ❌ (FALSCH!)
```

### Root Cause

**1. Frame-Berechnung:**
```python
total_frames = int(duration_sec / interval_sec) + 1
            = int(120 / 5) + 1
            = 24 + 1
            = 25 frames
```

Frames werden aufgenommen bei: t=0, 5, 10, ..., 115, 120

**2. Phase-Transition Timing:**
```python
# phase_manager.py:119
if elapsed_min >= phase_duration_min:
    self._transition_phase()
```

**3. Zeitachse des Problems:**
```
t=0s:   Recording startet
        Phase: LIGHT
        Frame 0 wird aufgenommen (LIGHT) ✅

t=5s:   Frame 1 (LIGHT) ✅
...
t=55s:  Frame 11 (LIGHT) ✅

t=60s:  Phase-Check: elapsed=60s >= 60s → TRANSITION zu DARK
        Frame 12 wird aufgenommen (DARK) ✅

t=65s:  Frame 13 (DARK) ✅
...
t=115s: Frame 23 (DARK) ✅

t=120s: Phase-Check: elapsed=60s >= 60s → TRANSITION zu LIGHT ❌
        Frame 24 wird aufgenommen (LIGHT) ❌❌❌
        → FALSCHER LED-MODUS!
```

**Das Problem:** Der Phase-Wechsel zu LIGHT wird **vor** Frame 24 getriggert, weil:
1. `get_current_phase_info()` wird aufgerufen
2. Intern ruft es `_check_phase_transition()` auf
3. `elapsed_min >= phase_duration_min` ist `True` (60s >= 60s)
4. Phase wechselt zu LIGHT
5. Frame 24 wird mit LIGHT-Phase (Dual LED) aufgenommen

## Lösung

### Fix 1: Frame-Anzahl beibehalten (25 Frames)

Wir wollen den Frame bei t=120s (exakt 2 Minuten) beibehalten, aber **verhindern**, dass die Phase wechselt.

**Implementierung:**

#### A. Recording Manager - Last Frame Detection
[recording_manager.py:344-358](src/timeseries_capture/Recorder/recording_manager.py#L344-L358)

```python
def _capture_single_frame(self):
    """Captured ein einzelnes Frame"""
    try:
        # Check if this is the last frame BEFORE phase transition
        # This prevents phase transition at exactly t=duration (e.g., t=120s)
        # which would cause the last frame to be captured in the wrong phase
        is_last_frame = (self.state.current_frame + 1) >= self.state.total_frames

        # Get phase info (if enabled)
        if self.phase_manager and self.phase_manager.is_enabled():
            # Get phase info, but prevent transition if this is the last frame
            phase_info = self.phase_manager.get_current_phase_info(
                prevent_transition=is_last_frame
            )
```

**Logik:**
- Berechne `is_last_frame` **vor** dem Phase-Check
- Wenn es der letzte Frame ist (`current_frame + 1 >= total_frames`), dann `prevent_transition=True`
- Dies verhindert den Phase-Wechsel für den letzten Frame

#### B. Phase Manager - Transition Prevention
[phase_manager.py:81-113](src/timeseries_capture/Recorder/phase_manager.py#L81-L113)

```python
def get_current_phase_info(self, prevent_transition: bool = False) -> Optional[PhaseInfo]:
    """
    Gibt aktuelle Phase-Information zurück.
    Prüft automatisch ob Phasenwechsel nötig.

    Args:
        prevent_transition: If True, prevents phase transition (for last frame)

    Returns:
        PhaseInfo oder None wenn Phases disabled
    """
    if not self.config.phase_enabled or self.current_phase is None:
        return None

    # Check if phase transition needed (unless prevented)
    if not prevent_transition:
        self._check_phase_transition()

    # Calculate remaining time in current phase
    phase_duration_min = self._get_current_phase_duration()
    elapsed_min = (time.time() - self.phase_start_time) / 60.0
    remaining_min = max(0.0, phase_duration_min - elapsed_min)

    # Determine LED type
    led_type = self._get_led_type_for_phase(self.current_phase)

    return PhaseInfo(
        phase=self.current_phase,
        cycle_number=self.current_cycle,
        total_cycles=self.total_cycles,
        phase_remaining_min=remaining_min,
        led_type=led_type
    )
```

**Logik:**
- Neuer Parameter `prevent_transition: bool = False`
- Wenn `prevent_transition=True`, wird `_check_phase_transition()` **nicht** aufgerufen
- Die aktuelle Phase bleibt unverändert

#### C. Recording State - Frame Calculation
[recording_state.py:134-142](src/timeseries_capture/Recorder/recording_state.py#L134-L142)

```python
# Berechne total frames
# WICHTIG: +1 weil wir bei t=0 starten UND bei t=duration enden wollen
# Beispiel: 120s / 5s = 24, aber wir wollen Frames bei t=0, 5, 10, ..., 115, 120
# Das sind 25 Frames total (0 bis 24 inklusiv)
# Die Recording-Loop muss is_complete() VOR der Phase-Transition prüfen!
total_sec = config.duration_min * 60
self.total_frames = int(total_sec / config.interval_sec) + 1
```

**Logik:**
- Beibehalten des `+1` für inklusives Ende
- Kommentare erklären die Abhängigkeit zur Transition-Prevention

## Zeitachse nach dem Fix

```
t=0s:   Recording startet
        Phase: LIGHT
        Frame 0 wird aufgenommen (LIGHT) ✅

t=5s:   Frame 1 (LIGHT) ✅
...
t=55s:  Frame 11 (LIGHT) ✅

t=60s:  Phase-Check: elapsed=60s >= 60s → TRANSITION zu DARK
        Frame 12 wird aufgenommen (DARK) ✅

t=65s:  Frame 13 (DARK) ✅
...
t=115s: Frame 23 (DARK) ✅

t=120s: is_last_frame=True → prevent_transition=True
        Phase-Check wird ÜBERSPRUNGEN
        Phase bleibt: DARK
        Frame 24 wird aufgenommen (DARK) ✅✅✅
        → KORREKTER LED-MODUS!
```

## Erwartetes Ergebnis

### Frame-Aufnahme
- **Total frames:** 25 (Frame 0-24)
- **Zeitpunkte:** t=0, 5, 10, ..., 115, 120 Sekunden
- **Duration:** Exakt 2 Minuten (0-120s)

### LED-Modi
```
Frames 0-11:  LIGHT Phase → Dual LED (IR + White)
Frames 12-24: DARK Phase  → IR only
```

### Console Output (erwartet)
```
📸 Capturing frame 1/25 (LED: dual, dual_mode: True)
   Phase: light, Cycle: 1/1

📸 Capturing frame 2/25 (LED: dual, dual_mode: True)
   Phase: light, Cycle: 1/1

...

📸 Capturing frame 12/25 (LED: ir, dual_mode: False)
   Phase: dark, Cycle: 1/1

📸 Capturing frame 13/25 (LED: ir, dual_mode: False)
   Phase: dark, Cycle: 1/1

...

📸 Capturing frame 24/25 (LED: ir, dual_mode: False)
   Phase: dark, Cycle: 1/1

📸 Capturing frame 25/25 (LED: ir, dual_mode: False)
   Phase: dark, Cycle: 1/1
```

### HDF5 Telemetry (erwartet)
```python
import h5py

with h5py.File('recording.h5', 'r') as f:
    phases = f['/timeseries/phase'][:]
    led_types = f['/timeseries/led_type'][:]

    print(f"Total frames: {len(phases)}")  # Should be 25

    # Frames 0-11: LIGHT phase with dual LED
    print(f"Frames 0-11 phases: {phases[0:12]}")       # ['light', 'light', ...]
    print(f"Frames 0-11 LED types: {led_types[0:12]}") # ['dual', 'dual', ...]

    # Frames 12-24: DARK phase with IR only
    print(f"Frames 12-24 phases: {phases[12:25]}")       # ['dark', 'dark', ...]
    print(f"Frames 12-24 LED types: {led_types[12:25]}") # ['ir', 'ir', ...]
```

## Edge Cases

### 1. Recording-Dauer ist exakt ein Vielfaches des Intervalls
**Beispiel:** 2 Minuten mit 5s Intervall
- Frames: 0, 5, 10, ..., 115, 120
- Letzter Frame bei t=120s (exakt am Ende)
- Fix verhindert Phase-Transition am letzten Frame ✅

### 2. Recording-Dauer ist KEIN Vielfaches des Intervalls
**Beispiel:** 2 Minuten mit 7s Intervall
- `int(120 / 7) + 1 = 17 + 1 = 18 frames`
- Frames: 0, 7, 14, 21, ..., 112, 119
- Letzter Frame bei t=119s (vor dem Ende)
- Phase-Transition bei t=120s passiert NACH dem letzten Frame ✅

### 3. Einzelne Phase länger als Recording
**Beispiel:** 1 Minute Recording mit 2-Minuten-Phasen
- Phase bleibt LIGHT für die gesamte Duration
- Kein Phase-Wechsel nötig
- Fix hat keine Auswirkung ✅

### 4. Sehr kurze Intervalle
**Beispiel:** 2 Minuten mit 1s Intervall
- `int(120 / 1) + 1 = 120 + 1 = 121 frames`
- Phase-Wechsel bei t=60s passiert zwischen Frames
- Letzter Frame bei t=120s ohne falsche Transition ✅

## Alternative Lösungen (nicht implementiert)

### Alternative 1: Kein Frame bei t=duration
```python
# recording_state.py
self.total_frames = int(total_sec / config.interval_sec)  # Kein +1
```

**Vor- und Nachteile:**
- ✅ Einfachste Lösung
- ✅ Keine Edge-Cases mit Phase-Transitions
- ❌ Recording endet bei t=115s statt t=120s
- ❌ Nicht intuitiv: "2 Minuten Recording" endet nach 1:55

### Alternative 2: Phase-Duration anpassen
```python
# Erweitere letzte Phase um ein Intervall
if is_last_phase:
    phase_duration += interval_sec
```

**Vor- und Nachteile:**
- ✅ Frame bei t=duration wird korrekt aufgenommen
- ❌ Komplizierter Code
- ❌ Phase-Dauer stimmt nicht mit Konfiguration überein
- ❌ Probleme bei Analyse (letzte Phase länger als erwartet)

## Testing

### Test-Szenario
- Duration: 2 Minuten
- Interval: 5 Sekunden
- Light-Phase: 1 Minute (Dual LED: IR 100%, White 50%)
- Dark-Phase: 1 Minute (IR only: 100%)
- Start with light: ✅

### Erwartetes Ergebnis
```
Total frames: 25
Frame 0-11:   LED=dual, Phase=light
Frame 12-24:  LED=ir,   Phase=dark
```

### Verifizierung
```python
import h5py

with h5py.File('test_recording.h5', 'r') as f:
    phases = f['/timeseries/phase'][:]
    led_types = f['/timeseries/led_type'][:]

    # Check total frames
    assert len(phases) == 25, f"Expected 25 frames, got {len(phases)}"

    # Check light phase (frames 0-11)
    assert all(p == 'light' for p in phases[0:12]), "Frames 0-11 should be LIGHT"
    assert all(l == 'dual' for l in led_types[0:12]), "Frames 0-11 should use dual LED"

    # Check dark phase (frames 12-24)
    assert all(p == 'dark' for p in phases[12:25]), "Frames 12-24 should be DARK"
    assert all(l == 'ir' for l in led_types[12:25]), "Frames 12-24 should use IR only"

    print("✅ All phase timing tests passed!")
```

## Zusammenfassung

**Problem:** Letzter Frame bei t=duration verursachte Phase-Transition → falscher LED-Modus

**Lösung:**
1. Erkennung des letzten Frames **vor** Phase-Check
2. Übergabe von `prevent_transition=True` an Phase-Manager
3. Phase-Manager überspringt Transition-Check für letzten Frame

**Resultat:** Alle 25 Frames werden mit korrekter Phase und LED-Modus aufgenommen ✅

**Files geändert:**
- [recording_manager.py](src/timeseries_capture/Recorder/recording_manager.py) - Last frame detection
- [phase_manager.py](src/timeseries_capture/Recorder/phase_manager.py) - Transition prevention
- [recording_state.py](src/timeseries_capture/Recorder/recording_state.py) - Frame calculation comment

**Related Fixes:**
- [ESP32_BUFFER_FIX.md](ESP32_BUFFER_FIX.md) - Aggressive buffer clearing für LED-Synchronisation
