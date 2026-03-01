"""
Serial (UART-over-BLE) transport for older Duravit SensoWash devices.

Used by:  SensoWash Starck F Lite / Plus, i Lite / Plus (China/USA/Asia)
          Any device advertising as DURAVIT_BT or with name containing "duravit"

Wire format (from SerialPacket.kt / PROTOCOL.md):
    [0x55][type][opCode][payload...]

    type = 0x01 (Command) for host→toilet
         = 0x02 (Response) for toilet→host
         = 0x03 (Event)
         = 0x05 (Data)
"""

from __future__ import annotations
import json
import pathlib

import asyncio
import logging
from datetime import datetime
from typing import Callable, Dict, Optional

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from .exceptions import PairingTimeout

_LOGGER = logging.getLogger(__name__)

# ── Serial service / characteristic UUIDs ─────────────────────────────────────
SERVICE_UUID  = "00011111-0405-0607-0809-0a0b0c0d11ff"
CHAR_RX       = "00012222-0405-0607-0809-0a0b0c0d11ff"  # toilet → host (notify)
CHAR_TX       = "00013333-0405-0607-0809-0a0b0c0d11ff"  # host → toilet (write)
CHAR_SHAKE    = "00014444-0405-0607-0809-0a0b0c0d11ff"  # handshake
CHAR_TB       = "00015555-0405-0607-0809-0a0b0c0d11ff"  # unknown (TB)

# ── Packet type / op-code constants ───────────────────────────────────────────
TYPE_DATA     = 0x05

# Commands (host → toilet)
OP_STOP                  = 0x01
OP_REAR_WASH             = 0x02
OP_LADY_WASH             = 0x03
OP_DRYING                = 0x04
OP_OPEN_CLOSE_LID        = 0x09
OP_FULL_FLUSH            = 0x0B
OP_ECO_FLUSH             = 0x0C
OP_DEODORIZATION         = 0x0D
OP_COMFORT_WASH          = 0x20
OP_NOZZLE_POSITION       = 0x21
OP_WATER_FLOW            = 0x22
OP_WATER_TEMPERATURE     = 0x23
OP_SEAT_TEMPERATURE      = 0x25
OP_TIME_UPDATE           = 0x2B
OP_TOILET_STATE_REQ      = 0x52
OP_ERROR_CODES_REQ       = 0x54
OP_FUNCTION_LIST_REQ     = 0x5C
OP_FUNCTION_CONFIG_REQ   = 0x50
OP_SET_DEFAULT_SETTINGS  = 0x5E
OP_NOZZLE_SELF_CLEAN     = 0x60
OP_NOZZLE_MANUAL_CLEAN   = 0x61
OP_TANK_DRAINAGE         = 0x62
OP_DESCALING             = 0x63
OP_WATER_HARDNESS_REQ            = 0x68
OP_WATER_HARDNESS                = 0x67
OP_DESCALING_STATE_REQ           = 0x64
OP_DESCALING_STATE_RESP          = 0x65
OP_DESCALING_REMAINING_TIME_REQ  = 0x69
OP_DESCALING_REMAINING_TIME_RESP = 0x66
OP_TIME_UPDATE_REQ               = 0x2A
OP_AUTO_LID_SEAT_OPEN            = 0x43
OP_AUTO_LID_SEAT_CLOSE           = 0x44
OP_AUTO_FLUSH                    = 0x45
OP_AUTO_PREFLUSH                 = 0x46
OP_AUTO_DEODORIZATION            = 0x42
OP_AUTO_DEODORIZATION_DELAY      = 0x48
OP_BEEP_TONE                     = 0x40
OP_NIGHT_LIGHT                   = 0x41
OP_HUMAN_SENSING_DISTANCE        = 0x49
OP_ENERGY_SAVING                 = 0x47
OP_SERIAL_NUMBER_REQ     = 0x58
OP_HW_VERSION_REQ        = 0x5A
OP_SW_VERSION_REQ        = 0x56

# Responses (toilet → host)
OP_TOILET_STATE_RESP     = 0x53
OP_ERROR_CODES_RESP      = 0x55
OP_FUNCTION_LIST_RESP    = 0x5D
OP_FUNCTION_CONFIG_RESP  = 0x51
OP_WATER_HARDNESS_RESP   = 0x67
OP_DESCALING_STATE_RESP  = 0x65
OP_SERIAL_NUMBER_RESP    = 0x59
OP_HW_VERSION_RESP       = 0x5B
OP_SW_VERSION_RESP       = 0x57


