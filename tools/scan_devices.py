"""Standalone LAN scan for Tuya devices - no cloud, no config file needed.

Usage:
    python tools/scan_devices.py

Finds IP address, device id (gwId) and protocol version for any Tuya device
already paired to your Wi-Fi network. Does NOT return the local_key - that
requires the cloud setup wizard (see tools/setup_wizard.py) or another
source you already have local_key from.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from airam_lights.lamps.discovery import scan_network  # noqa: E402


def main() -> None:
    print("Scanning local network for Tuya devices (this can take ~8-10 seconds)...\n")
    results = scan_network(timeout=10.0)
    if not results:
        print("No devices found. Check that the bulbs are powered on and connected to Wi-Fi,")
        print("and that this PC is on the same LAN/subnet as the bulbs.")
        return

    print(f"Found {len(results)} device(s):\n")
    for d in results:
        print(f"  ip={d.ip:<15}  id={d.device_id:<25}  version={d.version}")
    print("\nNext: run tools/setup_wizard.py to obtain local_key for each device id above,")
    print("or add them manually in the app's Devices tab if you already have the keys.")


if __name__ == "__main__":
    main()
