#!/usr/bin/env python3
"""
SensoWash live monitor — subscribes to all BLE notifications and prints state changes.

Usage:
    python monitor.py [ADDRESS]
"""

import asyncio
import sys
from datetime import datetime
from sensowash import SensoWashClient, CHARACTERISTICS
from sensowash.models import (
    OnOff, WaterFlow, WaterTemperature, NozzlePosition,
    SeatTemperature, DryerTemperature, DryerSpeed, LidState,
    ErrorCode,
)

# Reverse UUID→name map
_UUID_TO_NAME = {v.lower(): k for k, v in CHARACTERISTICS.items()}

# Per-characteristic decoder: uuid → (enum_type or None, label)
_DECODERS = {
    CHARACTERISTICS["WASH_STATE"]:         (OnOff,            "Wash"),
    CHARACTERISTICS["WATER_FLOW"]:         (WaterFlow,        "Water Flow"),
    CHARACTERISTICS["WATER_TEMPERATURE"]:  (WaterTemperature, "Water Temp"),
    CHARACTERISTICS["NOZZLE_POSITION"]:    (NozzlePosition,   "Nozzle"),
    CHARACTERISTICS["DRYER_STATE"]:        (OnOff,            "Dryer"),
    CHARACTERISTICS["DRYER_TEMPERATURE"]:  (DryerTemperature, "Dryer Temp"),
    CHARACTERISTICS["DRYER_SPEED"]:        (DryerSpeed,       "Dryer Speed"),
    CHARACTERISTICS["FLUSH_STATE"]:        (None,             "Flush"),
    CHARACTERISTICS["FLUSH_AUTOMATIC"]:    (OnOff,            "Auto Flush"),
    CHARACTERISTICS["LID_STATE"]:          (LidState,         "Lid"),
    CHARACTERISTICS["SEAT_STATE"]:         (OnOff,            "Seat"),
    CHARACTERISTICS["SEAT_TEMPERATURE"]:   (SeatTemperature,  "Seat Temp"),
    CHARACTERISTICS["SEAT_ACTUAL_TEMP"]:   (None,             "Actual Seat Temp"),
    CHARACTERISTICS["SEAT_PROXIMITY"]:     (OnOff,            "Proximity"),
    CHARACTERISTICS["DEODORIZATION_STATE"]:(OnOff,            "Deodorization"),
    CHARACTERISTICS["AMBIENT_LIGHT_STATE"]:(OnOff,            "Ambient Light"),
    CHARACTERISTICS["UVC_STATE"]:          (OnOff,            "UVC Light"),
    CHARACTERISTICS["STOP_STATE"]:         (None,             "STOP"),
    CHARACTERISTICS["ERROR_CODES"]:        ("errors",         "Error Codes"),
}


def decode_notification(uuid: str, data: bytes) -> str:
    entry = _DECODERS.get(uuid)
    if entry is None:
        return f"raw={data.hex()}"
    enum_type, label = entry
    if enum_type == "errors":
        errors = ErrorCode.decode_payload(data)
        if errors:
            return f"{label}: " + "; ".join(str(e.code) for e in errors)
        return f"{label}: none"
    if enum_type and data:
        try:
            return f"{label}: {enum_type(data[0]).name}"
        except ValueError:
            return f"{label}: {data.hex()}"
    return f"{label}: {data.hex()}"


async def monitor(address: str):
    def on_notif(uuid: str, data: bytes):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        desc = decode_notification(uuid, data)
        print(f"[{ts}] {desc}")

    print(f"🔌 Connecting to {address}...")
    async with SensoWashClient(address, notification_cb=on_notif) as toilet:
        info = await toilet.get_device_info()
        print(f"✅ Connected: {info.model_number} ({info.serial_number})")
        print("📡 Listening for notifications. Press Ctrl+C to exit.\n")
        while True:
            await asyncio.sleep(1)


async def main():
    address = sys.argv[1] if len(sys.argv) > 1 else None
    if not address:
        print("🔍 Scanning for SensoWash devices (10s)...")
        devices = await SensoWashClient.discover(timeout=10.0)
        if not devices:
            print("❌ No devices found.")
            sys.exit(1)
        address = devices[0].address
        print(f"Using: {devices[0].name} ({address})\n")
    await monitor(address)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped.")