def _build_packet(op_code: int, payload: bytes = b"") -> bytes:
    """
    Encode a command packet.

      [0x55][0x05][length][opCode][payload...][checksum]

    length   = len(payload) + 3
    checksum = (length + opCode + sum(payload)) & 0xFF
    """
    length   = len(payload) + 3
    checksum = (length + op_code + sum(payload)) & 0xFF
    return bytes([0x55, TYPE_DATA, length, op_code]) + payload + bytes([checksum])


def _parse_packet(data: bytes) -> Optional[tuple[int, bytes]]:
    """
    Parse a received packet: [0x55][?][length][opCode][payload...]
    Returns (opCode, payload) or None if invalid.
    """
    if len(data) < 4 or data[0] != 0x55:
        return None
    op_code = data[3]
    # Use length field to strip trailing checksum byte
    payload_len = max(0, data[2] - 3)
    payload = data[4:4 + payload_len]
    return op_code, payload



async def pair(address_or_device, timeout: float = 30.0) -> bytes:
    """
    Initiate a pairing handshake with a serial-protocol SensoWash toilet.

    Connects to the device, sends zeros to the shake characteristic, and waits
    for the toilet to respond with the pairing key (requires pressing the
    physical Bluetooth button on the unit within ``timeout`` seconds).

    Args:
        address_or_device: Bluetooth MAC / CoreBluetooth UUID / BLEDevice.
        timeout:           Seconds to wait for the toilet to respond.

    Returns:
        The pairing key as bytes. Store this and pass it as ``pairing_key``
        to :class:`SerialTransport` (or :class:`SensoWashClient`) on future
        connections.

    Raises:
        PairingTimeout: If the toilet does not respond in time (button not pressed).
        RuntimeError: If the device does not expose the serial shake characteristic.
    """
    from bleak import BleakClient
    async with BleakClient(address_or_device, timeout=20.0) as client:
        char_map = {c.uuid.lower(): c for svc in client.services for c in svc.characteristics}
        shake_char = char_map.get(CHAR_SHAKE)
        if not shake_char:
            raise RuntimeError(
                "Shake characteristic not found — is this a serial-protocol SensoWash?"
            )
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[bytes] = loop.create_future()

        async def on_shake(_char, data: bytearray):
            if not fut.done():
                loop.call_soon_threadsafe(fut.set_result, bytes(data))

        await client.start_notify(shake_char, on_shake)
        await client.write_gatt_char(shake_char, bytes(4), response=True)
        try:
            key = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            raise PairingTimeout(
                f"Toilet did not respond within {timeout}s — "
                "press the Bluetooth button on the unit to confirm pairing."
            )
        return key

