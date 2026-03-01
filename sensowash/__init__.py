"""
sensowash - Python BLE library for Duravit SensoWash toilets.

Reverse-engineered from the official Android app (com.duravit.sensowash v2.1.19).
Supports BLE GATT protocol used by modern SensoWash devices (Classic, U, Starck F Pro, i Pro).
"""

from .client import SensoWashClient
from .models import (
    WaterFlow,
    WaterTemperature,
    NozzlePosition,
    SeatTemperature,
    DryerTemperature,
    DryerSpeed,
    OnOff,
    LidState,
    FlushState,
    ErrorCode,
    ToiletState,
    DeviceInfo,
    SeatScheduleWindow,
    SeatHeatingSchedule,
    UvcScheduleTime,
    UvcSchedule,
    MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY,
    ALL_WEEKDAYS, ALL_WEEKEND, ALL_DAYS,
)
from .constants import SERVICES, CHARACTERISTICS

__version__ = "0.1.0"
__all__ = [
    "SensoWashClient",
    "WaterFlow",
    "WaterTemperature",
    "NozzlePosition",
    "SeatTemperature",
    "DryerTemperature",
    "DryerSpeed",
    "OnOff",
    "LidState",
    "FlushState",
    "ErrorCode",
    "ToiletState",
    "DeviceInfo",
    "SERVICES",
    "CHARACTERISTICS",
]
