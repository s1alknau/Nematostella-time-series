"""
ESP32 Commands - Kommando-Definitionen und Builder

Verantwortlich für:
- Command/Response Konstanten
- Command-Builder (Bytes zusammenstellen)
- Response-Parser
- Protokoll-Dokumentation
"""

import logging
import struct
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# COMMAND CONSTANTS (aus Firmware)
# ============================================================================


class Commands:
    """Command-Bytes die an ESP32 gesendet werden"""

    LED_ON = 0x01
    LED_OFF = 0x00
    STATUS = 0x02
    SYNC_CAPTURE = 0x0C
    SET_LED_POWER = 0x10
    SET_TIMING = 0x11
    SET_CAMERA_TYPE = 0x13
    SELECT_LED_IR = 0x20
    SELECT_LED_WHITE = 0x21
    LED_DUAL_OFF = 0x22
    GET_LED_STATUS = 0x23
    SET_IR_POWER = 0x24
    SET_WHITE_POWER = 0x25
    SYNC_CAPTURE_DUAL = 0x2C


class Responses:
    """Response-Bytes die von ESP32 empfangen werden"""

    LED_ON_ACK = 0xAA
    SYNC_COMPLETE = 0x1B
    TIMING_SET = 0x21
    ACK_ON = 0x01
    ACK_OFF = 0x02
    STATUS_ON = 0x11
    STATUS_OFF = 0x10
    ERROR = 0xFF
    LED_IR_SELECTED = 0x30
    LED_WHITE_SELECTED = 0x31
    LED_STATUS = 0x32


class CameraTypes:
    """Kamera-Typen"""

    HIK_GIGE = 1
    USB_GENERIC = 2


class LEDTypes:
    """LED-Typen"""

    IR = 0
    WHITE = 1


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class SyncResponse:
    """Response von SYNC_CAPTURE Command"""

    timing_ms: int
    temperature: float
    humidity: float
    led_type_used: str
    led_duration_ms: int
    led_power_actual: int
    success: bool


@dataclass
class LEDStatus:
    """Status der LEDs"""

    current_led_type: int  # 0=IR, 1=White
    ir_state: bool
    white_state: bool
    ir_power: int  # 0-100
    white_power: int  # 0-100


@dataclass
class TimingConfig:
    """Timing-Konfiguration"""

    stabilization_ms: int
    exposure_ms: int


# ============================================================================
# COMMAND BUILDERS
# ============================================================================