class SerialTransport:
    """
    Low-level serial (UART-over-BLE) transport for older SensoWash models.

    Wraps a BleakClient and provides packet-level send/receive over the
    proprietary Duravit serial service.
    """

    def __init__(
        self,
        client: BleakClient,
        notification_cb: Optional[Callable[[int, bytes], None]] = None,
    ):
        self._client = client
        self._user_cb = notification_cb
        self._pending: Dict[int, asyncio.Future] = {}
        self._rx_char: Optional[BleakGATTCharacteristic] = None
        self._tx_char: Optional[BleakGATTCharacteristic] = None

    async def setup(self, pairing_key: Optional[bytes] = None) -> bool:
        """Subscribe to RX notifications and perform shake handshake.

        Args:
            pairing_key: Previously obtained pairing key bytes. If None, the
                         toilet will be asked to issue a new key (requires
                         pressing the physical Bluetooth button on the unit).
                         The issued key is returned by this method so the caller
                         can persist it.

        Returns True if serial service found and handshake succeeded.
        """
        char_map = {
            c.uuid.lower(): c
            for svc in self._client.services
            for c in svc.characteristics
        }
        self._rx_char = char_map.get(CHAR_RX)
        self._tx_char = char_map.get(CHAR_TX)
        shake_char = char_map.get(CHAR_SHAKE)
        if not self._rx_char or not self._tx_char:
            return False
        await self._client.start_notify(self._rx_char, self._on_notification)

        # Handshake: required before the toilet will respond to any command.
        # On first connect: write [0,0,0,0] → toilet notifies with pairing key.
        # On subsequent connects: write the stored pairing key directly.
        if shake_char:
            self._last_pairing_key = await self._handshake(shake_char, pairing_key)

        _LOGGER.debug("Serial transport ready")
        return True

    async def _handshake(
        self,
        shake_char,
        pairing_key: Optional[bytes] = None,
        timeout: float = 5.0,
    ) -> Optional[bytes]:
        """Perform the BLE shake/pairing handshake.

        If pairing_key is provided, write it directly (re-authentication).
        Otherwise initiate a new pairing and return the issued key bytes.
        """
        if pairing_key:
            _LOGGER.debug("Re-using provided pairing key")
            await self._client.write_gatt_char(shake_char, pairing_key, response=True)
            return pairing_key

        # First time: subscribe to shake notifications, write zeros, wait for key
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()

        async def on_shake(_char, data: bytearray):
            if not fut.done():
                loop.call_soon_threadsafe(fut.set_result, bytes(data))

        await self._client.start_notify(shake_char, on_shake)
        _LOGGER.debug("Shake: writing first-time pairing packet [0,0,0,0]")
        await self._client.write_gatt_char(shake_char, bytes(4), response=True)

        try:
            pairing_key = await asyncio.wait_for(fut, timeout=timeout)
            _LOGGER.debug("Shake: got pairing key %s", pairing_key.hex())
            return pairing_key
        except asyncio.TimeoutError:
            raise PairingTimeout(
                "Pairing handshake timed out — press the Bluetooth button on the toilet "
                "within the timeout window, or pass a previously obtained pairing_key="
            )

    def _on_notification(self, _: BleakGATTCharacteristic, data: bytearray) -> None:
        parsed = _parse_packet(bytes(data))
        if parsed is None:
            _LOGGER.debug("Serial: unparseable packet %s", data.hex())
            return
        op_code, payload = parsed
        _LOGGER.debug("Serial RX op=0x%02x payload=%s", op_code, payload.hex())
        # Resolve any pending await
        if op_code in self._pending:
            fut = self._pending.pop(op_code)
            if not fut.done():
                asyncio.get_event_loop().call_soon_threadsafe(fut.set_result, payload)
        # Forward to user callback
        if self._user_cb:
            self._user_cb(op_code, payload)

    async def send(self, op_code: int, payload: bytes = b"") -> None:
        """Send a command packet without waiting for a response."""
        pkt = _build_packet(op_code, payload)
        _LOGGER.debug("Serial TX op=0x%02x payload=%s", op_code, payload.hex())
        await self._client.write_gatt_char(self._tx_char, pkt, response=False)

    async def request(
        self,
        op_code: int,
        response_op: int,
        payload: bytes = b"",
        timeout: float = 5.0,
    ) -> Optional[bytes]:
        """
        Send a command and wait for a specific response op-code.
        Returns the response payload, or None on timeout.
        """
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[response_op] = fut
        await self.send(op_code, payload)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(response_op, None)
            _LOGGER.warning("Serial request op=0x%02x timed out", op_code)
            return None

    async def sync_time(self) -> None:
        """Write current time to the toilet's RTC."""
        now = datetime.now()
        payload = bytes([
            now.year - 2000,
            now.month,
            now.day,
            now.hour,
            now.minute,
            now.second,
        ])
        await self.send(OP_TIME_UPDATE, payload)

    # ── FunctionList (capability bits) ────────────────────────────────────────

    async def get_function_list(self) -> Optional[dict]:
        """
        Query the toilet's capability bitmask.

        Response byte 0:
          bit 0 = deodorizationA2
          bit 1 = flushA2
          bit 2 = humanSensor

        Response byte 1:
          bit 0 = washing
          bit 1 = lid
          bit 2 = seat
          bit 3 = deodorizationEbs
          bit 4 = drying
          bit 5 = flushingEbs
          bit 6 = seatHeating
          bit 7 = descaling
        """
        data = await self.request(OP_FUNCTION_LIST_REQ, OP_FUNCTION_LIST_RESP)
        if data is None or len(data) < 2:
            return None
        b0, b1 = data[0], data[1]
        return {
            "deodorization_a2":  bool(b0 & 0x01),
            "flush_a2":          bool(b0 & 0x02),
            "human_sensor":      bool(b0 & 0x04),
            "washing":           bool(b1 & 0x01),
            "lid":               bool(b1 & 0x02),
            "seat":              bool(b1 & 0x04),
            "deodorization":     bool(b1 & 0x08),
            "drying":            bool(b1 & 0x10),
            "flushing":          bool(b1 & 0x20),
            "seat_heating":      bool(b1 & 0x40),
            "descaling":         bool(b1 & 0x80),
        }

    # ── Device info ────────────────────────────────────────────────────────────

    async def get_serial_number(self) -> Optional[str]:
        data = await self.request(OP_SERIAL_NUMBER_REQ, OP_SERIAL_NUMBER_RESP)
        if data is None:
            return None
        # Serial number is hex-encoded bytes with last 2 chars trimmed (see factory)
        s = "".join(f"{b & 0xFF:02x}" for b in data)
        return s[:-2] if len(s) > 2 else s

    async def get_hardware_version(self) -> Optional[str]:
        data = await self.request(OP_HW_VERSION_REQ, OP_HW_VERSION_RESP)
        return data.decode("ascii", errors="replace").strip() if data else None

    async def get_software_version(self) -> Optional[str]:
        data = await self.request(OP_SW_VERSION_REQ, OP_SW_VERSION_RESP)
        return data.decode("ascii", errors="replace").strip() if data else None

    # ── State ──────────────────────────────────────────────────────────────────

    async def get_toilet_state(self) -> Optional[bytes]:
        """Raw 2-byte toilet state payload (see ToiletState.from_bytes)."""
        return await self.request(OP_TOILET_STATE_REQ, OP_TOILET_STATE_RESP)

    async def get_error_codes(self) -> Optional[bytes]:
        """Raw error code bitmask payload."""
        return await self.request(OP_ERROR_CODES_REQ, OP_ERROR_CODES_RESP)


    async def get_function_config(self) -> Optional[dict]:
        """
        Query the toilet full function configuration (op 0x50/0x51).

        Returns a dict with auto settings and seat heating schedule windows.
        Schedule window keys per entry: day_mask, from_hour, from_minute, to_hour, to_minute.
        day_mask bits: Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6.
        Seat temp is in bits 4-5 of payload[2].
        """
        data = await self.request(OP_FUNCTION_CONFIG_REQ, OP_FUNCTION_CONFIG_RESP)
        if data is None or len(data) < 2:
            return None
        b0, b1 = data[0], data[1]
        result = {
            "auto_deodorization":   bool(b0 & 0x01),
            "night_light":          (b0 >> 2) & 0x03,
            "deodorization_delay":  (b0 >> 4) & 0x03,
            "auto_preflush":        bool(b0 & 0x40),
            "auto_flush":           bool(b0 & 0x80),
            "auto_lid_close":       bool(b1 & 0x01),
            "auto_lid_open":        bool(b1 & 0x02),
            "human_sensing":        bool(b1 & 0x10),
            "proximity_state":      (b1 >> 5) & 0x03,
            "seat_temperature":     None,
            "energy_saving_on":     False,
            "schedule_windows":     [],
        }
        if len(data) > 2:
            result["seat_temperature"] = (data[2] >> 4) & 0x03
        if len(data) > 3:
            n = data[3]
            result["energy_saving_on"] = n > 0
            windows = []
            offset = 4
            for _ in range(n):
                if offset + 5 > len(data):
                    break
                day_mask, fh, fm, th, tm = data[offset:offset+5]
                windows.append({
                    "day_mask":    day_mask,
                    "from_hour":   fh,
                    "from_minute": fm,
                    "to_hour":     th,
                    "to_minute":   tm,
                })
                offset += 5
            result["schedule_windows"] = windows
        return result

    async def get_water_hardness(self) -> Optional[int]:
        data = await self.request(OP_WATER_HARDNESS_REQ, OP_WATER_HARDNESS_RESP)
        return data[0] if data else None

    async def get_descaling_state(self):
        '''Query descaling state (op 0x64/0x65). Returns DescalingState or None.
        Response: [state][a_hi][a_lo][b_hi][b_lo] (big-endian uint16s).'''
        from .models import DescalingState as _DS
        data = await self.request(OP_DESCALING_STATE_REQ, OP_DESCALING_STATE_RESP)
        if data is None:
            return None
        return _DS.from_bytes(data)

    async def get_descaling_remaining_time(self) -> Optional[int]:
        '''Query remaining descaling time in minutes (op 0x69/0x66).
        Returns minutes remaining as int, or None on timeout.'''
        data = await self.request(
            OP_DESCALING_REMAINING_TIME_REQ,
            OP_DESCALING_REMAINING_TIME_RESP,
        )
        if data is None or len(data) < 2:
            return None
        return (data[0] * 256) + data[1]

