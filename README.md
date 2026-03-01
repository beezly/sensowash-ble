# sensowash-ble

Python BLE library for **Duravit SensoWash** smart toilets.

Reverse-engineered from the official Android app (`com.duravit.sensowash` v2.1.19).  
Supports both the modern GATT protocol and the older UART-over-BLE serial protocol,
auto-detected on connect.

| Model | Protocol | BLE name |
|---|---|---|
| SensoWash Classic | GATT | `SensoWash c…` |
| SensoWash U | GATT | `SensoWash u…` |
| SensoWash Starck F Pro | GATT | `SensoWash s…` |
| SensoWash i Pro | GATT | `SensoWash i…` |
| DuraSystem | GATT | `DuraSystem…` |
| Starck F Lite / Plus | Serial | `DURAVIT_BT` |
| i Lite / Plus | Serial | `DURAVIT_BT` |

---

## Requirements

- Python 3.9+
- [bleak](https://github.com/hbldh/bleak) — cross-platform BLE library
- Bluetooth adapter on your host machine
- Linux: may need `sudo` or `CAP_NET_ADMIN` for BLE scanning

```bash
pip install bleak
pip install -e .
```

---

## Quick Start

```python
import asyncio
from sensowash import SensoWashClient
from sensowash.models import WaterFlow, WaterTemperature, NozzlePosition

async def main():
    async with SensoWashClient("AA:BB:CC:DD:EE:FF") as toilet:
        info = await toilet.get_device_info()
        print(info)

        await toilet.start_rear_wash(
            water_flow=WaterFlow.MEDIUM,
            water_temperature=WaterTemperature.TEMP_2,
            nozzle_position=NozzlePosition.POSITION_2,
        )
        await asyncio.sleep(30)
        await toilet.stop()

asyncio.run(main())
```

> **macOS:** Use the CoreBluetooth UUID instead of a MAC address —
> find it via Bluetooth settings or `SensoWashClient.discover()`.

---

## Pairing (serial-protocol devices only)

Older serial-protocol devices (Starck F/i Lite/Plus) require a one-time pairing handshake.
Press the physical Bluetooth button on the toilet when prompted.

```python
import asyncio
from sensowash import SensoWashClient

async def main():
    address = "AA:BB:CC:DD:EE:FF"  # or CoreBluetooth UUID on macOS

    # One-time pairing — press button on toilet within 30 seconds
    key = await SensoWashClient.pair(address)
    print(f"Pairing key: {key.hex()}")
    # → store this key somewhere (env var, config file, etc.)

    # Subsequent connections — supply the stored key
    async with SensoWashClient(address, pairing_key=key) as toilet:
        state = await toilet.get_full_state()
        print(state)

asyncio.run(main())
```

The library does **not** persist the key itself — that is left to the caller.
If you connect without a key and the toilet issues one, it is available on
`toilet.pairing_key` after connect.

---

## API Reference

### `SensoWashClient(address, timeout=20.0, notification_cb=None, pairing_key=None)`

Async context manager. `address` is a MAC address string (Linux/Windows) or
CoreBluetooth UUID (macOS). `notification_cb(uuid, data)` is called for every
BLE notification. `pairing_key` is required for serial-protocol devices after
the initial pairing.

| Property | Description |
|---|---|
| `toilet.protocol` | `'gatt'` or `'serial'` — detected on connect |
| `toilet.pairing_key` | Active pairing key bytes, or `None` (serial devices only) |

#### Discovery
| Method | Description |
|---|---|
| `SensoWashClient.discover(timeout=10.0)` | Scan and return list of `BLEDevice` |
| `SensoWashClient.pair(address, timeout=30.0)` | One-time pairing → returns key `bytes` |

#### Device Info & State
| Method | Returns |
|---|---|
| `get_device_info()` | `DeviceInfo` (manufacturer, model, serial, firmware) |
| `get_capabilities()` | `DeviceCapabilities` — which features this unit supports |
| `get_full_state()` | `dict` snapshot of all readable characteristics |
| `get_error_codes()` | `list[ErrorCode]` |

#### Wash
| Method | Description |
|---|---|
| `start_rear_wash(water_flow, water_temperature, nozzle_position)` | Start rear wash |
| `start_lady_wash(water_flow, water_temperature, nozzle_position)` | Start lady wash |
| `stop()` | Stop any active function |
| `set_water_flow(flow)` | `WaterFlow.LOW / MEDIUM / HIGH` |
| `set_water_temperature(temp)` | `WaterTemperature.TEMP_0–3` |
| `set_nozzle_position(pos)` | `NozzlePosition.POSITION_0–4` |

#### Dryer
| Method | Description |
|---|---|
| `start_dryer(temperature, speed)` | Start warm air dryer |
| `stop_dryer()` | Stop dryer |

#### Flush
| Method | Description |
|---|---|
| `flush()` | Trigger a manual flush |
| `set_auto_flush(enabled)` | Enable/disable auto flush |
| `set_pre_flush(enabled)` | Enable/disable pre-flush |

#### Seat & Lid
| Method | Description |
|---|---|
| `open_lid()` | Open lid |
| `close_lid()` | Close lid |
| `get_lid_state()` | `LidState.OPEN / CLOSED` |
| `set_seat_temperature(temp)` | `SeatTemperature.OFF / TEMP_1–3` |
| `get_actual_seat_temperature()` | Raw measured temp (int) |
| `set_proximity_detection(enabled)` | Proximity sensor on/off |

#### Lighting
| Method | Description |
|---|---|
| `get_ambient_light()` | Current ambient light state (`bool`) |
| `set_ambient_light(enabled)` | Ambient/night light on/off |
| `set_uvc_light(enabled)` | HygieneUV light on/off |
| `set_uvc_auto(enabled)` | Automatic UVC cycles |

#### Maintenance
| Method | Description |
|---|---|
| `get_mute()` | Current mute state (`bool`) |
| `set_mute(muted)` | Mute/unmute beep tones |
| `set_water_hardness(hardness)` | `WaterHardness.LEVEL_0–4` |
| `get_error_codes()` | List active fault codes |

#### Seat Heating Schedule
| Method | Description |
|---|---|
| `get_seat_heating_schedule()` | Read schedule → `SeatHeatingSchedule` |
| `set_seat_heating_schedule(schedule)` | Write a new schedule |
| `clear_seat_heating_schedule()` | Remove all scheduled windows |

#### UVC Disinfection Schedule
| Method | Description |
|---|---|
| `get_uvc_schedule()` | Read schedule → `UvcSchedule` |
| `set_uvc_schedule(schedule)` | Write a new schedule |
| `set_uvc_schedule_default()` | Restore factory default (02:00 + 03:00 daily) |

---

## Scheduling

The toilet runs schedules autonomously using its onboard RTC. BLE is only needed
to read or update them. The client syncs the RTC on every connect automatically.

### Seat Heating Schedule

```python
from sensowash import SensoWashClient
from sensowash.models import (
    SeatHeatingSchedule, SeatScheduleWindow, SeatTemperature,
    ALL_WEEKDAYS, ALL_WEEKEND,
)

schedule = SeatHeatingSchedule(
    enabled=True,
    temperature=SeatTemperature.TEMP_2,
    windows=[
        SeatScheduleWindow(
            from_hour=6, from_minute=30,
            to_hour=8,   to_minute=0,
            days=ALL_WEEKDAYS,    # Mon–Fri
        ),
        SeatScheduleWindow(
            from_hour=8, from_minute=0,
            to_hour=9,   to_minute=30,
            days=ALL_WEEKEND,     # Sat–Sun
        ),
    ],
)

async with SensoWashClient(address, pairing_key=key) as toilet:
    await toilet.set_seat_heating_schedule(schedule)
    current = await toilet.get_seat_heating_schedule()
    for w in current.windows:
        print(w)  # → "06:30–08:00 [MonTueWedThuFri]"
```

### UVC Disinfection Schedule

```python
from sensowash.models import UvcSchedule, UvcScheduleTime

schedule = UvcSchedule(triggers=[
    UvcScheduleTime(hour=2, minute=0),
    UvcScheduleTime(hour=4, minute=0),
])

async with SensoWashClient(address) as toilet:
    await toilet.set_uvc_schedule(schedule)
    await toilet.set_uvc_schedule_default()  # restore 02:00 + 03:00
```

Each UVC cycle runs for exactly **20 minutes** (firmware fixed). Triggers fire daily —
there is no per-weekday control for UVC.

### Day constants

```python
from sensowash.models import (
    MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY,
    ALL_WEEKDAYS, ALL_WEEKEND, ALL_DAYS,
)
```

---

## Enumerations

```python
from sensowash.models import (
    OnOff,             # OFF=0, ON=1
    WaterFlow,         # LOW=0, MEDIUM=1, HIGH=2
    WaterTemperature,  # TEMP_0–3
    NozzlePosition,    # POSITION_0–4
    SeatTemperature,   # OFF=0, TEMP_1–3
    DryerTemperature,  # TEMP_0–3
    DryerSpeed,        # SPEED_0=normal, SPEED_1=turbo
    LidState,          # CLOSED=0, OPEN=1
    WaterHardness,     # LEVEL_0–4
)
```

---

## Error Codes

```python
errors = await toilet.get_error_codes()
for e in errors:
    print(f"[{e.code}] {e.category}: {e.title} — {e.action}")
```

| Code | Category | Meaning |
|---|---|---|
| 1–3 | Power Supply | Power fault — cut power, call installer |
| 4, 9–13 | Seat Heating | Seat heating fault — cut power, call installer |
| 17–20 | Water Supply | Water fault — close stop valve |
| 25–30 | Water Temperature | Shower water temp fault — close stop valve |
| 33–35 | Warm Air Dryer | Dryer fault — cut power, call installer |
| 41–42 | Gearbox | Seat/lid gear fault — call installer |
| 49–51 | HygieneUV | UVC fan/circuit/comms fault |
| 65 | Flush System | Flush fault — cut power, close stop valve |

---

## Examples

```bash
# Interactive demo (auto-discovers or pass address)
python examples/demo.py
python examples/demo.py AA:BB:CC:DD:EE:FF

# Supply pairing key via env var (serial-protocol devices)
SENSOWASH_KEY=aabbccdd python examples/demo.py AA:BB:CC:DD:EE:FF

# Live notification monitor
python examples/monitor.py AA:BB:CC:DD:EE:FF
```

The demo includes:
- Device info, capabilities, error codes, full state snapshot
- Interactive wash / dryer / flush / lid / seat temp controls
- Ambient light blink test (5× toggle, restores original state)
- Seat heating schedule viewer/editor
- UVC schedule viewer/editor
- Pairing flow for serial-protocol devices

---

## Protocol Notes

- **Auto-detection:** The client checks for the serial UART service UUID on connect;
  if absent it falls back to GATT.
- **Time sync:** RTC is synced on every connect (required for scheduling).
- **Notifications:** All notifiable GATT characteristics are subscribed on connect.
  Pass `notification_cb` to receive real-time state changes.
- **Serial protocol:** Older devices use a UART-over-BLE serial framing layer with
  a proprietary handshake. The pairing key is a 4-byte secret exchanged once via
  the shake characteristic.

Full protocol documentation (GATT UUIDs, serial op codes, wire formats):  
[`docs/PROTOCOL.md`](docs/PROTOCOL.md)

---

## Legal

This project is an independent reverse engineering effort for personal interoperability
purposes. It is not affiliated with, endorsed by, or connected to Duravit AG in any way.
Use at your own risk. Do not use to modify toilet behaviour in a way that could cause harm.