class CommandBuilder:
    """Builder für ESP32 Commands"""

    @staticmethod
    def build_led_on() -> bytes:
        """Build LED ON Command"""
        return bytes([Commands.LED_ON])

    @staticmethod
    def build_led_off() -> bytes:
        """Build LED OFF Command"""
        return bytes([Commands.LED_OFF])

    @staticmethod
    def build_status() -> bytes:
        """Build STATUS Command"""
        return bytes([Commands.STATUS])

    @staticmethod
    def build_sync_capture() -> bytes:
        """Build SYNC_CAPTURE Command"""
        return bytes([Commands.SYNC_CAPTURE])

    @staticmethod
    def build_sync_capture_dual() -> bytes:
        """Build SYNC_CAPTURE_DUAL Command"""
        return bytes([Commands.SYNC_CAPTURE_DUAL])

    @staticmethod
    def build_select_led_ir() -> bytes:
        """Build SELECT_LED_IR Command"""
        return bytes([Commands.SELECT_LED_IR])

    @staticmethod
    def build_select_led_white() -> bytes:
        """Build SELECT_LED_WHITE Command"""
        return bytes([Commands.SELECT_LED_WHITE])

    @staticmethod
    def build_led_dual_off() -> bytes:
        """Build LED_DUAL_OFF Command"""
        return bytes([Commands.LED_DUAL_OFF])

    @staticmethod
    def build_get_led_status() -> bytes:
        """Build GET_LED_STATUS Command"""
        return bytes([Commands.GET_LED_STATUS])

    @staticmethod
    def build_set_led_power(power: int) -> bytes:
        """
        Build SET_LED_POWER Command.

        Args:
            power: LED Power 0-100

        Returns:
            Command bytes
        """
        power = max(0, min(100, power))
        return bytes([Commands.SET_LED_POWER, power])

    @staticmethod
    def build_set_ir_power(power: int) -> bytes:
        """
        Build SET_IR_POWER Command.

        Args:
            power: IR LED Power 0-100

        Returns:
            Command bytes
        """
        power = max(0, min(100, power))
        return bytes([Commands.SET_IR_POWER, power])

    @staticmethod
    def build_set_white_power(power: int) -> bytes:
        """
        Build SET_WHITE_POWER Command.

        Args:
            power: White LED Power 0-100

        Returns:
            Command bytes
        """
        power = max(0, min(100, power))
        return bytes([Commands.SET_WHITE_POWER, power])

    @staticmethod
    def build_set_timing(stabilization_ms: int, exposure_ms: int) -> bytes:
        """
        Build SET_TIMING Command.

        Firmware erwartet: CMD (1 byte) + stab_ms (2 bytes big-endian) + exp_ms (2 bytes big-endian)

        Args:
            stabilization_ms: LED Stabilization Zeit in ms
            exposure_ms: Exposure Zeit in ms

        Returns:
            Command bytes
        """
        # Validate
        stabilization_ms = max(10, min(10000, stabilization_ms))
        exposure_ms = max(0, min(30000, exposure_ms))

        # Pack as big-endian uint16
        cmd = bytes([Commands.SET_TIMING])
        stab_bytes = struct.pack(">H", stabilization_ms)  # big-endian uint16
        exp_bytes = struct.pack(">H", exposure_ms)

        return cmd + stab_bytes + exp_bytes

    @staticmethod
    def build_set_camera_type(camera_type: int) -> bytes:
        """
        Build SET_CAMERA_TYPE Command.

        Args:
            camera_type: CameraTypes.HIK_GIGE oder CameraTypes.USB_GENERIC

        Returns:
            Command bytes
        """
        return bytes([Commands.SET_CAMERA_TYPE, camera_type])


# ============================================================================
# RESPONSE PARSERS
# ============================================================================


class ResponseParser:
    """Parser für ESP32 Responses"""

    @staticmethod
    def parse_sync_response(data: bytes) -> Optional[SyncResponse]:
        """
        Parse SYNC_COMPLETE Response.

        Format (aus Firmware):
        - Byte 0: 0x1B (RESPONSE_SYNC_COMPLETE)
        - Bytes 1-2: timing_ms (uint16 big-endian)
        - Bytes 3-6: temperature (float)
        - Bytes 7-10: humidity (float)
        - Byte 11: led_type_used (0=IR, 1=White)
        - Bytes 12-13: led_duration_ms (uint16 big-endian)
        - Byte 14: led_power_actual (uint8)

        Args:
            data: Response bytes (sollte 15 bytes sein)

        Returns:
            SyncResponse oder None bei Fehler
        """
        if len(data) < 15:
            logger.error(f"Sync response too short: {len(data)} bytes")
            return None

        if data[0] != Responses.SYNC_COMPLETE:
            logger.error(f"Invalid sync response header: 0x{data[0]:02X}")
            return None

        try:
            # Parse fields
            timing_ms = struct.unpack(">H", data[1:3])[0]
            temperature = struct.unpack("f", data[3:7])[0]
            humidity = struct.unpack("f", data[7:11])[0]
            led_type_used = data[11]
            led_duration_ms = struct.unpack(">H", data[12:14])[0]
            led_power_actual = data[14]

            # Map LED type to string
            led_type_str = "ir" if led_type_used == LEDTypes.IR else "white"

            return SyncResponse(
                timing_ms=timing_ms,
                temperature=temperature,
                humidity=humidity,
                led_type_used=led_type_str,
                led_duration_ms=led_duration_ms,
                led_power_actual=led_power_actual,
                success=True,
            )

        except Exception as e:
            logger.error(f"Error parsing sync response: {e}")
            return None

    @staticmethod
    def parse_led_status(data: bytes) -> Optional[LEDStatus]:
        """
        Parse GET_LED_STATUS Response.

        Format (aus Firmware sendLedStatus):
        - Byte 0: 0x32 (RESPONSE_LED_STATUS)
        - Byte 1: currentLedType (0=IR, 1=White)
        - Byte 2: ledIrState (0=OFF, 1=ON)
        - Byte 3: ledWhiteState (0=OFF, 1=ON)
        - Byte 4: LED_POWER_PERCENT_IR
        - Byte 5: LED_POWER_PERCENT_WHITE

        Args:
            data: Response bytes (sollte 6 bytes sein)

        Returns:
            LEDStatus oder None bei Fehler
        """
        if len(data) < 6:
            logger.error(f"LED status response too short: {len(data)} bytes")
            return None

        if data[0] != Responses.LED_STATUS:
            logger.error(f"Invalid LED status response header: 0x{data[0]:02X}")
            return None

        try:
            return LEDStatus(
                current_led_type=data[1],
                ir_state=(data[2] == 1),
                white_state=(data[3] == 1),
                ir_power=data[4],
                white_power=data[5],
            )
        except Exception as e:
            logger.error(f"Error parsing LED status: {e}")
            return None


