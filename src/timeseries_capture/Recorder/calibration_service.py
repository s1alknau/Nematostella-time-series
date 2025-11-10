"""
Calibration Service - LED Intensity Calibration

Automatically adjusts LED power levels to achieve target intensity.
Supports:
- IR LED calibration
- White LED calibration
- Dual LED calibration (matching intensities)
"""

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CalibrationResult:
    """Result of LED calibration"""

    success: bool
    led_type: str  # 'ir', 'white', 'dual'
    ir_power: int  # Final IR LED power (0-100)
    white_power: int  # Final White LED power (0-100)
    measured_intensity: float  # Final measured intensity
    target_intensity: float  # Target intensity
    error_percent: float  # Percentage error from target
    iterations: int  # Number of iterations used
    message: str  # Human-readable result message


class CalibrationService:
    """
    LED Intensity Calibration Service.

    Uses camera feedback to automatically adjust LED power levels
    to achieve target intensity values.
    """

    def __init__(
        self,
        capture_callback: Callable[[], Optional[np.ndarray]],
        set_led_power_callback: Callable[[int, str], bool],
        led_on_callback: Callable[[str], bool],
        led_off_callback: Callable[[], bool],
        target_intensity: float = 200.0,
        max_iterations: int = 10,
        tolerance_percent: float = 5.0,
        use_full_frame: bool = False,
        roi_fraction: float = 0.75,
    ):
        """
        Args:
            capture_callback: Function that captures a frame and returns np.ndarray
            set_led_power_callback: Function(power, led_type) that sets LED power
            led_on_callback: Function(led_type) that turns LED on
            led_off_callback: Function() that turns LED off
            target_intensity: Target mean intensity value
            max_iterations: Maximum calibration iterations
            tolerance_percent: Acceptable error percentage from target
            use_full_frame: If True, measure intensity over entire frame. If False, use center ROI
            roi_fraction: Fraction of frame to use for ROI (e.g., 0.75 = 75% x 75% center region)
        """
        self.capture_callback = capture_callback
        self.set_led_power_callback = set_led_power_callback
        self.led_on_callback = led_on_callback
        self.led_off_callback = led_off_callback
        self.target_intensity = target_intensity
        self.max_iterations = max_iterations
        self.tolerance_percent = tolerance_percent
        self.use_full_frame = use_full_frame
        self.roi_fraction = roi_fraction

        roi_desc = (
            "full frame"
            if use_full_frame
            else f"center ROI ({roi_fraction*100:.0f}% x {roi_fraction*100:.0f}%)"
        )
        logger.info(
            f"CalibrationService initialized (target={target_intensity}, tolerance={tolerance_percent}%, region={roi_desc})"
        )

    def calibrate_ir(self, initial_power: int = 50) -> CalibrationResult:
        """
        Calibrate IR LED to target intensity.

        Args:
            initial_power: Starting IR LED power

        Returns:
            CalibrationResult with calibration outcome
        """
        logger.info(f"Starting IR LED calibration (initial power: {initial_power}%)")

        return self._calibrate_single_led(led_type="ir", initial_power=initial_power)

    def calibrate_white(self, initial_power: int = 30) -> CalibrationResult:
        """
        Calibrate White LED to target intensity.

        Args:
            initial_power: Starting White LED power

        Returns:
            CalibrationResult with calibration outcome
        """
        logger.info(f"Starting White LED calibration (initial power: {initial_power}%)")

        return self._calibrate_single_led(led_type="white", initial_power=initial_power)

    def calibrate_dual(
        self, ir_initial_power: int = 50, white_initial_power: int = 30
    ) -> CalibrationResult:
        """
        Calibrate both LEDs to match target intensity.

        First calibrates IR LED, then calibrates White LED to match.

        Args:
            ir_initial_power: Starting IR LED power
            white_initial_power: Starting White LED power

        Returns:
            CalibrationResult with both LED powers
        """
        logger.info("Starting Dual LED calibration")

        # Step 1: Calibrate IR LED
        logger.info("Step 1: Calibrating IR LED...")
        ir_result = self.calibrate_ir(ir_initial_power)

        if not ir_result.success:
            return CalibrationResult(
                success=False,
                led_type="dual",
                ir_power=ir_result.ir_power,
                white_power=white_initial_power,
                measured_intensity=ir_result.measured_intensity,
                target_intensity=self.target_intensity,
                error_percent=ir_result.error_percent,
                iterations=ir_result.iterations,
                message=f"Dual calibration failed: IR calibration unsuccessful - {ir_result.message}",
            )

        # Step 2: Calibrate White LED to match IR
        logger.info(
            f"Step 2: Calibrating White LED to match IR intensity ({ir_result.measured_intensity:.1f})..."
        )
        white_result = self.calibrate_white(white_initial_power)

        if not white_result.success:
            return CalibrationResult(
                success=False,
                led_type="dual",
                ir_power=ir_result.ir_power,
                white_power=white_result.white_power,
                measured_intensity=white_result.measured_intensity,
                target_intensity=self.target_intensity,
                error_percent=white_result.error_percent,
                iterations=ir_result.iterations + white_result.iterations,
                message=f"Dual calibration failed: White calibration unsuccessful - {white_result.message}",
            )

        # Success!
        return CalibrationResult(
            success=True,
            led_type="dual",
            ir_power=ir_result.ir_power,
            white_power=white_result.white_power,
            measured_intensity=(ir_result.measured_intensity + white_result.measured_intensity)
            / 2.0,
            target_intensity=self.target_intensity,
            error_percent=(ir_result.error_percent + white_result.error_percent) / 2.0,
            iterations=ir_result.iterations + white_result.iterations,
            message=f"Dual calibration successful! IR={ir_result.ir_power}%, White={white_result.white_power}%",
        )

    def _calibrate_single_led(self, led_type: str, initial_power: int) -> CalibrationResult:
        """
        Calibrate a single LED using binary search.

        Args:
            led_type: 'ir' or 'white'
            initial_power: Starting power level

        Returns:
            CalibrationResult
        """
        current_power = initial_power
        best_power = initial_power
        best_intensity = 0.0
        best_error = float("inf")

        # Binary search boundaries
        min_power = 1
        max_power = 100

        # Turn on LED before calibration
        logger.info(f"Turning on {led_type.upper()} LED for calibration")
        if not self.led_on_callback(led_type):
            logger.error(f"Failed to turn on {led_type} LED")
            return CalibrationResult(
                success=False,
                led_type=led_type,
                ir_power=0,
                white_power=0,
                measured_intensity=0.0,
                target_intensity=self.target_intensity,
                error_percent=100.0,
                iterations=0,
                message=f"Failed to turn on {led_type} LED",
            )

        try:
            for iteration in range(self.max_iterations):
                logger.info(
                    f"Iteration {iteration + 1}/{self.max_iterations}: Testing {led_type.upper()} LED at {current_power}%"
                )

                # Set LED power
                success = self.set_led_power_callback(current_power, led_type)
                if not success:
                    logger.error(f"Failed to set {led_type} LED power to {current_power}%")
                    return CalibrationResult(
                        success=False,
                        led_type=led_type,
                        ir_power=current_power if led_type == "ir" else 0,
                        white_power=current_power if led_type == "white" else 0,
                        measured_intensity=best_intensity,
                        target_intensity=self.target_intensity,
                        error_percent=best_error,
                        iterations=iteration + 1,
                        message=f"Failed to set LED power (iteration {iteration + 1})",
                    )

                # Wait for LED to stabilize
                time.sleep(0.5)  # Increased from 0.3s to 0.5s for better stabilization

                # Capture and measure frame
                measured_intensity = self._measure_intensity()

                if measured_intensity is None:
                    logger.error(f"Failed to capture frame at iteration {iteration + 1}")
                    return CalibrationResult(
                        success=False,
                        led_type=led_type,
                        ir_power=current_power if led_type == "ir" else 0,
                        white_power=current_power if led_type == "white" else 0,
                        measured_intensity=best_intensity,
                        target_intensity=self.target_intensity,
                        error_percent=best_error,
                        iterations=iteration + 1,
                        message=f"Failed to capture frame (iteration {iteration + 1})",
                    )

                # Calculate error
                error_percent = (
                    abs(measured_intensity - self.target_intensity) / self.target_intensity * 100.0
                )

                logger.info(
                    f"  Measured intensity: {measured_intensity:.1f} (target: {self.target_intensity:.1f}, error: {error_percent:.1f}%)"
                )

                # Update best result
                if error_percent < best_error:
                    best_power = current_power
                    best_intensity = measured_intensity
                    best_error = error_percent

                # Check if within tolerance
                if error_percent <= self.tolerance_percent:
                    logger.info(
                        f"✅ Calibration successful! Power={best_power}%, Intensity={best_intensity:.1f}, Error={error_percent:.1f}%"
                    )
                    return CalibrationResult(
                        success=True,
                        led_type=led_type,
                        ir_power=best_power if led_type == "ir" else 0,
                        white_power=best_power if led_type == "white" else 0,
                        measured_intensity=best_intensity,
                        target_intensity=self.target_intensity,
                        error_percent=error_percent,
                        iterations=iteration + 1,
                        message=f"Calibration successful at {best_power}% power",
                    )

                # Binary search adjustment
                if measured_intensity < self.target_intensity:
                    # Too dim, increase power
                    min_power = current_power
                    current_power = (current_power + max_power) // 2
                else:
                    # Too bright, decrease power
                    max_power = current_power
                    current_power = (min_power + current_power) // 2

                # Prevent getting stuck
                if current_power == best_power:
                    logger.info(
                        f"⚠️ Calibration converged at {best_power}% (error: {best_error:.1f}%)"
                    )
                    break

            # Max iterations reached or converged
            if best_error <= self.tolerance_percent:
                success = True
                message = f"Calibration successful at {best_power}% power"
            else:
                success = False
                message = f"Calibration did not converge (best error: {best_error:.1f}%)"

            logger.info(f"Calibration finished: {message}")

            return CalibrationResult(
                success=success,
                led_type=led_type,
                ir_power=best_power if led_type == "ir" else 0,
                white_power=best_power if led_type == "white" else 0,
                measured_intensity=best_intensity,
                target_intensity=self.target_intensity,
                error_percent=best_error,
                iterations=self.max_iterations,
                message=message,
            )

        finally:
            # Always turn off LED after calibration
            logger.info(f"Turning off {led_type.upper()} LED after calibration")
            self.led_off_callback()

    def _measure_intensity(self) -> Optional[float]:
        """
        Capture frame and measure mean intensity.

        Returns:
            Mean intensity value or None if capture failed
        """
        try:
            # Capture frame
            frame = self.capture_callback()

            if frame is None:
                logger.error("Capture callback returned None")
                return None

            if frame.size == 0:
                logger.error("Captured frame is empty")
                return None

            # Calculate mean intensity
            if self.use_full_frame:
                # Use entire frame
                region = frame
                region_desc = f"full frame ({frame.shape})"
            else:
                # Use center ROI to avoid edge artifacts
                h, w = frame.shape[:2]

                # Calculate ROI boundaries based on roi_fraction
                # E.g., 0.75 means 75% x 75% center region
                margin_h = int(h * (1 - self.roi_fraction) / 2)
                margin_w = int(w * (1 - self.roi_fraction) / 2)

                roi_y1 = margin_h
                roi_y2 = h - margin_h
                roi_x1 = margin_w
                roi_x2 = w - margin_w

                region = frame[roi_y1:roi_y2, roi_x1:roi_x2]
                region_desc = f"ROI ({region.shape}, {self.roi_fraction*100:.0f}% center)"

            intensity = float(np.mean(region))

            logger.debug(f"Measured intensity: {intensity:.1f} ({region_desc})")

            return intensity

        except Exception as e:
            logger.error(f"Error measuring intensity: {e}")
            return None
