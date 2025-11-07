"""
Phase Manager - Day/Night Cycle Management

Verantwortlich für:
- Phase-Wechsel (Light <-> Dark)
- Cycle Counting
- LED Type Bestimmung pro Phase
- Phase Timing
"""

import logging
import time
from typing import Optional

from .recording_state import PhaseInfo, PhaseType, RecordingConfig

logger = logging.getLogger(__name__)


class PhaseManager:
    """
    Verwaltet Day/Night Cycles während Recording.

    Funktionsweise:
    - Recording startet mit start_phase
    - Bei jedem Frame: get_current_phase() prüft ob Wechsel nötig
    - Automatischer Phasenwechsel nach Zeitablauf
    """

    def __init__(self, config: RecordingConfig):
        self.config = config

        # Current Phase State
        self.current_phase: Optional[PhaseType] = None
        self.current_cycle = 0
        self.total_cycles = 0
        self.phase_start_time = 0.0

        # Calculate total cycles
        if config.phase_enabled:
            self._calculate_total_cycles()

        logger.info(f"PhaseManager initialized (enabled={config.phase_enabled})")

    def _calculate_total_cycles(self):
        """Berechnet Anzahl der Zyklen (inkl. partielle Zyklen)"""
        cycle_duration_min = self.config.light_duration_min + self.config.dark_duration_min
        total_duration_min = self.config.duration_min

        # Calculate total cycles including partial cycles
        # Use ceiling to count partial cycles
        import math

        self.total_cycles = math.ceil(total_duration_min / cycle_duration_min)

        # At least 1 cycle if phases enabled
        if self.total_cycles == 0:
            self.total_cycles = 1

        logger.info(
            f"Total cycles calculated: {self.total_cycles} (duration: {total_duration_min}min, cycle: {cycle_duration_min}min)"
        )

    def is_enabled(self) -> bool:
        """Gibt zurück ob Phase-Management aktiviert ist"""
        return self.config.phase_enabled

    def start_phase_recording(self):
        """Startet Phase-Recording"""
        if not self.config.phase_enabled:
            logger.info("Phase recording disabled")
            return

        # Determine starting phase
        if self.config.start_with_light:
            self.current_phase = PhaseType.LIGHT
        else:
            self.current_phase = PhaseType.DARK

        self.current_cycle = 1
        self.phase_start_time = time.time()

        logger.info(
            f"Phase recording started: {self.current_phase.value} (cycle 1/{self.total_cycles})"
        )

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
            led_type=led_type,
        )

    def _check_phase_transition(self):
        """Prüft ob Phasenwechsel nötig ist"""
        if not self.current_phase:
            return

        phase_duration_min = self._get_current_phase_duration()
        elapsed_min = (time.time() - self.phase_start_time) / 60.0

        if elapsed_min >= phase_duration_min:
            self._transition_phase()

    def _transition_phase(self):
        """Führt Phasenwechsel durch"""
        if not self.current_phase:
            return

        # Switch phase
        if self.current_phase == PhaseType.LIGHT:
            self.current_phase = PhaseType.DARK
            logger.info(f"Phase transition: LIGHT -> DARK (cycle {self.current_cycle})")
        else:
            self.current_phase = PhaseType.LIGHT
            self.current_cycle += 1
            logger.info(
                f"Phase transition: DARK -> LIGHT (cycle {self.current_cycle}/{self.total_cycles})"
            )

        # Reset phase timer
        self.phase_start_time = time.time()

    def _get_current_phase_duration(self) -> float:
        """Gibt Dauer der aktuellen Phase in Minuten zurück"""
        if self.current_phase == PhaseType.LIGHT:
            return self.config.light_duration_min
        else:
            return self.config.dark_duration_min

    def _get_led_type_for_phase(self, phase: PhaseType) -> str:
        """
        Bestimmt LED-Typ für Phase.

        Returns:
            'ir', 'white', oder 'dual'
        """
        if phase == PhaseType.DARK:
            # Dark phase always uses IR
            return "ir"
        else:
            # Light phase
            if self.config.dual_light_phase:
                return "dual"  # Both IR + White
            else:
                return "white"  # White only

    def force_phase_transition(self):
        """Erzwingt sofortigen Phasenwechsel (für Testing)"""
        if self.current_phase:
            self._transition_phase()
            logger.info("Phase transition forced")

    def get_phase_summary(self) -> dict:
        """Gibt Zusammenfassung zurück"""
        if not self.config.phase_enabled:
            return {"enabled": False}

        return {
            "enabled": True,
            "current_phase": self.current_phase.value if self.current_phase else None,
            "current_cycle": self.current_cycle,
            "total_cycles": self.total_cycles,
            "light_duration_min": self.config.light_duration_min,
            "dark_duration_min": self.config.dark_duration_min,
            "dual_light_phase": self.config.dual_light_phase,
        }
