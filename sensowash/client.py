"""
SensoWashClient — async BLE client for Duravit SensoWash toilets.

Uses bleak (cross-platform BLE) under the hood.

Quick start:
    import asyncio
    from sensowash import SensoWashClient

    async def main():
        async with SensoWashClient("AA:BB:CC:DD:EE:FF") as toilet:
            info = await toilet.get_device_info()
            print(info)
            await toilet.start_rear_wash()
            await asyncio.sleep(30)
            await toilet.stop()

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import struct
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic

import logging

from .constants import CHARACTERISTICS, DEVICE_NAME_PREFIXES

_LOGGER = logging.getLogger(__name__)
from .models import (
    DeviceInfo, ToiletState, ErrorCode, DeviceCapabilities,
    OnOff, WaterFlow, WaterTemperature, NozzlePosition,
    SeatTemperature, DryerTemperature, DryerSpeed, LidState, WaterHardness,
    SeatHeatingSchedule, UvcSchedule,
    model_name_from_article,
)
from .serial import SerialTransport, SERVICE_UUID as SERIAL_SERVICE_UUID, pair as serial_pair


def _byte(value: int) -> bytes:
    """Encode a single integer as a BLE characteristic byte."""
    return bytes([value & 0xFF])


def _read_str(data: bytes) -> str:
    try:
        return data.decode("utf-8").strip("\x00").strip()
    except Exception:
        return data.hex()


class SensoWashClient:
    """
    Async context-manager client for a SensoWash BLE device.

    Args:
        address_or_device: Bluetooth MAC address (str) or BLEDevice.
        timeout:           Connection timeout in seconds.
        notification_cb:   Optional callback(characteristic_uuid, data) for BLE
                           notifications from the toilet.
    """

    def __init__(
        self,
        address_or_device,
        timeout: float = 20.0,
        notification_cb: Optional[Callable[[str, bytes], None]] = None,
        pairing_key: Optional[bytes] = None,
    ):
        self._address = address_or_device
        self._timeout = timeout
        self._user_cb = notification_cb
        self._client: Optional[BleakClient] = None
        self._char_cache: Dict[str, BleakGATTCharacteristic] = {}
        self._serial: Optional[SerialTransport] = None  # set if serial protocol detected
        self._pairing_key = pairing_key

    @property
    def protocol(self) -> str:
        """'serial' for older UART-over-BLE models, 'gatt' for modern GATT models."""
        return "serial" if self._serial else "gatt"

    # ── Context manager ────────────────────────────────────────────────────────

    async def __aenter__(self) -> "SensoWashClient":
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect()

    # ── Connection ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """
        Connect to the toilet and auto-detect the protocol.

        Modern devices (Classic, U, Starck F Pro, i Pro) use GATT services.
        Older devices (Starck F Lite/Plus, i Lite/Plus) use a UART serial protocol
        over a proprietary BLE service — detected automatically by checking which
        services are present after connection.
        """
        self._client = BleakClient(self._address, timeout=self._timeout)
        await self._client.connect()
        self._char_cache = {}
        self._serial = None

        # Build a flat UUID → characteristic map
        for service in self._client.services:
            for char in service.characteristics:
                self._char_cache[char.uuid.lower()] = char

        # Detect protocol: check for serial service
        service_uuids = {s.uuid.lower() for s in self._client.services}
        if SERIAL_SERVICE_UUID.lower() in service_uuids:
            _LOGGER.info("Serial (UART-over-BLE) protocol detected")
            self._serial = SerialTransport(
                self._client,
                notification_cb=self._on_serial_notification,
            )
            issued_key = await self._serial.setup(pairing_key=self._pairing_key)
            if issued_key and not self._pairing_key:
                self._pairing_key = issued_key
            await self._serial.sync_time()
        else:
            _LOGGER.info("GATT protocol detected")
            await self._sync_time()
            await self._subscribe_all()

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected:
            await self._client.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    # ── Discovery ──────────────────────────────────────────────────────────────

    @staticmethod
    async def discover(timeout: float = 10.0) -> List[BLEDevice]:
        """
        Scan for SensoWash BLE devices.

        Returns a list of BLEDevice objects whose names start with a known prefix.
        """
        devices = await BleakScanner.discover(timeout=timeout)
        return [
            d for d in devices
            if d.name and any(
                d.name.lower().startswith(p.lower()) for p in DEVICE_NAME_PREFIXES
            )
        ]

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _char(self, key: str) -> Optional[BleakGATTCharacteristic]:
        uuid = CHARACTERISTICS.get(key, "").lower()
        return self._char_cache.get(uuid)

    async def _read(self, key: str) -> Optional[bytes]:
        char = self._char(key)
        if char is None:
            return None
        return bytes(await self._client.read_gatt_char(char))

    async def _write(self, key: str, data: bytes, with_response: bool = True) -> bool:
        char = self._char(key)
        if char is None:
            return False
        await self._client.write_gatt_char(char, data, response=with_response)
        return True

    async def _read_byte(self, key: str) -> Optional[int]:
        data = await self._read(key)
        if data:
            return data[0]
        return None

    async def _sync_time(self) -> None:
        """Write current local time to the Current Time characteristic."""
        char = self._char("CURRENT_TIME")
        if char is None:
            return
        now = datetime.now()
        # BLE Current Time Service format: year(2) month day hour min sec weekday(1) fractions(1) adjust(1)
        payload = struct.pack(
            "<HBBBBBBB",
            now.year, now.month, now.day,
            now.hour, now.minute, now.second,
            now.isoweekday(),  # 1=Mon … 7=Sun
            0,  # fractions256
        ) + bytes([0])  # adjust reason
        try:
            await self._client.write_gatt_char(char, payload, response=True)
        except Exception:
            pass  # not all models expose this as writable

    async def _subscribe_all(self) -> None:
        """Enable BLE notifications on all notifiable characteristics."""
        notifiable_keys = [
            "WASH_STATE", "DRYER_STATE", "DRYER_TEMPERATURE", "DRYER_SPEED",
            "FLUSH_STATE", "FLUSH_AUTOMATIC",
            "SEAT_STATE", "LID_STATE", "LID_AUTOMATIC_STATE",
            "SEAT_TEMPERATURE", "SEAT_ACTUAL_TEMP", "SEAT_PROXIMITY",
            "DEODORIZATION_STATE", "DEODORIZATION_AUTO",
            "AMBIENT_LIGHT_STATE",
            "UVC_STATE", "UVC_AUTOMATIC",
            "STOP_STATE",
            "CLEANING_STATE", "DESCALING_STATE", "ERROR_CODES",
        ]
        for key in notifiable_keys:
            char = self._char(key)
            if char is None:
                continue
            try:
                await self._client.start_notify(char, self._on_notification)
            except Exception:
                pass

    def _on_notification(self, char: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._user_cb:
            self._user_cb(char.uuid.lower(), bytes(data))

    def _on_serial_notification(self, op_code: int, payload: bytes) -> None:
        """Forward serial protocol notifications to the user callback as pseudo-UUIDs."""
        if self._user_cb:
            self._user_cb(f"serial:0x{op_code:02x}", payload)

    # ── Device Information ─────────────────────────────────────────────────────

    async def get_device_info(self) -> DeviceInfo:
        """Read manufacturer, model, serial, and revision strings."""
        if self._serial:
            info = DeviceInfo(manufacturer="Duravit")
            sn = await self._serial.get_serial_number()
            if sn:
                info.serial_number = sn
            hw = await self._serial.get_hardware_version()
            if hw:
                info.hardware_revision = hw
            sw = await self._serial.get_software_version()
            if sw:
                info.software_revision = sw
            return info

        info = DeviceInfo()
        for field, key in [
            ("manufacturer",       "MANUFACTURER_NAME"),
            ("model_number",       "MODEL_NUMBER"),
            ("serial_number",      "SERIAL_NUMBER"),
            ("hardware_revision",  "HARDWARE_REVISION"),
            ("software_revision",  "SOFTWARE_REVISION"),
            ("firmware_revision",  "FIRMWARE_REVISION"),
        ]:
            data = await self._read(key)
            if data:
                setattr(info, field, _read_str(data))
        return info

    # ── Wash functions ─────────────────────────────────────────────────────────

    async def start_rear_wash(
        self,
        water_flow: WaterFlow = WaterFlow.MEDIUM,
        water_temperature: WaterTemperature = WaterTemperature.TEMP_2,
        nozzle_position: NozzlePosition = NozzlePosition.POSITION_2,
    ) -> None:
        """Start rear wash with the given settings."""
        if self._serial:
            # Serial packet packs flow+nozzle into byte 0, comfortWash+temp into byte 1
            b0 = (water_flow.value << 4) | nozzle_position.value
            b1 = (0 << 4) | water_temperature.value  # comfortWash=0 (rear)
            from .serial import OP_REAR_WASH
            await self._serial.send(OP_REAR_WASH, bytes([b0, b1]))
        else:
            await self._write("WASH_STATE", _byte(OnOff.ON))
            await self._write("WATER_FLOW", _byte(water_flow))
            await self._write("WATER_TEMPERATURE", _byte(water_temperature))
            await self._write("NOZZLE_POSITION", _byte(nozzle_position))

    async def start_lady_wash(
        self,
        water_flow: WaterFlow = WaterFlow.MEDIUM,
        water_temperature: WaterTemperature = WaterTemperature.TEMP_2,
        nozzle_position: NozzlePosition = NozzlePosition.POSITION_2,
    ) -> None:
        """Start lady wash."""
        if self._serial:
            b0 = (water_flow.value << 4) | nozzle_position.value
            b1 = (1 << 4) | water_temperature.value  # comfortWash=1 (lady)
            from .serial import OP_LADY_WASH
            await self._serial.send(OP_LADY_WASH, bytes([b0, b1]))
        else:
            await self._write("COMFORT_WASH", _byte(OnOff.ON))
            await self._write("WATER_FLOW", _byte(water_flow))
            await self._write("WATER_TEMPERATURE", _byte(water_temperature))
            await self._write("NOZZLE_POSITION", _byte(nozzle_position))
            await self._write("WASH_STATE", _byte(OnOff.ON))

    async def stop(self) -> None:
        """Stop any currently active wash or dryer function."""
        if self._serial:
            from .serial import OP_STOP
            await self._serial.send(OP_STOP)
        else:
            await self._write("STOP_STATE", _byte(0x01))

    async def set_water_flow(self, flow: WaterFlow) -> None:
        if self._serial:
            from .serial import OP_WATER_FLOW
            await self._serial.send(OP_WATER_FLOW, bytes([flow.value]))
        else:
            await self._write("WATER_FLOW", _byte(flow))

    async def set_water_temperature(self, temp: WaterTemperature) -> None:
        if self._serial:
            from .serial import OP_WATER_TEMPERATURE
            await self._serial.send(OP_WATER_TEMPERATURE, bytes([temp.value]))
        else:
            await self._write("WATER_TEMPERATURE", _byte(temp))

    async def set_nozzle_position(self, position: NozzlePosition) -> None:
        if self._serial:
            from .serial import OP_NOZZLE_POSITION
            await self._serial.send(OP_NOZZLE_POSITION, bytes([position.value]))
        else:
            await self._write("NOZZLE_POSITION", _byte(position))

    async def get_wash_state(self) -> Optional[OnOff]:
        if self._serial:
            data = await self._serial.get_toilet_state()
            if data:
                return OnOff.ON if (data[0] & 0x01) else OnOff.OFF
            return None
        v = await self._read_byte("WASH_STATE")
        return OnOff(v) if v is not None else None

    async def get_water_flow(self) -> Optional[WaterFlow]:
        if self._serial:
            return None  # not individually readable on serial protocol
        v = await self._read_byte("WATER_FLOW")
        return WaterFlow(v) if v is not None else None

    async def get_water_temperature(self) -> Optional[WaterTemperature]:
        if self._serial:
            return None
        v = await self._read_byte("WATER_TEMPERATURE")
        return WaterTemperature(v) if v is not None else None

    async def get_nozzle_position(self) -> Optional[NozzlePosition]:
        if self._serial:
            return None
        v = await self._read_byte("NOZZLE_POSITION")
        return NozzlePosition(v) if v is not None else None

    # ── Dryer ──────────────────────────────────────────────────────────────────

    async def start_dryer(
        self,
        temperature: DryerTemperature = DryerTemperature.TEMP_2,
        speed: DryerSpeed = DryerSpeed.SPEED_0,
    ) -> None:
        if self._serial:
            from .serial import OP_DRYING
            await self._serial.send(OP_DRYING, bytes([temperature.value]))
        else:
            await self._write("DRYER_TEMPERATURE", _byte(temperature))
            await self._write("DRYER_SPEED", _byte(speed))
            await self._write("DRYER_STATE", _byte(OnOff.ON))

    async def stop_dryer(self) -> None:
        if self._serial:
            await self.stop()
        else:
            await self._write("DRYER_STATE", _byte(OnOff.OFF))

    async def set_dryer_temperature(self, temp: DryerTemperature) -> None:
        if self._serial:
            from .serial import OP_DRYING
            await self._serial.send(OP_DRYING, bytes([temp.value]))
        else:
            await self._write("DRYER_TEMPERATURE", _byte(temp))

    async def set_dryer_speed(self, speed: DryerSpeed) -> None:
        if not self._serial:
            await self._write("DRYER_SPEED", _byte(speed))
        # serial protocol has no separate speed command

    async def get_dryer_state(self) -> Optional[OnOff]:
        if self._serial:
            data = await self._serial.get_toilet_state()
            if data:
                return OnOff.ON if (data[0] & 0x10) else OnOff.OFF
            return None
        v = await self._read_byte("DRYER_STATE")
        return OnOff(v) if v is not None else None

    # ── Flush ──────────────────────────────────────────────────────────────────

    async def flush(self) -> None:
        """Trigger a manual flush."""
        if self._serial:
            from .serial import OP_FULL_FLUSH
            await self._serial.send(OP_FULL_FLUSH)
        else:
            await self._write("FLUSH_STATE", _byte(0x01))

    async def set_auto_flush(self, enabled: bool) -> None:
        if self._serial:
            from .serial import OP_AUTO_FLUSH
            await self._serial.send(OP_AUTO_FLUSH, bytes([1 if enabled else 0]))
        else:
            await self._write("FLUSH_AUTOMATIC", _byte(OnOff.ON if enabled else OnOff.OFF))

    async def set_pre_flush(self, enabled: bool) -> None:
        if self._serial:
            from .serial import OP_AUTO_PREFLUSH
            await self._serial.send(OP_AUTO_PREFLUSH, bytes([1 if enabled else 0]))
        else:
            await self._write("FLUSH_PRE_FLUSH", _byte(OnOff.ON if enabled else OnOff.OFF))

    async def get_auto_flush(self) -> Optional[bool]:
        v = await self._read_byte("FLUSH_AUTOMATIC")
        return bool(v) if v is not None else None

    # ── Seat & Lid ─────────────────────────────────────────────────────────────

    async def open_lid(self) -> None:
        if self._serial:
            from .serial import OP_OPEN_CLOSE_LID
            await self._serial.send(OP_OPEN_CLOSE_LID)
        else:
            await self._write("LID_STATE", _byte(LidState.OPEN))

    async def close_lid(self) -> None:
        if self._serial:
            from .serial import OP_OPEN_CLOSE_LID
            await self._serial.send(OP_OPEN_CLOSE_LID)
        else:
            await self._write("LID_STATE", _byte(LidState.CLOSED))

    async def get_lid_state(self) -> Optional[LidState]:
        v = await self._read_byte("LID_STATE")
        return LidState(v) if v is not None else None

    async def set_seat_temperature(self, temp: SeatTemperature) -> None:
        if self._serial:
            from .serial import OP_SEAT_TEMPERATURE
            await self._serial.send(OP_SEAT_TEMPERATURE, bytes([temp.value]))
        else:
            await self._write("SEAT_TEMPERATURE", _byte(temp))

    async def get_seat_temperature(self) -> Optional[SeatTemperature]:
        if self._serial:
            return None  # readable via function config request, not implemented yet
        v = await self._read_byte("SEAT_TEMPERATURE")
        return SeatTemperature(v) if v is not None else None

    async def get_actual_seat_temperature(self) -> Optional[int]:
        """Read the actual measured seat temperature (raw value, 0–255)."""
        return await self._read_byte("SEAT_ACTUAL_TEMP")

    async def set_proximity_detection(self, enabled: bool) -> None:
        if self._serial:
            from .serial import OP_HUMAN_SENSING
            await self._serial.send(OP_HUMAN_SENSING, bytes([1 if enabled else 0]))
        else:
            await self._write("SEAT_PROXIMITY", _byte(OnOff.ON if enabled else OnOff.OFF))

    async def get_proximity_detection(self) -> Optional[bool]:
        if self._serial:
            return None  # not individually readable on serial; use get_function_config
        v = await self._read_byte("SEAT_PROXIMITY")
        return bool(v) if v is not None else None

    async def set_seat_auto(self, enabled: bool) -> None:
        """Enable/disable automatic seat lowering."""
        if self._serial:
            from .serial import OP_AUTO_LID_SEAT_OPEN, OP_AUTO_LID_SEAT_CLOSE
            op = OP_AUTO_LID_SEAT_OPEN if enabled else OP_AUTO_LID_SEAT_CLOSE
            await self._serial.send(op, bytes([1]))
        else:
            await self._write("SEAT_AUTOMATIC", _byte(OnOff.ON if enabled else OnOff.OFF))

    # ── Deodorization ──────────────────────────────────────────────────────────

    async def set_deodorization(self, enabled: bool) -> None:
        if self._serial:
            from .serial import OP_DEODORIZATION
            await self._serial.send(OP_DEODORIZATION)  # toggle on serial
        else:
            await self._write("DEODORIZATION_STATE", _byte(OnOff.ON if enabled else OnOff.OFF))

    async def set_deodorization_auto(self, enabled: bool) -> None:
        if self._serial:
            from .serial import OP_AUTO_DEODORIZATION
            await self._serial.send(OP_AUTO_DEODORIZATION, bytes([1 if enabled else 0]))
        else:
            await self._write("DEODORIZATION_AUTO", _byte(OnOff.ON if enabled else OnOff.OFF))

    async def get_deodorization_state(self) -> Optional[bool]:
        v = await self._read_byte("DEODORIZATION_STATE")
        return bool(v) if v is not None else None

    # ── Ambient Light ──────────────────────────────────────────────────────────

    async def set_ambient_light(self, enabled: bool) -> None:
        if self._serial:
            from .serial import OP_NIGHT_LIGHT
            await self._serial.send(OP_NIGHT_LIGHT, bytes([1 if enabled else 0]))
        else:
            await self._write("AMBIENT_LIGHT_STATE", _byte(OnOff.ON if enabled else OnOff.OFF))

    async def get_ambient_light(self) -> Optional[bool]:
        if self._serial:
            return None  # not individually readable on serial
        v = await self._read_byte("AMBIENT_LIGHT_STATE")
        return bool(v) if v is not None else None

    # ── UVC Hygiene Light ──────────────────────────────────────────────────────

    async def set_uvc_light(self, enabled: bool) -> None:
        await self._write("UVC_STATE", _byte(OnOff.ON if enabled else OnOff.OFF))

    async def set_uvc_auto(self, enabled: bool) -> None:
        await self._write("UVC_AUTOMATIC", _byte(OnOff.ON if enabled else OnOff.OFF))

    async def get_uvc_state(self) -> Optional[bool]:
        v = await self._read_byte("UVC_STATE")
        return bool(v) if v is not None else None

    # ── Maintenance ────────────────────────────────────────────────────────────

    async def get_error_codes(self) -> List[ErrorCode]:
        """
        Read and decode all active error codes.
        Returns a list of ErrorCode objects (empty list = no errors).
        """
        if self._serial:
            data = await self._serial.get_error_codes()
        else:
            data = await self._read("ERROR_CODES")
        if not data:
            return []
        return ErrorCode.decode_payload(data)

    async def set_mute(self, muted: bool) -> None:
        """Mute or unmute the toilet's beep tones."""
        if self._serial:
            from .serial import OP_BEEP_TONE
            await self._serial.send(OP_BEEP_TONE, bytes([1 if muted else 0]))
        else:
            await self._write("MUTE", _byte(OnOff.ON if muted else OnOff.OFF))

    async def get_mute(self) -> Optional[bool]:
        if self._serial:
            return None  # not individually readable on serial
        v = await self._read_byte("MUTE")
        return bool(v) if v is not None else None

    async def set_water_hardness(self, hardness: WaterHardness) -> None:
        if self._serial:
            from .serial import OP_WATER_HARDNESS
            await self._serial.send(OP_WATER_HARDNESS, bytes([hardness.value]))
        else:
            await self._write("WATER_HARDNESS", _byte(hardness))

    async def get_water_hardness(self) -> Optional[WaterHardness]:
        if self._serial:
            v = await self._serial.get_water_hardness()
            return WaterHardness(v) if v is not None else None
        v = await self._read_byte("WATER_HARDNESS")
        return WaterHardness(v) if v is not None else None

    async def get_descaling_state(self) -> Optional[bytes]:
        """Raw descaling state bytes for inspection."""
        return await self._read("DESCALING_STATE")

    # ── Seat heating schedule ──────────────────────────────────────────────────

    async def get_seat_heating_schedule(self) -> Optional[SeatHeatingSchedule]:
        """
        Read the programmed seat heating schedule from the toilet.

        Returns a SeatHeatingSchedule, or None if the characteristic is unavailable.
        The toilet runs this schedule autonomously — seat heating turns on/off
        at the configured times without needing BLE connection.
        """
        if self._serial:
            cfg = await self._serial.get_function_config()
            if cfg is None:
                return None
            from .models import SeatScheduleWindow
            windows = []
            for w in cfg.get("schedule_windows", []):
                days = tuple(
                    day + 1 for day in range(7) if w["day_mask"] & (1 << day)
                )
                if days:
                    windows.append(SeatScheduleWindow(
                        from_hour=w["from_hour"],
                        from_minute=w["from_minute"],
                        to_hour=w["to_hour"],
                        to_minute=w["to_minute"],
                        days=days,
                    ))
            temp_val = cfg.get("seat_temperature") or 1
            try:
                temp = SeatTemperature(temp_val)
            except ValueError:
                temp = SeatTemperature.TEMP_1
            return SeatHeatingSchedule(
                enabled=cfg.get("energy_saving_on", False),
                temperature=temp,
                windows=windows,
            )
        data = await self._read("SEAT_TEMPERATURE_PROGRAMMED")
        if data is None:
            return None
        # The current setpoint temperature is used as the scheduled temperature
        temp_raw = await self._read_byte("SEAT_TEMPERATURE")
        try:
            temp = SeatTemperature(temp_raw) if temp_raw is not None else SeatTemperature.TEMP_1
        except ValueError:
            temp = SeatTemperature.TEMP_1
        return SeatHeatingSchedule.from_bytes(data, enabled=True, temperature=temp)

    async def set_seat_heating_schedule(self, schedule: SeatHeatingSchedule) -> None:
        """
        Write a seat heating schedule to the toilet.

        The toilet's RTC must be synced (done automatically on connect) for
        schedules to fire correctly.

        Example — warm seat on weekday mornings::

            from sensowash import SeatHeatingSchedule, SeatScheduleWindow
            from sensowash import SeatTemperature, ALL_WEEKDAYS

            schedule = SeatHeatingSchedule(
                enabled=True,
                temperature=SeatTemperature.TEMP_2,
                windows=[
                    SeatScheduleWindow(
                        from_hour=6, from_minute=30,
                        to_hour=8,   to_minute=30,
                        days=ALL_WEEKDAYS,
                    ),
                ],
            )
            await toilet.set_seat_heating_schedule(schedule)
        """
        if self._serial:
            # Serial protocol encodes schedule via OP_ENERGY_SAVING
            # Format: [temp<<4|state][n_chunks][chunk_size][day_mask][fh][fm][th][tm]...
            from .serial import OP_ENERGY_SAVING
            state_byte = (schedule.temperature.value << 4) | (1 if schedule.enabled else 0)
            entries = []
            for w in schedule.windows:
                day_mask = 0
                for d in w.days:
                    day_mask |= (1 << (d - 1))
                entries.append(bytes([day_mask, w.from_hour, w.from_minute, w.to_hour, w.to_minute]))
            # Chunk into groups of 7 (serial protocol limit per packet)
            chunks = [entries[i:i+7] for i in range(0, len(entries), 7)] or [[]]
            payload = bytes([state_byte])
            for chunk in chunks:
                payload += bytes([len(chunk)])
                for entry in chunk:
                    payload += entry
            await self._serial.send(OP_ENERGY_SAVING, payload)
            return
        payload = schedule.to_bytes()
        await self._write("SEAT_TEMPERATURE_PROGRAMMED", payload)

    async def clear_seat_heating_schedule(self) -> None:
        """Remove all seat heating schedule windows."""
        await self._write("SEAT_TEMPERATURE_PROGRAMMED", b"")

    # ── UVC light schedule ─────────────────────────────────────────────────────

    async def get_uvc_schedule(self) -> Optional[UvcSchedule]:
        """
        Read the programmed UVC / HygieneUV light schedule.

        Returns a UvcSchedule with the list of daily trigger times.
        Each trigger runs a 20-minute disinfection cycle.
        """
        data = await self._read("UVC_PROGRAMMED")
        if data is None:
            return None
        return UvcSchedule.from_bytes(data)

    async def set_uvc_schedule(self, schedule: UvcSchedule) -> None:
        """
        Write a UVC disinfection schedule to the toilet.

        Triggers fire daily at the specified times regardless of weekday.
        Each run lasts 20 minutes (fixed by firmware).

        Example — disinfect at 2am and 4am::

            from sensowash import UvcSchedule, UvcScheduleTime

            schedule = UvcSchedule(triggers=[
                UvcScheduleTime(hour=2, minute=0),
                UvcScheduleTime(hour=4, minute=0),
            ])
            await toilet.set_uvc_schedule(schedule)
        """
        await self._write("UVC_PROGRAMMED", schedule.to_bytes())

    async def set_uvc_schedule_default(self) -> None:
        """Restore UVC schedule to factory default (02:00 and 03:00 daily)."""
        await self.set_uvc_schedule(UvcSchedule.default())

    # ── Full state snapshot ────────────────────────────────────────────────────

    # ── Capabilities ───────────────────────────────────────────────────────────

    async def get_capabilities(self) -> DeviceCapabilities:
        """
        Probe the connected device's GATT profile and return a DeviceCapabilities
        object describing exactly what this toilet supports.

        Detection is based on which characteristics are present in the discovered
        GATT services — no guessing from model name.  The model name is resolved
        from the article number (Device Info Model Number characteristic) against
        Duravit's known article number table.

        Example::

            async with SensoWashClient(address) as toilet:
                caps = await toilet.get_capabilities()
                print(caps.summary())
                if caps.uvc_light:
                    await toilet.set_uvc_light(True)
        """
        def has(key: str) -> bool:
            uuid = CHARACTERISTICS.get(key, "").lower()
            return uuid in self._char_cache

        # Serial protocol: query function list from toilet
        if self._serial:
            fl = await self._serial.get_function_list() or {}
            sn = await self._serial.get_serial_number()
            return DeviceCapabilities(
                model_name="SensoWash (serial protocol)",
                article_number=sn or "",
                rear_wash=fl.get("washing", False),
                lady_wash=fl.get("washing", False),
                water_flow_control=fl.get("washing", False),
                nozzle_position_control=fl.get("washing", False),
                water_temperature_control=fl.get("washing", False),
                dryer=fl.get("drying", False),
                dryer_temperature_control=fl.get("drying", False),
                dryer_speed_control=False,  # no serial speed control
                flush=fl.get("flushing", False),
                auto_flush=fl.get("flushing", False),
                pre_flush=fl.get("flushing", False),
                seat=fl.get("seat", False),
                seat_auto=fl.get("lid", False),
                lid=fl.get("lid", False),
                lid_auto=fl.get("lid", False),
                seat_heating=fl.get("seat_heating", False),
                seat_heating_schedule=fl.get("seat_heating", False),
                proximity_detection=fl.get("human_sensor", False),
                actual_seat_temperature=False,
                deodorization=fl.get("deodorization", False),
                deodorization_auto=fl.get("deodorization", False),
                ambient_light=False,
                uvc_light=False,
                uvc_auto=False,
                uvc_schedule=False,
                descaling=fl.get("descaling", False),
                water_hardness=fl.get("descaling", False),
                mute=True,  # all serial devices support beep tone
                error_codes=True,
            )

        # Resolve model name from article number
        article = ""
        model = "Unknown"
        raw = await self._read("MODEL_NUMBER")
        if raw:
            article = _read_str(raw)
            model = model_name_from_article(article)

        return DeviceCapabilities(
            model_name=model,
            article_number=article,

            # Wash
            rear_wash=has("WASH_STATE"),
            lady_wash=has("COMFORT_WASH"),
            water_flow_control=has("WATER_FLOW"),
            nozzle_position_control=has("NOZZLE_POSITION"),
            water_temperature_control=has("WATER_TEMPERATURE"),

            # Dryer
            dryer=has("DRYER_STATE"),
            dryer_temperature_control=has("DRYER_TEMPERATURE"),
            dryer_speed_control=has("DRYER_SPEED"),

            # Flush
            flush=has("FLUSH_STATE"),
            auto_flush=has("FLUSH_AUTOMATIC"),
            pre_flush=has("FLUSH_PRE_FLUSH"),

            # Seat / lid
            seat=has("SEAT_STATE"),
            seat_auto=has("SEAT_AUTOMATIC"),
            lid=has("LID_STATE"),
            lid_auto=has("LID_AUTOMATIC_STATE"),
            seat_heating=has("SEAT_TEMPERATURE"),
            seat_heating_schedule=has("SEAT_TEMPERATURE_PROGRAMMED"),
            proximity_detection=has("SEAT_PROXIMITY"),
            actual_seat_temperature=has("SEAT_ACTUAL_TEMP"),

            # Deodorization
            deodorization=has("DEODORIZATION_STATE"),
            deodorization_auto=has("DEODORIZATION_AUTO"),

            # Lighting
            ambient_light=has("AMBIENT_LIGHT_STATE"),
            uvc_light=has("UVC_STATE"),
            uvc_auto=has("UVC_AUTOMATIC"),
            uvc_schedule=has("UVC_PROGRAMMED"),

            # Maintenance
            descaling=has("DESCALING_STATE"),
            water_hardness=has("WATER_HARDNESS"),
            mute=has("MUTE"),
            error_codes=has("ERROR_CODES"),
        )



    async def get_is_seated(self) -> Optional[bool]:
        """
        Return whether a person is currently detected as seated.

        Uses the seat sensor bits from the serial state response.
        Returns ``None`` for GATT-protocol devices (no seat sensor in the GATT profile).
        """
        state = await self.get_toilet_state_raw()
        if state is None:
            return None
        return state.get('seated', False)

    async def get_toilet_state_raw(self):
        '''Return raw toilet state dict from serial protocol, or None for GATT devices.'''  
        if self._serial:
            data = await self._serial.get_toilet_state()
            if not data or len(data) < 2:
                return None
            b0, b1 = data[0], data[1]
            return {
                'washing':              bool(b0 & 0x01),
                'wash_initializing':   bool(b0 & 0x02),
                'seated_wash':         bool(b0 & 0x04),
                'wash_powered':        bool(b0 & 0x08),
                'drying':              bool(b0 & 0x10),
                'dry_initializing':    bool(b0 & 0x20),
                'seated_dry':          bool(b0 & 0x40),
                'dry_powered':         bool(b0 & 0x80),
                'deodorizing_idle':    not bool(b1 & 0x01),
                'deodorizing':         bool(b1 & 0x01),
                'seated':              bool((b0 & 0x04) or (b0 & 0x40)),
            }
        return None

    async def get_full_state(self) -> Dict[str, Any]:
        """
        Read all readable characteristics and return a dict snapshot.
        Useful for debugging or building a dashboard.
        """
        if self._serial:
            state = await self.get_toilet_state_raw() or {}
            errors = await self.get_error_codes()
            hw = await self.get_water_hardness()
            state["water_hardness"] = hw
            state["errors"] = errors
            return state
        reads = {
            "wash_state":         ("WASH_STATE",         OnOff),
            "water_flow":         ("WATER_FLOW",         WaterFlow),
            "water_temperature":  ("WATER_TEMPERATURE",  WaterTemperature),
            "nozzle_position":    ("NOZZLE_POSITION",    NozzlePosition),
            "dryer_state":        ("DRYER_STATE",        OnOff),
            "dryer_temperature":  ("DRYER_TEMPERATURE",  DryerTemperature),
            "dryer_speed":        ("DRYER_SPEED",        DryerSpeed),
            "flush_automatic":    ("FLUSH_AUTOMATIC",    OnOff),
            "lid_state":          ("LID_STATE",          LidState),
            "seat_temperature":   ("SEAT_TEMPERATURE",   SeatTemperature),
            "seat_actual_temp":   ("SEAT_ACTUAL_TEMP",   None),
            "seat_proximity":     ("SEAT_PROXIMITY",     OnOff),
            "deodorization":      ("DEODORIZATION_STATE", OnOff),
            "deodorization_auto": ("DEODORIZATION_AUTO", OnOff),
            "ambient_light":      ("AMBIENT_LIGHT_STATE", OnOff),
            "uvc_state":          ("UVC_STATE",          OnOff),
            "mute":               ("MUTE",               OnOff),
            "water_hardness":     ("WATER_HARDNESS",     WaterHardness),
        }
        state: Dict[str, Any] = {}
        for name, (key, enum_type) in reads.items():
            raw = await self._read_byte(key)
            if raw is not None:
                state[name] = enum_type(raw) if enum_type else raw
            else:
                state[name] = None
        state["errors"] = await self.get_error_codes()
        return state
