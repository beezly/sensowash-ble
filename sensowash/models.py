"""
Data models and enumerations for SensoWash BLE protocol.

All values match those reverse-engineered from the official Android app.
Wire format: single unsigned byte per enum value (except where noted).
"""

from __future__ import annotations
from dataclasses import dataclass
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
