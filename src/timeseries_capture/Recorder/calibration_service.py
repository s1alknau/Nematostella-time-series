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
        max_iterations: int = 15,  # Increased from 10 to 15 for better convergence
        tolerance_percent: float = 2.5,  # Reduced from 5.0% to 2.5% for tighter intensity matching
        use_full_frame: bool = False,
        roi_fraction: float = 0.75,
        effective_max_getter: Optional[Callable[[], Optional[float]]] = None,
        saturation_limit_percent: float = 0.05,
        saturation_backoff_percent: float = 10.0,
        max_saturation_backoffs: int = 3,
    ):
        """
        Args:
            capture_callback: Function that captures a frame and returns np.ndarray
            set_led_power_callback: Function(power, led_type) that sets LED power
            led_on_callback: Function(led_type) that turns LED on
            led_off_callback: Function() that turns LED off
            target_intensity: Target mean intensity value
            max_iterations: Maximum calibration iterations
            tolerance_percent: Acceptable error percentage from target (default 2.5% for ≤5% phase difference)
            use_full_frame: If True, measure intensity over entire frame. If False, use center ROI
            roi_fraction: Fraction of frame to use for ROI (e.g., 0.75 = 75% x 75% center region)

        Note:
            A tolerance of 2.5% ensures that the maximum difference between dark and light phases
            is within 5% (worst case: both at opposite tolerance bounds: 2.5% + 2.5% = 5%)
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
        # Optional getter that returns the camera's actual max pixel value
        # (e.g. 4095 for 12-bit-in-uint16). When None the code falls back
        # to observed-max heuristics — see _measure_intensity().
        self.effective_max_getter = effective_max_getter

        # Saturation guard. Wells are brighter at their edges than in the
        # middle, so a calibration that only looks at the mean can land on a
        # power where those edges already sit at the sensor limit - and an
        # animal that swims there stops producing any measurable change.
        # Whenever the sensor clips while the mean is still at or below the
        # target, the target itself is unreachable without clipping and gets
        # lowered. It stays lowered for every case calibrated afterwards on
        # this instance, so IR, White and Dual keep their relation to each
        # other.
        self.saturation_limit_percent = saturation_limit_percent
        self.saturation_backoff_percent = saturation_backoff_percent
        self.max_saturation_backoffs = max_saturation_backoffs
        self.initial_target_intensity = target_intensity
        self.saturation_backoffs = 0
        self.last_saturation_percent = 0.0

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
        Calibrate both LEDs SIMULTANEOUSLY to match target intensity.

        IMPORTANT: This method calibrates IR and White LEDs together with both on at the same time.
        This ensures the combined intensity matches the target when using dual LED mode.

        CONSTRAINT: IR LED power is constrained to a minimum of 20% to maintain adequate
        darkfield illumination quality for transparent specimens. This ensures sufficient
        contrast and image quality even when white LED is present.

        Args:
            ir_initial_power: Starting IR LED power
            white_initial_power: Starting White LED power

        Returns:
            CalibrationResult with both LED powers (IR power will be >= 20%)
        """
        logger.info("Starting Dual LED calibration (SIMULTANEOUS mode)")
        logger.info(f"Target intensity: {self.target_intensity}")
        logger.info(f"Initial powers: IR={ir_initial_power}%, White={white_initial_power}%")

        current_ir_power = ir_initial_power
        current_white_power = white_initial_power
        best_ir_power = ir_initial_power
        best_white_power = white_initial_power
        best_intensity = 0.0
        best_error = float("inf")

        # Binary search boundaries for both LEDs
        # IMPORTANT: IR LED minimum set to 20% to maintain adequate darkfield illumination
        # quality for transparent specimens (darkfield microscopy requirement)
        min_ir = 20
        max_ir = 100
        min_white = 1
        max_white = 100

        # Turn on BOTH LEDs before calibration
        logger.info("Turning on BOTH IR and White LEDs for simultaneous calibration")

        # Select IR and turn on
        if not self.led_on_callback("ir"):
            logger.error("Failed to turn on IR LED")
            return CalibrationResult(
                success=False,
                led_type="dual",
                ir_power=0,
                white_power=0,
                measured_intensity=0.0,
                target_intensity=self.target_intensity,
                error_percent=100.0,
                iterations=0,
                message="Failed to turn on IR LED",
            )

        time.sleep(0.1)

        # Select White and turn on
        if not self.led_on_callback("white"):
            logger.error("Failed to turn on White LED")
            self.led_off_callback()  # Turn off IR
            return CalibrationResult(
                success=False,
                led_type="dual",
                ir_power=0,
                white_power=0,
                measured_intensity=0.0,
                target_intensity=self.target_intensity,
                error_percent=100.0,
                iterations=0,
                message="Failed to turn on White LED",
            )

        try:
            for iteration in range(self.max_iterations):
                logger.info(
                    f"Iteration {iteration + 1}/{self.max_iterations}: Testing DUAL LED at IR={current_ir_power}%, White={current_white_power}%"
                )

                # Set BOTH LED powers
                success_ir = self.set_led_power_callback(current_ir_power, "ir")
                time.sleep(0.1)
                success_white = self.set_led_power_callback(current_white_power, "white")

                if not (success_ir and success_white):
                    logger.error(
                        f"Failed to set LED powers (IR: {success_ir}, White: {success_white})"
                    )
                    return CalibrationResult(
                        success=False,
                        led_type="dual",
                        ir_power=current_ir_power,
                        white_power=current_white_power,
                        measured_intensity=best_intensity,
                        target_intensity=self.target_intensity,
                        error_percent=best_error,
                        iterations=iteration + 1,
                        message=f"Failed to set LED powers (iteration {iteration + 1})",
                    )

                # Wait for LEDs to stabilize
                time.sleep(0.5)

                # Capture and measure frame with BOTH LEDs on
                measured_intensity = self._measure_intensity()

                if measured_intensity is None:
                    logger.error(f"Failed to capture frame at iteration {iteration + 1}")
                    return CalibrationResult(
                        success=False,
                        led_type="dual",
                        ir_power=current_ir_power,
                        white_power=current_white_power,
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
                    best_ir_power = current_ir_power
                    best_white_power = current_white_power
                    best_intensity = measured_intensity
                    best_error = error_percent

                # Check if within tolerance
                if error_percent <= self.tolerance_percent:
                    logger.info(
                        f"✅ Dual calibration successful! IR={best_ir_power}%, White={best_white_power}%, Intensity={best_intensity:.1f}, Error={error_percent:.1f}%"
                    )
                    return CalibrationResult(
                        success=True,
                        led_type="dual",
                        ir_power=best_ir_power,
                        white_power=best_white_power,
                        measured_intensity=best_intensity,
                        target_intensity=self.target_intensity,
                        error_percent=error_percent,
                        iterations=iteration + 1,
                        message=f"Dual calibration successful at IR={best_ir_power}%, White={best_white_power}%",
                    )

                # Binary search adjustment - adjust both LEDs proportionally
                if measured_intensity < self.target_intensity:
                    # Too dim, increase both powers proportionally
                    min_ir = current_ir_power
                    min_white = current_white_power
                    current_ir_power = (current_ir_power + max_ir) // 2
                    current_white_power = (current_white_power + max_white) // 2
                else:
                    # Too bright, decrease both powers proportionally
                    max_ir = current_ir_power
                    max_white = current_white_power
                    current_ir_power = (min_ir + current_ir_power) // 2
                    current_white_power = (min_white + current_white_power) // 2

                # Prevent getting stuck
                if current_ir_power == best_ir_power and current_white_power == best_white_power:
                    logger.info(
                        f"⚠️ Calibration converged at IR={best_ir_power}%, White={best_white_power}% (error: {best_error:.1f}%)"
                    )
                    break

            # Max iterations reached or converged
            if best_error <= self.tolerance_percent:
                success = True
                message = (
                    f"Dual calibration successful at IR={best_ir_power}%, White={best_white_power}%"
                )
            else:
                success = False
                message = f"Dual calibration did not converge (best error: {best_error:.1f}%)"

            logger.info(f"Calibration finished: {message}")

            return CalibrationResult(
                success=success,
                led_type="dual",
                ir_power=best_ir_power,
                white_power=best_white_power,
                measured_intensity=best_intensity,
                target_intensity=self.target_intensity,
                error_percent=best_error,
                iterations=self.max_iterations,
                message=message,
            )

        finally:
            # Always turn off BOTH LEDs after calibration
            logger.info("Turning off BOTH LEDs after dual calibration")
            self.led_off_callback()

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

    def _reset_saturation_state(self) -> None:
        """Put the target back to what the user asked for, before a new trial."""
        self.target_intensity = self.initial_target_intensity
        self.saturation_backoffs = 0
        self.last_saturation_percent = 0.0

    def measure_frame_stats(self) -> Optional[dict]:
        """
        Mean, median and saturated share of one frame, all on the 0-255 scale.

        The median says how well the sensor range is actually used: a scene
        that is mostly dark with a few bright reflections can carry a decent
        mean while half its pixels sit near zero, and only the median makes
        that visible.
        """
        frame = self.capture_callback()
        if frame is None or frame.size == 0:
            return None

        full_scale = self._full_scale(frame) if frame.dtype.kind == "u" else 255.0
        scale = 255.0 / full_scale

        return {
            "mean": float(np.mean(frame)) * scale,
            "median": float(np.median(frame)) * scale,
            "saturated_percent": float(np.mean(frame >= full_scale)) * 100.0,
        }

    def calibrate_over_exposures(
        self,
        calibrate_once: Callable[[], "CalibrationResult"],
        set_exposure_ms: Callable[[float], bool],
        exposures_ms,
        settle_s: float = 1.0,
    ) -> dict:
        """
        Run the LED calibration at several exposure times and keep the best.

        "Best" is the exposure whose calibrated image uses the sensor range
        best - the highest median - among those that stay below the saturation
        limit. Mean alone would favour an image carrying a few bright
        reflections over one that is evenly lit.

        Each exposure is an independent trial, so the saturation backoff is
        reset before every one; otherwise a lowered target would carry over
        and make later exposures look worse than they are.

        Returns a dict with one row per exposure and the chosen entry under
        "best", or "best": None when no exposure could be calibrated.
        """
        rows = []

        for exposure in exposures_ms:
            if not set_exposure_ms(float(exposure)):
                logger.warning(f"Exposure {exposure} ms could not be set - skipping")
                continue

            time.sleep(settle_s)
            self._reset_saturation_state()

            result = calibrate_once()
            stats = self.measure_frame_stats()
            if stats is None:
                logger.warning(f"No frame after calibrating at {exposure} ms - skipping")
                continue

            row = {
                "exposure_ms": float(exposure),
                # The caller needs the result of the winning trial, not just
                # its numbers - the LED powers live in there.
                "result": result,
                "success": bool(getattr(result, "success", False)),
                "ir_power": getattr(result, "ir_power", None),
                "white_power": getattr(result, "white_power", None),
                "target_used": self.target_intensity,
                "backoffs": self.saturation_backoffs,
                **stats,
            }
            rows.append(row)
            logger.info(
                f"Exposure {exposure:>5.1f} ms: median {row['median']:6.1f}, "
                f"mean {row['mean']:6.1f}, saturated {row['saturated_percent']:5.2f}%, "
                f"IR {row['ir_power']}%, White {row['white_power']}%"
            )

        usable = [
            r for r in rows
            if r["success"] and r["saturated_percent"] <= self.saturation_limit_percent
        ]
        if usable:
            best = max(usable, key=lambda r: r["median"])
        elif rows:
            # Nothing stayed clean - take the least saturated so the caller has
            # something to work with, and say so.
            best = min(rows, key=lambda r: r["saturated_percent"])
            logger.warning(
                "No exposure reached the target without saturation; falling back to "
                f"{best['exposure_ms']:.1f} ms with {best['saturated_percent']:.2f}% saturated"
            )
        else:
            best = None
            logger.error("Exposure search produced no usable measurement at all")

        return {"rows": rows, "best": best}

    def _full_scale(self, region) -> float:
        """
        Highest value this camera can produce, for unsigned integer frames.

        Preference: the value the adapter reports from the pixel format, then
        an observed-max heuristic for the usual bit depths, and the container
        width as a last resort.
        """
        effective_max = None
        if self.effective_max_getter is not None:
            try:
                effective_max = self.effective_max_getter()
            except Exception:
                effective_max = None

        dtype_max_full = float(np.iinfo(region.dtype).max)
        if effective_max is None:
            observed_max = float(region.max())
            effective_max = dtype_max_full
            for bit_max in (1023.0, 4095.0, 16383.0):
                if observed_max <= bit_max < dtype_max_full:
                    effective_max = bit_max
                    break

        return float(effective_max)

    def _lower_target_for_saturation(self) -> None:
        """
        Lower the target because the sensor clips before reaching it.

        Called only when the mean is at or below target while pixels already
        sit at full scale - a target that cannot be met without losing those
        pixels. Overshooting probes of the search are therefore not affected,
        they measure above target.
        """
        if self.saturation_backoffs >= self.max_saturation_backoffs:
            logger.warning(
                f"Sensor still saturating ({self.last_saturation_percent:.2f}% of pixels) "
                f"after {self.saturation_backoffs} corrections - leaving target at "
                f"{self.target_intensity:.1f}. Reduce illumination or check for reflections."
            )
            return

        self.saturation_backoffs += 1
        previous = self.target_intensity
        self.target_intensity = max(
            1.0, previous * (1.0 - self.saturation_backoff_percent / 100.0)
        )
        logger.warning(
            f"Sensor saturating on {self.last_saturation_percent:.2f}% of pixels at "
            f"intensity {previous:.1f} - lowering target to {self.target_intensity:.1f} "
            f"(correction {self.saturation_backoffs}/{self.max_saturation_backoffs}). "
            "Applies to every case calibrated from here on."
        )

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

            raw_intensity = float(np.mean(region))

            # Normalize to 0-255 scale so target_intensity=200 is meaningful
            # regardless of camera bit depth (uint8, 10/12/14/16-bit-in-uint16, float).
            # Preference:
            #   1) Camera-adapter-reported effective max (exact, from PixelFormat).
            #   2) Observed-max heuristic for uint types.
            #   3) Full dtype range as last resort.
            if region.dtype.kind == "f":
                intensity = raw_intensity * 255.0
                full_scale = 1.0
            elif region.dtype.kind == "u":
                full_scale = self._full_scale(region)
                intensity = raw_intensity * 255.0 / full_scale
            else:
                intensity = raw_intensity * 255.0 / 255.0
                full_scale = 255.0

            # Saturation is checked on the whole frame, not on the ROI: the
            # bright spots that matter sit at the well edges, which a centred
            # ROI deliberately cuts away.
            self.last_saturation_percent = float(np.mean(frame >= full_scale)) * 100.0

            logger.debug(
                f"Measured intensity: {intensity:.1f}/255 (raw={raw_intensity:.1f}, "
                f"{region_desc}, saturated={self.last_saturation_percent:.3f}%)"
            )

            if (
                self.last_saturation_percent > self.saturation_limit_percent
                and intensity <= self.target_intensity
            ):
                self._lower_target_for_saturation()

            return intensity

        except Exception as e:
            logger.error(f"Error measuring intensity: {e}")
            return None
