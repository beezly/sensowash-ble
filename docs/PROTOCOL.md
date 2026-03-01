# SensoWash BLE Protocol Reference

Reverse-engineered from `com.duravit.sensowash` APK v2.1.19 (version code 1216).  
Decompiled using jadx from the XAPK distributed via APKPure.

---

## Device Discovery

Scan for BLE devices. Match by name prefix (case-insensitive contains check):

| Model | BLE Name Prefix |
|---|---|
| SensoWash Classic EU/NonEU | `SensoWash c` |
| SensoWash U | `SensoWash u` |
| SensoWash Starck F Pro | `SensoWash s` |
| SensoWash i Pro | `SensoWash i` |
| DuraSystem (actuator plate) | `DuraSystem` |
| Older serial-protocol devices | `duravit` (lowercase) |

---

## Wire Encoding

| Type | Encoding |
|---|---|
| On/Off | 1 byte: `0x00` = OFF, `0x01` = ON |
| Enum values | 1 byte unsigned integer (value matches enum ordinal) |
| Strings | UTF-8 bytes |
| Error codes | Bitmask: bit N of byte B = error `(B×8 + N + 1)` |
| Multi-byte | Little-endian `(b[0] | b[1]<<8 | ...)` |
| Time | BLE Current Time Service format (see below) |

---

## Connection Flow

1. Scan → find device by name prefix
2. Connect GATT
3. Bond/pair (`BluetoothDevice.createBond()` equivalent)
4. Request MTU 512
5. Discover services & characteristics
6. Write current time to Current Time characteristic
7. Enable CCCD notifications on all notifiable characteristics
8. Read initial state of all characteristics

---

## GATT Services & Characteristics

### 🚿 Wash Comfort Service
**Service:** `d24ced2b-c6c3-4736-b3fb-1194799da6a3`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| Wash State | `6669f6f4-ce05-4f33-bd2b-a1d7708f435f` | R/W/N | OFF=0, ON=1 |
| Water Flow | `51f6bfe2-51e5-41ae-80ee-544f0bd0dd5c` | R/W/N | LOW=0, MEDIUM=1, HIGH=2 |
| Nozzle Position | `d23cdfd9-ced6-45be-ad02-06cc029dd86b` | R/W/N | POSITION 0–4 |
| Comfort Wash | `49a26f77-68a8-48ff-a177-8b69c20fe422` | R/W/N | OFF=0, ON=1 (lady wash flag) |
| Water Temperature | `30b716ec-92d0-439e-927c-792219bac010` | R/W/N | TEMP 0–3 |

**Wash type selection:** Writing `ON` to Comfort Wash before writing `ON` to Wash State
selects lady wash. Writing `ON` to Wash State without setting Comfort Wash selects rear wash.

---

### 🌬️ Dryer Service
**Service:** `cd20ecfa-63ba-4c05-b842-eb7df24e24f5`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| Dryer State | `900e960e-9bd2-4ad8-b266-1385ae1ff8b8` | R/W/N | OFF=0, ON=1 |
| Dryer Temperature | `1dbf23b4-5a41-449d-8636-464b43a81f8a` | R/W/N | TEMP 0–3 |
| Dryer Speed | `3028ecd5-93c4-42ff-a792-60ff2b2eb786` | R/W/N | SPEED_0=0, SPEED_1=1 |

---

### 🚽 Flush Comfort Service
**Service:** `e2136ec6-bab1-4126-b9a8-0bf77faf0fe4`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| Flush State | `7b11aa15-110a-4d5c-bcbe-68958a07110d` | R/W/N | IDLE=0, FLUSHING=1 |
| Flush Automatic | `c7e6fbf9-ca39-47f8-af6b-91921a8fb45a` | R/W/N | OFF=0, ON=1 |
| Pre-Flush Automatic | `4813ad84-faba-40ac-a979-8d3afa913e1f` | R/W/N | OFF=0, ON=1 |

---