# ============================================================================
# PROTOCOL DOCUMENTATION
# ============================================================================


class ProtocolDocs:
    """
    Dokumentation des ESP32 Kommunikations-Protokolls.

    SINGLE LED MODE:
    ----------------
    1. select_led_type('ir' oder 'white')
       → Sendet: CMD_SELECT_LED_IR (0x20) oder CMD_SELECT_LED_WHITE (0x21)
       → Response: RESPONSE_LED_IR_SELECTED (0x30) oder RESPONSE_LED_WHITE_SELECTED (0x31)

    2. begin_sync_pulse()
       → Sendet: CMD_SYNC_CAPTURE (0x0C)
       → Response: RESPONSE_LED_ON_ACK (0xAA)
       → ESP32 schaltet LED ein und wartet

    3. wait_sync_complete(timeout)
       → Wartet auf: RESPONSE_SYNC_COMPLETE (0x1B) + 14 bytes Daten
       → Response enthält: timing, temp, humidity, led_type, duration, power

    DUAL LED MODE:
    --------------
    1. begin_sync_pulse(dual=True)
       → Sendet: CMD_SYNC_CAPTURE_DUAL (0x2C)
       → Response: RESPONSE_LED_ON_ACK (0xAA)
       → ESP32 schaltet BEIDE LEDs ein

    2. wait_sync_complete(timeout)
       → Wie bei Single LED

    LED CONTROL:
    ------------
    - LED_ON: CMD_LED_ON (0x01) → schaltet aktuell gewählte LED ein
    - LED_OFF: CMD_LED_OFF (0x00) → schaltet aktuell gewählte LED aus
    - SET_LED_POWER: CMD_SET_LED_POWER (0x10) + power_byte
    - SET_IR_POWER: CMD_SET_IR_POWER (0x24) + power_byte
    - SET_WHITE_POWER: CMD_SET_WHITE_POWER (0x25) + power_byte

    TIMING:
    -------
    - SET_TIMING: CMD_SET_TIMING (0x11) + stab_ms (2 bytes) + exp_ms (2 bytes)
    - Response: RESPONSE_TIMING_SET (0x21)

    STATUS:
    -------
    - GET_STATUS: CMD_STATUS (0x02)
      → Response: RESPONSE_STATUS_ON (0x11) oder RESPONSE_STATUS_OFF (0x10)
    - GET_LED_STATUS: CMD_GET_LED_STATUS (0x23)
      → Response: RESPONSE_LED_STATUS (0x32) + 5 bytes Status

    WICHTIG:
    --------
    - Alle Multi-Byte Werte sind BIG-ENDIAN (außer floats)
    - Floats sind Little-Endian (standard IEEE 754)
    - Timeouts sollten mindestens 2 Sekunden sein
    - Buffer sollte vor Commands gecleart werden
    """

    pass
