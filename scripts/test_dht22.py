"""
Test: DHT22 temperature/humidity sensor on LED_Nematostella ESP32 firmware.

Reads sensor data via the custom binary protocol
(ESP32Controller.get_sensor_data), which returns a 5-byte response
[status][temp_hi][temp_lo][hum_hi][hum_lo].

Requires: LED_Nematostella firmware flashed on the ESP32 (NOT UC2-REST).

Usage:
    python scripts/test_dht22.py                       # auto-detect port, single read
    python scripts/test_dht22.py --port COM4           # explicit port
    python scripts/test_dht22.py --continuous          # loop until Ctrl+C
    python scripts/test_dht22.py --port COM7 --interval 2.0 --continuous
"""

import argparse
import logging
import sys
import time
from pathlib import Path

REPO_SRC = Path(__file__).resolve().parent.parent / "src"
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from timeseries_capture.ESP32_Controller.esp32_controller import ESP32Controller  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--port", default=None, help="Serial port (e.g. COM4). Default: auto-detect.")
    ap.add_argument("--baudrate", type=int, default=115200)
    ap.add_argument("--continuous", action="store_true", help="Keep reading until Ctrl+C")
    ap.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between reads in --continuous mode (min ~2s for DHT22)",
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    esp = ESP32Controller(port=args.port, baudrate=args.baudrate, auto_connect=True)

    if not esp.comm.connected:
        print(f"ERROR: could not connect to ESP32 on port={args.port or 'auto'}", file=sys.stderr)
        return 1

    print(f"Connected to ESP32 on {esp.comm.port} @ {esp.comm.baudrate} baud")
    print("Reading DHT22 sensor...\n")

    def read_once():
        data = esp.get_sensor_data()
        if data is None:
            print("  <read failed — no response from ESP32>")
            return
        print(
            f"  T = {data['temperature']:6.2f} °C   "
            f"H = {data['humidity']:6.2f} %   "
            f"(status=0x{data['status_code']:02X})"
        )

    try:
        if args.continuous:
            print(f"(polling every {args.interval:.1f}s, Ctrl+C to stop)\n")
            while True:
                read_once()
                time.sleep(args.interval)
        else:
            read_once()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            esp.disconnect()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