### 🪑 Seat Comfort Service
**Service:** `18ad3cbb-80c8-4bd9-aae0-7bc515518a75`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| Seat State | `b0d58bee-1577-4477-9a06-87a63d7f621e` | R/W/N | CLOSED=0, OPEN=1 |
| Seat Automatic | `43a5d0c4-d37c-44ac-8809-10bf7d3d1f76` | R/W/N | OFF=0, ON=1 |
| Lid State | `cbe0a79c-ec63-4002-99d9-f654e37c9f29` | R/W/N | CLOSED=0, OPEN=1 |
| Lid Automatic State | `9a29c013-a633-4b00-b2f9-85eed411a257` | R/W/N | (LidAutomaticState enum) |
| Seat Temperature (setpoint) | `3dd6cd56-8aa7-46ea-abf4-be0e22fe2cef` | R/W/N | OFF=0, TEMP 1–3 |
| Programmed Seat Temp | `c635f814-c6e5-49cb-8b31-2f4192091307` | R/W | schedule bytes |
| Proximity Detection | `d3edf5d9-24ac-49f7-ba53-5cf292c62a25` | R/W/N | OFF=0, ON=1 |
| Actual Seat Temperature | `74c0a5db-c82a-44f1-8afb-ec60d100513f` | R/N | raw uint8 |

---

### 💨 Deodorization Service
**Service:** `bbca9da5-9c55-4f7d-b300-5da2a40ba9ae`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| State | `af22add8-54de-4e0e-a6e1-0c0d7b966e50` | R/W/N | OFF=0, ON=1 |
| Automatic | `d89b39d3-087f-4387-bf4b-a1cf493b6e4b` | R/W/N | OFF=0, ON=1 |
| Delay | `757de4bc-f483-449c-b68d-692e4cd3f2da` | R/W | delay value |

---

### 💡 Ambient Light Service
**Service:** `1a6ee5de-e308-4690-97b6-9ac096c16326`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| State | `69c9c066-e07b-44cd-9de6-f59bba249e8a` | R/W/N | OFF=0, ON=1 |

---

### 🔵 HygieneUV Light Service
**Service:** `eccb139f-01bc-4999-9123-7fcf04559207`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| UVC State | `5d36dbf9-68fc-4241-b681-08660182c1f0` | R/W/N | (UvcLightState) |
| UVC Automatic | `fb8c782d-0491-44e0-8e1c-3f433a406595` | R/W/N | OFF=0, ON=1 |
| Programmed UVC | `26e57692-f4e2-4b5d-81da-08b0a645db3e` | R/W | schedule |
| Daily Cleaning Cycles | `dcfac46b-0e5e-4b07-b6f2-bfc801d2aa73` | R/W | cycle count |

---

### ⏹ Stop Service
**Service:** `aa33e402-ab99-4322-8c49-84c78f3fa5f2`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| Stop State | `e3909169-4b3e-4a5f-94c0-db27849cc5fd` | W | write any value to stop |

---

### 🔧 Maintenance Service
**Service:** `ea771f2d-ee21-4475-a1b5-229cb9b26807`

| Characteristic | UUID | R/W | Values |
|---|---|---|---|
| Cleaning State | `f9b1b6ee-530c-4c3b-bdba-8aec656681d1` | R/N | cleaning state |
| Draining State | `defd29ba-855a-407c-972a-570d002e4533` | R/N | read-only |
| Descaling State | `09952f12-2e5b-4842-bd84-2ffe43280c5a` | R/N | descaling state |
| Descaling Timer | `a10076f9-dfc9-4304-8769-2fb3ab368a4b` | R | remaining time |
| Mute | `b78b4d4f-9478-441f-a267-f93aa58bbb65` | R/W | OFF=0, ON=1 |
| Reset | `35d62c02-f2a0-4197-a855-acbc60d18598` | W | write to reset |
| Water Hardness | `55ec32c5-5353-4fe3-a103-90f35c7d2190` | R/W | 0–4 |
| Error Codes | `902acf9c-161c-4028-bbf4-0d2c9907b88d` | R/N | bitmask (see below) |

---

### ℹ️ Device Information (standard BLE 0x180A)

| Characteristic | UUID | Value |
|---|---|---|
| Manufacturer Name | `00002a29-0000-1000-8000-00805f9b34fb` | "Duravit" |
| Model Number | `00002a24-0000-1000-8000-00805f9b34fb` | Article number |
| Serial Number | `00002a25-0000-1000-8000-00805f9b34fb` | Serial string |
| Hardware Revision | `00002a27-0000-1000-8000-00805f9b34fb` | |
| Software Revision | `00002a28-0000-1000-8000-00805f9b34fb` | |
| Firmware Revision | `00002a26-0000-1000-8000-00805f9b34fb` | |

