"""
Data models and enumerations for SensoWash BLE protocol.

All values match those reverse-engineered from the official Android app.
Wire format: single unsigned byte per enum value (except where noted).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional


# ── Simple enums (value = byte sent/received over BLE) ────────────────────────

class OnOff(IntEnum):
    OFF = 0
    ON  = 1


class WaterFlow(IntEnum):
    LOW    = 0
    MEDIUM = 1
    HIGH   = 2


class WaterTemperature(IntEnum):
    """4 levels of wash water temperature (0 = coolest / off)."""
    TEMP_0 = 0
    TEMP_1 = 1
    TEMP_2 = 2
    TEMP_3 = 3


class NozzlePosition(IntEnum):
    """5 nozzle positions (0 = most forward, 4 = most rear)."""
    POSITION_0 = 0
    POSITION_1 = 1
    POSITION_2 = 2
    POSITION_3 = 3
    POSITION_4 = 4


class SeatTemperature(IntEnum):
    """4 seat heating levels (0 = off)."""
    OFF    = 0
    TEMP_1 = 1
    TEMP_2 = 2
    TEMP_3 = 3


class DryerTemperature(IntEnum):
    """4 dryer temperature levels."""
    TEMP_0 = 0
    TEMP_1 = 1
    TEMP_2 = 2
    TEMP_3 = 3


class DryerSpeed(IntEnum):
    SPEED_0 = 0  # normal
    SPEED_1 = 1  # turbo


class LidState(IntEnum):
    CLOSED = 0
    OPEN   = 1


class FlushState(IntEnum):
    IDLE     = 0
    FLUSHING = 1


class WaterHardness(IntEnum):
    """Water hardness setting for descaling reminder."""
    LEVEL_0 = 0
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3
    LEVEL_4 = 4


# ── Complex / composite models ─────────────────────────────────────────────────

@dataclass
class DeviceInfo:
    manufacturer: str = ""
    model_number: str = ""
    serial_number: str = ""
    hardware_revision: str = ""
    software_revision: str = ""
    firmware_revision: str = ""

    def __str__(self) -> str:
        return (
            f"Manufacturer: {self.manufacturer}\n"
            f"Model:        {self.model_number}\n"
            f"Serial:       {self.serial_number}\n"
            f"Hardware:     {self.hardware_revision}\n"
            f"Software:     {self.software_revision}\n"
            f"Firmware:     {self.firmware_revision}"
        )


@dataclass
class ToiletState:
    """
    Decoded from the 2-byte state response.

    Byte 0 bits 0-7: wash/dryer state flags
    Byte 1 bits 0-2: deodorization state flags
    """
    is_wash_active: bool = False
    is_wash_initializing: bool = False
    is_wash_seated: bool = False
    is_wash_powered: bool = False
    is_dryer_active: bool = False
    is_dryer_initializing: bool = False
    is_dryer_seated: bool = False
    is_dryer_powered: bool = False
    is_deodorizing_idle: bool = False
    is_deodorizing_paused: bool = False
    is_deodorizing: bool = False

    @property
    def is_seated(self) -> bool:
        """True if a person is detected as seated."""
        return self.is_wash_seated or self.is_dryer_seated

    @classmethod
    def from_bytes(cls, data: bytes) -> "ToiletState":
        if len(data) < 2:
            return cls()
        b0, b1 = data[0], data[1]
        return cls(
            is_wash_active=bool(b0 & 0x01),
            is_wash_initializing=bool(b0 & 0x02),
            is_wash_seated=bool(b0 & 0x04),
            is_wash_powered=bool(b0 & 0x08),
            is_dryer_active=bool(b0 & 0x10),
            is_dryer_initializing=bool(b0 & 0x20),
            is_dryer_seated=bool(b0 & 0x40),
            is_dryer_powered=bool(b0 & 0x80),
            is_deodorizing_idle=not bool(b1 & 0x01),
            is_deodorizing_paused=bool(b1 & 0x01),
            is_deodorizing=bool(b1 & 0x02),
        )


# ── Error codes ────────────────────────────────────────────────────────────────

# Maps raw integer error code → (service_code, category, title, action)
_ERROR_TABLE = {
    1:  ("721.1", "Power Supply",              "Power supply fault",           "Switch off power, call installer"),
    2:  ("721.2", "Power Supply",              "Power supply fault",           "Switch off power, call installer"),
    3:  ("721.3", "Power Supply",              "Power supply fault",           "Switch off power, call installer"),
    4:  ("725.1", "Seat Heating",              "Seat heating fault",           "Switch off power, call installer"),
    9:  ("725.2", "Seat Heating",              "Seat heating fault",           "Switch off power, call installer"),
    10: ("725.3", "Seat Heating",              "Seat heating fault",           "Switch off power, call installer"),
    11: ("725.4", "Seat Heating",              "Seat heating fault",           "Switch off power, call installer"),
    12: ("725.6", "Seat Heating",              "Seat heating fault",           "Switch off power, call installer"),
    13: ("725.5", "Seat Heating",              "Seat heating fault",           "Switch off power, call installer"),
    17: ("735.1", "Water Supply",              "Water supply fault",           "Close stop valve, call installer"),
    18: ("735.2", "Water Supply",              "Water supply – low pressure",  "Clean water filter, check tubes; if fails: close stop valve, call installer"),
    19: ("735.3", "Water Supply",              "Water supply fault",           "Close stop valve, call installer"),
    20: ("735.4", "Water Supply",              "Water supply fault",           "Close stop valve, call installer"),
    25: ("726.2", "Water Temperature",         "Shower water temperature",     "Close stop valve, call installer"),
    26: ("726.3", "Water Temperature",         "Shower water temperature",     "Close stop valve, call installer"),
    27: ("726.5", "Water Temperature",         "Shower water temperature",     "Close stop valve, call installer"),
    28: ("726.6", "Water Temperature",         "Shower water temperature",     "Close stop valve, call installer"),
    29: ("726.1", "Water Temperature",         "Shower water temperature",     "Close stop valve, call installer"),
    30: ("726.7", "Water Temperature",         "Shower water temperature",     "Close stop valve, call installer"),
    33: ("727.1", "Warm Air Dryer",            "Dryer fault",                  "Switch off power, call installer"),
    34: ("727.2", "Warm Air Dryer",            "Dryer fault",                  "Switch off power, call installer"),
    35: ("727.3", "Warm Air Dryer",            "Dryer fault",                  "Switch off power, call installer"),
    41: ("722.1", "Gearbox",                   "Seat/lid gear fault",          "Call installer"),
    42: ("722.2", "Gearbox",                   "Seat/lid gear fault",          "Call installer"),
    49: ("746.1", "HygieneUV",                 "UVC fan abnormal",             "Dryer speed not transmitted"),
    50: ("746.2", "HygieneUV",                 "UVC circuit abnormal",         "Voltage exceeds set value"),
    51: ("746.3", "HygieneUV",                 "UVC comms abnormal",           "No feedback for 3 consecutive attempts"),
    65: ("738.3", "Flush System",              "Flushing system fault",        "Switch off power, close stop valve, call installer"),
}


@dataclass
class ErrorCode:
    code: int
    service_code: str
    category: str
    title: str
    action: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.category} – {self.title} (service ref {self.service_code})\n  → {self.action}"

    @classmethod
    def from_int(cls, code: int) -> Optional["ErrorCode"]:
        if code not in _ERROR_TABLE:
            return None
        sc, cat, title, action = _ERROR_TABLE[code]
        return cls(code=code, service_code=sc, category=cat, title=title, action=action)

    @classmethod
    def decode_payload(cls, payload: bytes) -> List["ErrorCode"]:
        """
        Decode the bitmask payload from the ERROR_CODES characteristic.
        Each bit N of byte B represents error code (B*8 + N + 1).
        """
        errors = []
        for byte_idx, byte_val in enumerate(payload):
            for bit_idx in range(8):
                if byte_val & (1 << bit_idx):
                    code = byte_idx * 8 + bit_idx + 1
                    ec = cls.from_int(code)
                    if ec:
                        errors.append(ec)
        return errors


# ── Device Capabilities ────────────────────────────────────────────────────────

# Article number → model name lookup (from VariantBleConstants.kt)
_ARTICLE_NUMBERS: dict[str, str] = {
    # SensoWash Classic EU
    "613000012004300": "SensoWash Classic EU",
    "613200012004300": "SensoWash Classic EU",
    # SensoWash Classic NonEU
    "613000012000304": "SensoWash Classic NonEU",
    "613200012000304": "SensoWash Classic NonEU",
    "613000012000300": "SensoWash Classic NonEU",
    "613200012000300": "SensoWash Classic NonEU",
    "613000011001301": "SensoWash Classic NonEU",
    "613200011001301": "SensoWash Classic NonEU",
    "613000011001300": "SensoWash Classic NonEU",
    "613000011041300": "SensoWash Classic NonEU",
    "613200011001300": "SensoWash Classic NonEU",
    "613200011041300": "SensoWash Classic NonEU",
    "613000012002300": "SensoWash Classic NonEU",
    "613000012012300": "SensoWash Classic NonEU",
    "613200012002300": "SensoWash Classic NonEU",
    "613200012012300": "SensoWash Classic NonEU",
    # SensoWash U
    "622000012002300": "SensoWash U",
    "622000012000300": "SensoWash U",
    "622000011001301": "SensoWash U",
    "622000011001300": "SensoWash U",
    "622000012000304": "SensoWash U",
    # SensoWash Starck F Pro EU
    "650002012004300": "SensoWash Starck F Pro EU",
    # SensoWash Starck F Pro NonEU
    "612002012002300": "SensoWash Starck F Pro NonEU",
    "612002012402300": "SensoWash Starck F Pro NonEU",
    "612002011001300": "SensoWash Starck F Pro NonEU",
    "612002012000300": "SensoWash Starck F Pro NonEU",
    "612002011001301": "SensoWash Starck F Pro NonEU",
    # SensoWash i Pro
    "620002002402300": "SensoWash i Pro",
    "620002012402300": "SensoWash i Pro",
    "620002022402300": "SensoWash i Pro",
    "620002032402300": "SensoWash i Pro",
    "620002042402300": "SensoWash i Pro",
    "620002001401300": "SensoWash i Pro",
    "620002011401300": "SensoWash i Pro",
    "620002001401301": "SensoWash i Pro",
    "620002011401301": "SensoWash i Pro",
    "620002002400300": "SensoWash i Pro",
    "620002012400300": "SensoWash i Pro",
}


def model_name_from_article(article_number: str) -> str:
    """Return the human-readable model name for an article number, or the raw number."""
    return _ARTICLE_NUMBERS.get(article_number.strip(), article_number)


@dataclass
class DeviceCapabilities:
    """
    Capabilities detected from the live GATT profile of a connected toilet.

    Populated by SensoWashClient.get_capabilities() — reflects which services and
    characteristics are actually present on the physical device.  Use this to know
    which features are safe to call before attempting them.

    The model_name is resolved from the article number (Device Info Model Number
    characteristic) against a known table of Duravit article numbers.
    """
    # Resolved from article number
    model_name:               str  = "Unknown"
    article_number:           str  = ""

    # Core wash
    rear_wash:                bool = False
    lady_wash:                bool = False   # comfort wash flag present
    water_flow_control:       bool = False
    nozzle_position_control:  bool = False
    water_temperature_control:bool = False

    # Dryer
    dryer:                    bool = False
    dryer_temperature_control:bool = False
    dryer_speed_control:      bool = False

    # Flush
    flush:                    bool = False
    auto_flush:               bool = False
    pre_flush:                bool = False

    # Seat / lid
    seat:                     bool = False
    seat_auto:                bool = False
    lid:                      bool = False
    lid_auto:                 bool = False
    seat_heating:             bool = False
    seat_heating_schedule:    bool = False
    proximity_detection:      bool = False
    actual_seat_temperature:  bool = False

    # Deodorization
    deodorization:            bool = False
    deodorization_auto:       bool = False

    # Lighting
    ambient_light:            bool = False
    uvc_light:                bool = False
    uvc_auto:                 bool = False
    uvc_schedule:             bool = False

    # Maintenance
    descaling:                bool = False
    water_hardness:           bool = False
    mute:                     bool = False
    error_codes:              bool = False

    def summary(self) -> str:
        """Return a human-readable capability summary."""
        lines = [
            f"Model:    {self.model_name}",
            f"Article:  {self.article_number}" if self.article_number else "",
            "",
            "── Wash ──────────────────────────",
            f"  Rear wash:               {'✓' if self.rear_wash else '✗'}",
            f"  Lady wash:               {'✓' if self.lady_wash else '✗'}",
            f"  Water flow control:      {'✓' if self.water_flow_control else '✗'}",
            f"  Nozzle position:         {'✓' if self.nozzle_position_control else '✗'}",
            f"  Water temperature:       {'✓' if self.water_temperature_control else '✗'}",
            "── Dryer ─────────────────────────",
            f"  Dryer:                   {'✓' if self.dryer else '✗'}",
            f"  Dryer temperature:       {'✓' if self.dryer_temperature_control else '✗'}",
            f"  Dryer speed:             {'✓' if self.dryer_speed_control else '✗'}",
            "── Flush ─────────────────────────",
            f"  Flush:                   {'✓' if self.flush else '✗'}",
            f"  Auto flush:              {'✓' if self.auto_flush else '✗'}",
            f"  Pre-flush:               {'✓' if self.pre_flush else '✗'}",
            "── Seat & Lid ────────────────────",
            f"  Seat:                    {'✓' if self.seat else '✗'}",
            f"  Seat auto:               {'✓' if self.seat_auto else '✗'}",
            f"  Lid:                     {'✓' if self.lid else '✗'}",
            f"  Lid auto:                {'✓' if self.lid_auto else '✗'}",
            f"  Seat heating:            {'✓' if self.seat_heating else '✗'}",
            f"  Seat heating schedule:   {'✓' if self.seat_heating_schedule else '✗'}",
            f"  Proximity detection:     {'✓' if self.proximity_detection else '✗'}",
            f"  Actual seat temp sensor: {'✓' if self.actual_seat_temperature else '✗'}",
            "── Comfort ───────────────────────",
            f"  Deodorization:           {'✓' if self.deodorization else '✗'}",
            f"  Auto deodorization:      {'✓' if self.deodorization_auto else '✗'}",
            f"  Ambient light:           {'✓' if self.ambient_light else '✗'}",
            f"  HygieneUV light:         {'✓' if self.uvc_light else '✗'}",
            f"  HygieneUV auto:          {'✓' if self.uvc_auto else '✗'}",
            f"  HygieneUV schedule:      {'✓' if self.uvc_schedule else '✗'}",
            "── Maintenance ───────────────────",
            f"  Descaling:               {'✓' if self.descaling else '✗'}",
            f"  Water hardness setting:  {'✓' if self.water_hardness else '✗'}",
            f"  Mute:                    {'✓' if self.mute else '✗'}",
            f"  Error codes:             {'✓' if self.error_codes else '✗'}",
        ]
        return "\n".join(l for l in lines if l is not None)


# ── Scheduling ─────────────────────────────────────────────────────────────────

# Day-of-week constants matching the toilet's wire values (Mon=1 … Sun=7)
MONDAY    = 1
TUESDAY   = 2
WEDNESDAY = 3
THURSDAY  = 4
FRIDAY    = 5
SATURDAY  = 6
SUNDAY    = 7

ALL_WEEKDAYS = (MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY)
ALL_WEEKEND  = (SATURDAY, SUNDAY)
ALL_DAYS     = ALL_WEEKDAYS + ALL_WEEKEND


@dataclass
class SeatScheduleWindow:
    """
    A time window during which the seat heating should be active.

    The toilet stores one entry per (day, window) pair — this class represents
    a single window that can apply to multiple days.

    Args:
        from_hour:    Start hour (0–23)
        from_minute:  Start minute (0–59)
        to_hour:      End hour (0–23)
        to_minute:    End minute (0–59)
        days:         Tuple of day constants (MONDAY–SUNDAY).  Defaults to all days.
    """
    from_hour:   int
    from_minute: int
    to_hour:     int
    to_minute:   int
    days:        tuple = field(default_factory=lambda: ALL_DAYS)

    @property
    def duration_minutes(self) -> int:
        """Duration of this window in minutes (handles midnight wrap)."""
        start = self.from_hour * 60 + self.from_minute
        end   = self.to_hour   * 60 + self.to_minute
        if end <= start:
            end += 1440  # crosses midnight
        return end - start

    def __str__(self) -> str:
        day_names = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
        days_str  = "".join(day_names[d] for d in sorted(self.days))
        return (f"{self.from_hour:02d}:{self.from_minute:02d}–"
                f"{self.to_hour:02d}:{self.to_minute:02d} [{days_str}]")


@dataclass
class SeatHeatingSchedule:
    """
    Complete energy-saving / programmed seat heating schedule.

    Args:
        enabled:         Whether scheduled control is active.
        temperature:     The seat temperature to maintain during active windows.
        windows:         List of SeatScheduleWindow entries.
    """
    enabled:     bool
    temperature: SeatTemperature
    windows:     List[SeatScheduleWindow] = field(default_factory=list)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_bytes(self) -> bytes:
        """
        Encode to the BLE wire format.

        Each (day, window) pair becomes 7 bytes:
          [dayOfWeek][fromHour][fromMinute][0x00][durationLow][durationHigh][tempValue]
        """
        out = bytearray()
        for window in self.windows:
            dur = window.duration_minutes
            dur_lo = dur & 0xFF
            dur_hi = (dur >> 8) & 0xFF
            for day in sorted(window.days):
                out += bytes([
                    day,
                    window.from_hour,
                    window.from_minute,
                    0x00,
                    dur_lo,
                    dur_hi,
                    self.temperature.value,
                ])
        return bytes(out)

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        enabled: bool = True,
        temperature: SeatTemperature = SeatTemperature.TEMP_1,
    ) -> "SeatHeatingSchedule":
        """
        Decode from the BLE wire format.

        Merges entries that share the same time window across different days
        (mirrors the app's behaviour).
        """
        windows: List[SeatScheduleWindow] = []
        entry_count = len(data) // 7
        for i in range(entry_count):
            base = i * 7
            day       = data[base]
            fh        = data[base + 1]
            fm        = data[base + 2]
            dur       = data[base + 4] | (data[base + 5] << 8)
            temp_val  = data[base + 6]
            # Recover to_hour / to_minute from duration
            total_end = fh * 60 + fm + dur
            th, tm    = divmod(total_end % 1440, 60)
            try:
                temperature = SeatTemperature(temp_val)
            except ValueError:
                pass
            # Merge into existing window with the same times, or create new
            match = next(
                (w for w in windows
                 if w.from_hour == fh and w.from_minute == fm
                 and w.to_hour == th and w.to_minute == tm),
                None,
            )
            if match:
                match.days = tuple(sorted(set(match.days) | {day}))
            else:
                windows.append(SeatScheduleWindow(fh, fm, th, tm, days=(day,)))
        return cls(enabled=enabled, temperature=temperature, windows=windows)


@dataclass
class UvcScheduleTime:
    """
    A single daily UVC disinfection trigger time.

    The cycle always runs for 20 minutes from this time.

    Args:
        hour:   Trigger hour (0–23)
        minute: Trigger minute (0–59)
    """
    hour:   int
    minute: int

    def __str__(self) -> str:
        return f"{self.hour:02d}:{self.minute:02d} (20 min cycle)"


@dataclass
class UvcSchedule:
    """
    Complete programmed UVC / HygieneUV light schedule.

    The toilet runs all triggers daily (no per-weekday control).
    Each run lasts 20 minutes.

    Args:
        triggers: List of UvcScheduleTime entries.
    """
    triggers: List[UvcScheduleTime] = field(default_factory=list)

    _CYCLE_MINUTES = 20  # fixed run duration, hardcoded in firmware

    # ── Defaults ───────────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> "UvcSchedule":
        """Factory default: 02:00 and 03:00 daily."""
        return cls(triggers=[UvcScheduleTime(2, 0), UvcScheduleTime(3, 0)])

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_bytes(self) -> bytes:
        """
        Encode to the BLE wire format.
        Each trigger is 3 bytes: [hour][minute][0x00]
        """
        out = bytearray()
        for t in self.triggers:
            out += bytes([t.hour, t.minute, 0x00])
        return bytes(out)

    @classmethod
    def from_bytes(cls, data: bytes) -> "UvcSchedule":
        """Decode from the BLE wire format (3 bytes per trigger)."""
        triggers = []
        for i in range(len(data) // 3):
            base = i * 3
            triggers.append(UvcScheduleTime(data[base], data[base + 1]))
        return cls(triggers=triggers)
