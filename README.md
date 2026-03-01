# sensowash-ble

Python BLE library for **Duravit SensoWash** smart toilets.

Reverse-engineered from the official Android app (`com.duravit.sensowash` v2.1.19).  
Supports the BLE GATT protocol used by modern SensoWash devices:

| Model name | BLE prefix |
|---|---|
| SensoWash Classic | `SensoWash c` |
| SensoWash U | `SensoWash u` |
| SensoWash Starck F Pro | `SensoWash s` |
| SensoWash i Pro | `SensoWash i` |
| DuraSystem | `DuraSystem` |

> **Note:** Older serial-protocol devices (Starck Plus/Lite, i Plus/Lite China/USA) use a
> different UART-over-BLE protocol and are not currently supported.

---

## Requirements

- Python 3.9+
- [bleak](https://github.com/hbldh/bleak) — cross-platform BLE library
- Bluetooth adapter on your host machine
- Linux: may need `sudo` or `CAP_NET_ADMIN` for BLE scanning

```bash
pip install bleak
pip install .   # or: pip install -e .
```

---

## Quick Start

```python
import asyncio
from sensowash import SensoWashClient
from sensowash.models import WaterFlow, WaterTemperature, NozzlePosition

async def main():
    # Discover nearby devices
    devices = await SensoWashClient.discover()
    print(devices)

    # Connect by MAC address (Linux) or CoreBluetooth UUID (macOS)
    async with SensoWashClient("AA:BB:CC:DD:EE:FF") as toilet:

        # Device info
        info = await toilet.get_device_info()
        print(info)

        # Check for faults
        errors = await toilet.get_error_codes()
        for e in errors:
            print(e)

        # Full state snapshot
        state = await toilet.get_full_state()
        print(state)

        # Start rear wash
        await toilet.start_rear_wash(
            water_flow=WaterFlow.MEDIUM,
            water_temperature=WaterTemperature.TEMP_2,
            nozzle_position=NozzlePosition.POSITION_2,
        )
        await asyncio.sleep(30)
        await toilet.stop()

asyncio.run(main())
```

---

## API Reference

### `SensoWashClient(address, timeout=20.0, notification_cb=None)`

Async context manager. `notification_cb(uuid: str, data: bytes)` is called for every
BLE notification received from the toilet.

#### Discovery
| Method | Description |
|---|---|
| `SensoWashClient.discover(timeout=10.0)` | Scan and return list of `BLEDevice` |

#### Device Info & State
| Method | Returns |
|---|---|
| `get_device_info()` | `DeviceInfo` (manufacturer, model, serial, firmware) |
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
| `get_wash_state()` | `OnOff` |

#### Dryer
| Method | Description |
|---|---|
| `start_dryer(temperature, speed)` | Start warm air dryer |
| `stop_dryer()` | Stop dryer |
| `set_dryer_temperature(temp)` | `DryerTemperature.TEMP_0–3` |
| `set_dryer_speed(speed)` | `DryerSpeed.SPEED_0 / SPEED_1` |

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
| `set_seat_auto(enabled)` | Auto seat lowering |

#### Deodorization
| Method | Description |
|---|---|
| `set_deodorization(enabled)` | Deodorization on/off |
| `set_deodorization_auto(enabled)` | Automatic deodorization |

#### Lighting
| Method | Description |
|---|---|
| `set_ambient_light(enabled)` | Ambient/night light on/off |
| `set_uvc_light(enabled)` | HygieneUV light on/off |
| `set_uvc_auto(enabled)` | Automatic UVC cycles |

#### Maintenance
| Method | Description |
|---|---|
| `get_error_codes()` | List active fault codes |
| `set_mute(muted)` | Mute/unmute beep tones |
| `set_water_hardness(hardness)` | `WaterHardness.LEVEL_0–4` |
| `get_descaling_state()` | Raw descaling state bytes |

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

The `ERROR_CODES` characteristic returns a bitmask. Each active error is decoded
into an `ErrorCode` object:

```python
errors = await toilet.get_error_codes()
for e in errors:
    print(f"[{e.code}] {e.category}: {e.title}")
    print(f"  Service ref: {e.service_code}")
    print(f"  Action: {e.action}")
```

| Code | Service Ref | Category | Meaning |
|---|---|---|---|
| 1–3 | 721.x | Power Supply | Power fault — cut power, call installer |
| 4, 9–13 | 725.x | Seat Heating | Seat heating fault — cut power, call installer |
| 17 | 735.1 | Water Supply | Water supply fault — close stop valve |
| 18 | 735.2 | Water Supply | Low pressure — clean filter/check tubes |
| 19–20 | 735.x | Water Supply | Water supply fault — close stop valve |
| 25–30 | 726.x | Water Temperature | Shower water temp fault — close stop valve |
| 33–35 | 727.x | Warm Air Dryer | Dryer fault — cut power, call installer |
| 41–42 | 722.x | Gearbox | Seat/lid gear fault — call installer |
| 49 | 746.1 | HygieneUV | UVC fan abnormal |
| 50 | 746.2 | HygieneUV | UVC circuit voltage fault |
| 51 | 746.3 | HygieneUV | UVC comms failure |
| 65 | 738.3 | Flush System | Flush fault — cut power, close stop valve |

---

## BLE Protocol Notes

- **Transport:** BLE GATT over Bluetooth Low Energy
- **Bonding:** Required. Pair your device before connecting.
- **MTU:** The app requests 512 bytes; bleak handles this automatically.
- **Time sync:** The client writes current time to the Current Time Service on connect
  (required for scheduling features).
- **Notifications:** The client subscribes to all notifiable characteristics on connect.
  Pass `notification_cb` to receive real-time state changes.
- **Wire format:** Nearly all values are a single unsigned byte matching the enum integer.

Full GATT service/characteristic UUID reference: see [`sensowash/constants.py`](sensowash/constants.py)  
Full protocol documentation: [`docs/PROTOCOL.md`](docs/PROTOCOL.md)

---

## Examples

```bash
# Interactive demo
python examples/demo.py

# Connect to a specific device
python examples/demo.py AA:BB:CC:DD:EE:FF

# Live notification monitor
python examples/monitor.py AA:BB:CC:DD:EE:FF
```

---

## Legal

This project is an independent reverse engineering effort for personal interoperability
purposes. It is not affiliated with, endorsed by, or connected to Duravit AG in any way.
Use at your own risk. Do not use to modify toilet behaviour in a way that could cause harm.