---

### 🕐 Current Time Service (standard BLE 0x1805)

| Characteristic | UUID | Format |
|---|---|---|
| Current Time | `00002a2b-0000-1000-8000-00805f9b34fb` | `<H B B B B B B B` (year, month, day, hour, min, sec, weekday, fractions256) + adjust_reason byte |

The app writes current time on every connection. Required for scheduling (energy saving,
programmed seat temperature, UVC cleaning cycles).

---

## Notifications

Write `0x01 0x00` to the CCCD descriptor (`00002902-0000-1000-8000-00805f9b34fb`) on any
characteristic to subscribe to change notifications.

All characteristics marked `N` in the table above support notifications.

---

## Error Code Bitmask Decoding

The ERROR_CODES characteristic returns N bytes. Each byte covers 8 consecutive error codes:
- Bit 0 of byte 0 = error code 1
- Bit 1 of byte 0 = error code 2
- ...
- Bit 0 of byte 1 = error code 9
- etc.

```python
for byte_idx, byte_val in enumerate(payload):
    for bit_idx in range(8):
        if byte_val & (1 << bit_idx):
            error_code = byte_idx * 8 + bit_idx + 1
```

### Error Code Table

| Code | Service Ref | Category | Title | Action |
|---|---|---|---|---|
| 1 | 721.1 | Power Supply | Power fault | Cut power → call installer |
| 2 | 721.2 | Power Supply | Power fault | Cut power → call installer |
| 3 | 721.3 | Power Supply | Power fault | Cut power → call installer |
| 4 | 725.1 | Seat Heating | Seat heating fault | Cut power → call installer |
| 9 | 725.2 | Seat Heating | Seat heating fault | Cut power → call installer |
| 10 | 725.3 | Seat Heating | Seat heating fault | Cut power → call installer |
| 11 | 725.4 | Seat Heating | Seat heating fault | Cut power → call installer |
| 12 | 725.6 | Seat Heating | Seat heating fault | Cut power → call installer |
| 13 | 725.5 | Seat Heating | Seat heating fault | Cut power → call installer |
| 17 | 735.1 | Water Supply | Water supply fault | Close stop valve → call installer |
| 18 | 735.2 | Water Supply | Low pressure | Clean filter/check tubes; if fails → call installer |
| 19 | 735.3 | Water Supply | Water supply fault | Close stop valve → call installer |
| 20 | 735.4 | Water Supply | Water supply fault | Close stop valve → call installer |
| 25 | 726.2 | Water Temperature | Shower water temp | Close stop valve → call installer |
| 26 | 726.3 | Water Temperature | Shower water temp | Close stop valve → call installer |
| 27 | 726.5 | Water Temperature | Shower water temp | Close stop valve → call installer |
| 28 | 726.6 | Water Temperature | Shower water temp | Close stop valve → call installer |
| 29 | 726.1 | Water Temperature | Shower water temp | Close stop valve → call installer |
| 30 | 726.7 | Water Temperature | Shower water temp | Close stop valve → call installer |
| 33 | 727.1 | Warm Air Dryer | Dryer fault | Cut power → call installer |
| 34 | 727.2 | Warm Air Dryer | Dryer fault | Cut power → call installer |
| 35 | 727.3 | Warm Air Dryer | Dryer fault | Cut power → call installer |
| 41 | 722.1 | Gearbox | Seat/lid gear fault | Call installer |
| 42 | 722.2 | Gearbox | Seat/lid gear fault | Call installer |
| 49 | 746.1 | HygieneUV | UVC fan abnormal | Dryer speed not transmitted |
| 50 | 746.2 | HygieneUV | UVC circuit fault | Voltage exceeds set value |
| 51 | 746.3 | HygieneUV | UVC comms fault | No feedback for 3 consecutive attempts |
| 65 | 738.3 | Flush System | Flush fault | Cut power, close stop valve → call installer |

