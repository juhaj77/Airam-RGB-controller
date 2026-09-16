"""Phase 1 diagnostic script (see DEVELOPMENT STRATEGY in the project spec /
README.md): connect to ONE Airam/Tuya bulb over the local LAN and manually
verify read + write control works, before building anything else on top.

Usage:
    python tools/phase1_test.py --device "Lamp 1"                      # from saved config
    python tools/phase1_test.py --ip 192.168.1.50 --id eb... --key ... # ad-hoc, no config needed
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from airam_lights.config.schema import DeviceConfig  # noqa: E402
from airam_lights.config.store import ConfigStore  # noqa: E402
from airam_lights.lamps.tuya_device import LampDevice  # noqa: E402


def resolve_device(args) -> DeviceConfig:
    if args.device and not args.ip:
        store = ConfigStore()
        config = store.load()
        for d in config.devices:
            if d.name == args.device:
                return d
        names = [d.name for d in config.devices]
        raise SystemExit(f"No saved device named '{args.device}'. Known devices: {names}")
    if not (args.ip and args.id):
        raise SystemExit("Provide --device NAME (from saved config), or --ip and --id directly.")
    return DeviceConfig(
        id=args.id,
        name=args.device or "phase1-test-lamp",
        ip=args.ip,
        local_key=args.key or "",
        version=args.version,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1: single-bulb local control test")
    parser.add_argument("--device", help="Name of a device already saved in the app config")
    parser.add_argument("--ip", help="Bulb IP address (ad-hoc test, bypasses saved config)")
    parser.add_argument("--id", help="Tuya device id (gwId)")
    parser.add_argument("--key", help="Tuya local_key")
    parser.add_argument("--version", default="3.3", help="Local protocol version (default 3.3)")
    args = parser.parse_args()

    cfg = resolve_device(args)
    print(f"Connecting to '{cfg.name}' at {cfg.ip} (id={cfg.id}, protocol v{cfg.version})...\n")
    dev = LampDevice(cfg)

    print("-- status() : confirmed facts about THIS bulb --")
    try:
        dev.refresh_status()
        print(f"  Online:              {dev.status.online}")
        print(f"  Detected bulb type:  {dev.status.bulb_type}  (A/B/C - see DEVICE_NOTES.md)")
        latency = dev.status.last_latency_ms
        print(f"  Latency:             {latency:.0f} ms" if latency is not None else "  Latency:             n/a")
        if dev.status.last_error:
            print(f"  Error:               {dev.status.last_error}")
        print("  Raw datapoints (dps) as reported by the bulb itself:")
        for k, v in sorted(dev.status.raw_dps.items()):
            print(f"    {k}: {v}")
        if not dev.status.online:
            print("  Check: is the IP correct and reachable? Is local_key correct? Is the protocol version right?")
            print("  (Run tools/scan_devices.py to re-confirm IP/id/version from the LAN broadcast.)")
            return
    except Exception as e:
        print(f"  status() FAILED: {e}")
        print("  Check: is the IP correct and reachable? Is local_key correct? Is the protocol version right?")
        print("  (Run tools/scan_devices.py to re-confirm IP/id/version from the LAN broadcast.)")
        return

    if not cfg.local_key:
        print("\nNo local_key provided - stopping after the read-only status check.")
        print("Pass --key (or use --device with a saved, fully-configured device) to test writes.")
        return

    print("\n-- manual RGB / brightness / power test --")
    dev.ensure_colour_mode()
    for name, (r, g, b) in [("red", (255, 0, 0)), ("green", (0, 255, 0)), ("blue", (0, 0, 255)), ("white", (255, 255, 255))]:
        t0 = time.perf_counter()
        try:
            dev.set_color(r, g, b, wait_for_ack=True)
            latency_ms = (time.perf_counter() - t0) * 1000
            print(f"  set_color({name:5s}) OK   - {latency_ms:.0f} ms")
        except Exception as e:
            print(f"  set_color({name:5s}) FAILED: {e}")
        time.sleep(1.0)

    print("\nIf the bulb visibly cycled red -> green -> blue -> white, local RGB control is CONFIRMED.")
    print("Update the confirmation table in DEVICE_NOTES.md with these results.")


if __name__ == "__main__":
    main()
