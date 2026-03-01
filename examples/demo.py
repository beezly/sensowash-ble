#!/usr/bin/env python3
"""
SensoWash BLE Demo
==================
Demonstrates the main features of the sensowash Python library.

Usage:
    # Auto-discover and connect to the first SensoWash found:
    python demo.py

    # Connect to a specific device by MAC address:
    python demo.py AA:BB:CC:DD:EE:FF

    # On macOS, use the CoreBluetooth UUID instead of MAC:
    python demo.py 12345678-ABCD-1234-ABCD-1234567890AB
"""

import asyncio
import sys
from sensowash import SensoWashClient
from sensowash.models import (
    WaterFlow, WaterTemperature, NozzlePosition,
    SeatTemperature, DryerTemperature, DryerSpeed,
    SeatHeatingSchedule, SeatScheduleWindow, UvcSchedule, UvcScheduleTime,
    ALL_WEEKDAYS, ALL_WEEKEND, ALL_DAYS,
)


async def discover_and_connect() -> str:
    print("🔍 Scanning for SensoWash devices (10s)...")
    devices = await SensoWashClient.discover(timeout=10.0)
    if not devices:
        print("❌ No SensoWash devices found.")
        sys.exit(1)
    print(f"\nFound {len(devices)} device(s):")
    for i, d in enumerate(devices):
        print(f"  [{i}] {d.name}  ({d.address})")
    choice = 0 if len(devices) == 1 else int(input("\nSelect device index: "))
    return devices[choice].address


async def main():
    address = sys.argv[1] if len(sys.argv) > 1 else await discover_and_connect()

    print(f"\n🔌 Connecting to {address}...")

    def on_notification(uuid: str, data: bytes):
        print(f"  📡 notification [{uuid[-8:]}] → {data.hex()}")

    async with SensoWashClient(address, notification_cb=on_notification) as toilet:
        print(f"✅ Connected! (protocol: {toilet.protocol})\n")

        # ── Device Info ────────────────────────────────────────────────────────
        print("── Device Information ──────────────────────────────────")
        info = await toilet.get_device_info()
        print(info)

        # ── Capabilities ───────────────────────────────────────────────────────
        print("\n── Capabilities ────────────────────────────────────────")
        caps = await toilet.get_capabilities()
        print(caps.summary())

        # ── Error Codes ────────────────────────────────────────────────────────
        print("\n── Error Codes ─────────────────────────────────────────")
        errors = await toilet.get_error_codes()
        if errors:
            for e in errors:
                print(f"  ⚠️  {e}")
        else:
            print("  ✅ No active errors")

        # ── Full State Snapshot ────────────────────────────────────────────────
        print("\n── Current State ───────────────────────────────────────")
        state = await toilet.get_full_state()
        for key, val in state.items():
            if key == "errors":
                continue
            print(f"  {key:<22} = {val}")

        # ── Interactive menu ───────────────────────────────────────────────────
        print("\n── What would you like to do? ──────────────────────────")
        print("  1) Start rear wash (medium flow, temp 2, centre nozzle)")
        print("  2) Start lady wash (medium flow, temp 2, centre nozzle)")
        print("  3) Start dryer")
        print("  4) Flush")
        print("  5) Open lid")
        print("  6) Close lid")
        print("  7) Set seat temperature")
        print("  8) Toggle ambient light")
        print("  t) Ambient light blink test (5x toggle, restore)")
        print("  9) Toggle mute")
        print("  s) View / set seat heating schedule")
        print("  u) View / set UVC disinfection schedule")
        print("  c) Re-display capabilities")
        print("  0) Stop / exit")

        choice = input("\nChoice: ").strip()

        if choice == "1":
            print("🚿 Starting rear wash...")
            await toilet.start_rear_wash(
                water_flow=WaterFlow.MEDIUM,
                water_temperature=WaterTemperature.TEMP_2,
                nozzle_position=NozzlePosition.POSITION_2,
            )
            print("  Running for 20s. Press Ctrl+C to stop early.")
            await asyncio.sleep(20)
            await toilet.stop()
            print("  ⏹ Stopped.")

        elif choice == "2":
            print("🚿 Starting lady wash...")
            await toilet.start_lady_wash(
                water_flow=WaterFlow.MEDIUM,
                water_temperature=WaterTemperature.TEMP_2,
                nozzle_position=NozzlePosition.POSITION_2,
            )
            await asyncio.sleep(20)
            await toilet.stop()
            print("  ⏹ Stopped.")

        elif choice == "3":
            print("💨 Starting dryer...")
            await toilet.start_dryer(
                temperature=DryerTemperature.TEMP_2,
                speed=DryerSpeed.SPEED_0,
            )
            await asyncio.sleep(30)
            await toilet.stop_dryer()
            print("  ⏹ Dryer stopped.")

        elif choice == "4":
            print("🌊 Flushing...")
            await toilet.flush()

        elif choice == "5":
            print("🚪 Opening lid...")
            await toilet.open_lid()

        elif choice == "6":
            print("🚪 Closing lid...")
            await toilet.close_lid()

        elif choice == "7":
            levels = {
                "0": SeatTemperature.OFF,
                "1": SeatTemperature.TEMP_1,
                "2": SeatTemperature.TEMP_2,
                "3": SeatTemperature.TEMP_3,
            }
            lvl = input("  Seat temperature (0=off, 1-3): ").strip()
            await toilet.set_seat_temperature(levels.get(lvl, SeatTemperature.TEMP_1))
            print("  🌡 Set.")

        elif choice == "8":
            current = await toilet.get_ambient_light()
            new_state = not current if current is not None else True
            await toilet.set_ambient_light(new_state)
            print(f"  💡 Ambient light {'on' if new_state else 'off'}.")

        elif choice == "t":
            await demo_ambient_blink(toilet)

        elif choice == "9":
            current = await toilet.get_mute()
            new_state = not current if current is not None else True
            await toilet.set_mute(new_state)
            print(f"  🔇 Mute {'on' if new_state else 'off'}.")

        elif choice == "c":
            caps = await toilet.get_capabilities()
            print("\n── Capabilities ────────────────────────────────────────")
            print(caps.summary())

        elif choice == "s":
            await demo_seat_schedule(toilet)

        elif choice == "u":
            await demo_uvc_schedule(toilet)

        elif choice == "0":
            print("  ⏹ Stopping...")
            await toilet.stop()

        print("\n👋 Done. Disconnecting.")


