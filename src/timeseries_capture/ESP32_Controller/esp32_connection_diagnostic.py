"""
ESP32 Connection Diagnostic Tool
Helps identify why ESP32 won't connect
"""

import sys
import time

import serial
import serial.tools.list_ports


def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def scan_all_ports():
    """Scan and display ALL serial ports with detailed info"""
    print_header("SCANNING ALL SERIAL PORTS")

    ports = serial.tools.list_ports.comports()

    if not ports:
        print("❌ No serial ports found!")
        return []

    print(f"\n✅ Found {len(ports)} serial port(s):\n")

    for i, port in enumerate(ports, 1):
        print(f"{i}. Port: {port.device}")
        print(f"   Description: {port.description}")
        print(f"   HWID: {port.hwid}")
        print(f"   Manufacturer: {port.manufacturer}")
        print(f"   Product: {port.product}")
        print(f"   VID:PID: {port.vid}:{port.pid}" if port.vid else "   VID:PID: N/A")
        print()

    return [port.device for port in ports]


def test_port_connection(port, baudrate=115200):
    """Test if we can open a port and read data"""
    print_header(f"TESTING PORT: {port}")

    print(f"Attempting to open {port} at {baudrate} baud...")

    try:
        # Try different DTR/RTS configurations
        configs = [
            {"dtr": True, "rts": True},
            {"dtr": False, "rts": False},
            {"dtr": True, "rts": False},
            {"dtr": False, "rts": True},
        ]

        for config in configs:
            print(f"\n📌 Testing with DTR={config['dtr']}, RTS={config['rts']}...")

            try:
                ser = serial.Serial(port=port, baudrate=baudrate, timeout=1.0, **config)

                print("   ✅ Port opened successfully")
                print("   Waiting 2 seconds for ESP32 to boot...")
                time.sleep(2.0)

                # Check if any data in buffer
                waiting = ser.in_waiting
                print(f"   Bytes in buffer: {waiting}")

                if waiting > 0:
                    data = ser.read(waiting)
                    print("   📨 Received data:")
                    try:
                        print(f"      {data.decode('utf-8', errors='ignore')}")
                    except:
                        print(f"      (binary): {data.hex()}")

                # Try sending a simple command (STATUS = 0x02)
                print("\n   Sending STATUS command (0x02)...")
                ser.write(bytes([0x02]))
                ser.flush()

                time.sleep(0.5)

                waiting = ser.in_waiting
                print(f"   Response bytes: {waiting}")

                if waiting > 0:
                    response = ser.read(waiting)
                    print(f"   📨 Response: {response.hex()}")
                    if response:
                        print("   🎉 ESP32 IS RESPONDING!")
                        ser.close()
                        return True, config
                else:
                    print("   ⚠️ No response from ESP32")

                ser.close()

            except serial.SerialException as e:
                print(f"   ❌ Failed to open with this config: {e}")
                continue
            except Exception as e:
                print(f"   ❌ Unexpected error: {e}")
                continue

        return False, None

    except Exception as e:
        print(f"❌ Error testing port: {e}")
        return False, None


def check_permissions(port):
    """Check if user has permissions to access port (Linux/Mac)"""
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        print_header("CHECKING PERMISSIONS")
        import os
        import stat

        try:
            st = os.stat(port)
            mode = stat.filemode(st.st_mode)
            print(f"Port permissions: {mode}")

            # Check if user is in dialout group (Linux)
            if sys.platform.startswith("linux"):
                import grp

                try:
                    dialout = grp.getgrnam("dialout")
                    username = os.getenv("USER")
                    if username in dialout.gr_mem:
                        print(f"✅ User '{username}' is in 'dialout' group")
                    else:
                        print(f"⚠️ User '{username}' is NOT in 'dialout' group")
                        print(f"   Run: sudo usermod -a -G dialout {username}")
                        print("   Then logout and login again")
                except:
                    pass
        except Exception as e:
            print(f"Could not check permissions: {e}")


def main():
    print(
        """
    ╔═══════════════════════════════════════════════════════════╗
    ║        ESP32 CONNECTION DIAGNOSTIC TOOL                   ║
    ║                                                           ║
    ║  This tool will help identify why your ESP32 won't       ║
    ║  connect and suggest fixes.                              ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    )

    # Step 1: Scan all ports
    available_ports = scan_all_ports()

    if not available_ports:
        print("\n⚠️ DIAGNOSIS:")
        print("   - No serial ports detected")
        print("   - Make sure ESP32 is plugged in via USB")
        print("   - Try a different USB cable (must be data cable, not charge-only)")
        print("   - Try a different USB port")
        return

    # Step 2: Let user select port or test all
    print("\nOptions:")
    print("  A - Test ALL ports automatically")
    for i, port in enumerate(available_ports, 1):
        print(f"  {i} - Test only {port}")
    print("  Q - Quit")

    choice = input("\nYour choice: ").strip().upper()

    if choice == "Q":
        return

    ports_to_test = []
    if choice == "A":
        ports_to_test = available_ports
    elif choice.isdigit() and 1 <= int(choice) <= len(available_ports):
        ports_to_test = [available_ports[int(choice) - 1]]
    else:
        print("Invalid choice")
        return

    # Step 3: Test selected ports
    working_ports = []
    for port in ports_to_test:
        # Check permissions first (Linux/Mac)
        if sys.platform.startswith("linux") or sys.platform == "darwin":
            check_permissions(port)

        success, config = test_port_connection(port)
        if success:
            working_ports.append((port, config))

    # Step 4: Summary
    print_header("DIAGNOSTIC SUMMARY")

    if working_ports:
        print("\n🎉 SUCCESS! Found working ESP32 connection(s):\n")
        for port, config in working_ports:
            print(f"  Port: {port}")
            print(f"  Config: DTR={config['dtr']}, RTS={config['rts']}")
            print()

        print("📝 TO FIX YOUR CODE:")
        print("\n1. Use this port:")
        print(f"   controller.connect(port='{working_ports[0][0]}')")

        print("\n2. Update esp32_communication.py connect() method:")
        config = working_ports[0][1]
        print(
            f"""
   self.serial_connection = serial.Serial(
       port=target_port,
       baudrate=self.baudrate,
       timeout=self.read_timeout,
       write_timeout=self.write_timeout,
       dtr={config['dtr']},
       rts={config['rts']}
   )

   # Increase boot delay
   time.sleep(2.0)  # Changed from 0.5 to 2.0
        """
        )
    else:
        print("\n❌ No working ESP32 connection found\n")
        print("⚠️ POSSIBLE ISSUES:")
        print("   1. ESP32 is not running the correct firmware")
        print("   2. ESP32 is in bootloader mode (needs reset)")
        print("   3. Wrong baud rate (try 9600 or 115200)")
        print("   4. USB cable is charge-only (no data lines)")
        print("   5. Driver issues (install CP210x or CH340 drivers)")
        print("   6. Permission issues (run as admin/sudo)")

        print("\n🔧 TROUBLESHOOTING STEPS:")
        print("   1. Press the RESET button on your ESP32")
        print("   2. Try a different USB cable")
        print("   3. Install drivers:")
        print("      - CP210x: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers")
        print("      - CH340: http://www.wch-ic.com/downloads/CH341SER_EXE.html")
        print("   4. On Linux: sudo usermod -a -G dialout $USER (then logout/login)")
        print("   5. Try connecting with Arduino IDE or PuTTY to verify hardware")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDiagnostic cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