UVC informational status codes (not faults, appear in notification stream):
- **52**: UVC disinfection cancelled — lid was lifted
- **53**: UVC not run — daily cycle limit reached
- **54**: UVC module cooling — disinfection skipped

---

## Older Serial-Protocol Devices

Devices with name containing `duravit` use a UART-over-BLE protocol (not GATT services).

**Service:** `00011111-0405-0607-0809-0a0b0c0d11ff`

| Characteristic | UUID | Purpose |
|---|---|---|
| RX | `00012222-0405-0607-0809-0a0b0c0d11ff` | Receive |
| TX | `00013333-0405-0607-0809-0a0b0c0d11ff` | Transmit |
| Shake | `00014444-0405-0607-0809-0a0b0c0d11ff` | Handshake |
| TB | `00015555-0405-0607-0809-0a0b0c0d11ff` | Unknown |

### Packet Format

```
[0x55][type][opCode][payload...]
```

- Header always `0x55`
- Types: Command=`0x01`, Response=`0x02`, Event=`0x03`, Data=`0x05`

### Serial Op Codes

| Op | Hex | Command | Payload |
|---|---|---|---|
| Stop | 0x01 | Stop all | — |
| Rear Wash | 0x02 | Start rear wash | `[flow<<4 | nozzle][comfort<<4 | temp]` |
| Lady Wash | 0x03 | Start lady wash | same as rear wash |
| Drying | 0x04 | Start dryer | `[temp]` |
| Open/Close Lid | 0x09 | Toggle lid | — |
| Full Flush | 0x0B | Full flush | — |
| Eco Flush | 0x0C | Eco flush | — |
| Deodorization | 0x0D | Toggle deodorization | — |
| Comfort Wash | 0x20 | Set comfort wash | `[0/1]` |
| Nozzle Position | 0x21 | Set nozzle | `[0–4]` |
| Water Flow | 0x22 | Set flow | `[0–2]` |
| Water Temp | 0x23 | Set water temp | `[0–3]` |
| Seat Temp | 0x25 | Set seat temp | `[0–3]` |
| Night Light | 0x41 | Night light | `[lightState]` |
| Beep Tone | 0x40 | Mute/unmute | `[0/1]` |
| Human Sensing | 0x49 | Proximity sensitivity | `[value]` |
| Nozzle Self-Clean | 0x60 | Self-cleaning cycle | — |
| Nozzle Manual Clean | 0x61 | Manual nozzle clean | — |
| Tank Drainage | 0x62 | Drain tank | `[tankDrainage]` |
| Descaling | 0x63 | Start descale | — |
| Set Defaults | 0x5E | Factory reset | — |
| Water Hardness | 0x67 | Set hardness | `[0–4]` |
| Time Update | 0x2B | Sync RTC | `[YY][MM][DD][HH][mm][ss]` (YY = year-2000) |
| Toilet State Req | 0x52 | Poll state | — |
| Toilet State Resp | 0x53 | State response | 2 bitmask bytes (see below) |
| Function List Req | 0x5C | Feature caps | — |
| Function List Resp | 0x5D | Feature caps | 2 bitmask bytes |
| Error Codes Req | 0x54 | Get errors | — |
| Error Codes Resp | 0x55 | Error data | bitmask bytes |

### Toilet State Response (0x53) Bitmask

Byte 0:
- bit 0: comfortWashWashing
- bit 1: comfortWashInitializing
- bit 2: comfortWashSeated
- bit 3: comfortWashPowered
- bit 4: drying
- bit 5: dryingInitializing
- bit 6: dryingSeated
- bit 7: dryingPowered

Byte 1:
- bit 0: deodorizingPaused (0 = idle)
- bit 1: deodorizing

`isSeated = comfortWashSeated || dryingSeated`

---

## Notes

- The app includes a fully-implemented virtual toilet simulator (all models) in the release
  binary, disabled by a hardcoded `isActivated() → false` check.
- The app checks `bytes[7:9] == [0x00, 0x01]` in the serial number payload to detect
  pairing mode.
- Model identification uses article numbers from the Device Information `MODEL_NUMBER`
  characteristic matched against sets of known article numbers per model class.
- Energy saving schedules are encoded as multi-byte structures in the programmed temperature
  / UVC characteristics (format not fully decoded here).