async def demo_seat_schedule(toilet: SensoWashClient) -> None:
    """Interactive seat heating schedule manager."""
    print("\n── Seat Heating Schedule ───────────────────────────────")
    current = await toilet.get_seat_heating_schedule()
    if current:
        print(f"  Enabled:     {current.enabled}")
        print(f"  Temperature: {current.temperature.name}")
        if current.windows:
            print("  Windows:")
            for w in current.windows:
                print(f"    {w}")
        else:
            print("  Windows: (none)")
    else:
        print("  (characteristic not available on this model)")
        return

    print("\n  a) Apply example schedule (weekday mornings + weekend late morning)")
    print("  c) Clear all windows")
    print("  x) Back")
    sub = input("  Choice: ").strip()

    if sub == "a":
        schedule = SeatHeatingSchedule(
            enabled=True,
            temperature=SeatTemperature.TEMP_2,
            windows=[
                SeatScheduleWindow(
                    from_hour=6, from_minute=30,
                    to_hour=8,   to_minute=0,
                    days=ALL_WEEKDAYS,
                ),
                SeatScheduleWindow(
                    from_hour=8, from_minute=0,
                    to_hour=9,   to_minute=30,
                    days=ALL_WEEKEND,
                ),
            ],
        )
        await toilet.set_seat_heating_schedule(schedule)
        print("  ✅ Schedule written.")
        print(f"     Weekday window: 06:30–08:00 at {schedule.temperature.name}")
        print(f"     Weekend window: 08:00–09:30 at {schedule.temperature.name}")

    elif sub == "c":
        await toilet.clear_seat_heating_schedule()
        print("  ✅ Schedule cleared.")


async def demo_uvc_schedule(toilet: SensoWashClient) -> None:
    """Interactive UVC schedule manager."""
    print("\n── UVC Disinfection Schedule ───────────────────────────")
    current = await toilet.get_uvc_schedule()
    if current is not None:
        if current.triggers:
            print(f"  Triggers ({len(current.triggers)}):")
            for t in current.triggers:
                print(f"    {t}")
        else:
            print("  Triggers: (none)")
    else:
        print("  (characteristic not available on this model)")
        return

    print("\n  a) Apply example (2am + 4am daily)")
    print("  d) Restore factory default (2am + 3am)")
    print("  c) Clear all triggers")
    print("  x) Back")
    sub = input("  Choice: ").strip()

    if sub == "a":
        schedule = UvcSchedule(triggers=[
            UvcScheduleTime(hour=2, minute=0),
            UvcScheduleTime(hour=4, minute=0),
        ])
        await toilet.set_uvc_schedule(schedule)
        print("  ✅ UVC schedule set: 02:00 and 04:00 daily (20 min each).")

    elif sub == "d":
        await toilet.set_uvc_schedule_default()
        print("  ✅ UVC schedule restored to default: 02:00 and 03:00.")

    elif sub == "c":
        await toilet.set_uvc_schedule(UvcSchedule(triggers=[]))
        print("  ✅ UVC schedule cleared.")



async def demo_ambient_blink(toilet: SensoWashClient) -> None:
    """Toggle ambient light 5 times (once per second), then restore original state."""
    print("\n── Ambient Light Blink Test ───────────────────────────")
    original = await toilet.get_ambient_light()
    print(f"  Current state: {'on' if original else 'off'}")
    current = original
    for i in range(5):
        current = not current
        await toilet.set_ambient_light(current)
        print(f"  [{i+1}/5] {'on' if current else 'off'}")
        await asyncio.sleep(1)
    await toilet.set_ambient_light(original)
    print(f"  Restored to: {'on' if original else 'off'}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted.")
