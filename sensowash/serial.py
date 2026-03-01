"""
Serial (UART-over-BLE) transport for older Duravit SensoWash devices.

Used by:  SensoWash Starck F Lite / Plus, i Lite / Plus (China/USA/Asia)
          Any device advertising as DURAVIT_BT or with name containing "duravit"

Wire format (from SerialPacket.kt):
    [0x55][type][length][opCode][payload...][checksum]

    type     = 0x05 (typeData) for all commands
    length   = len(payload) + 3
    checksum = (length + opCode + sum(payload)) & 0xFF
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, Dict, Optional

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

_LOGGER = logging.getLogger(__name__)

# ── Serial service / characteristic UUIDs ─────────────────────────────────────
SERVICE_UUID  = "00011111-0405-0607-0809-0a0b0c0d11ff"
CHAR_RX       = "00012222-0405-0607-0809-0a0b0c0d11ff"  # toilet → host (notify)
CHAR_TX       = "00013333-0405-0607-0809-0a0b0c0d11ff"  # host → toilet (write)
CHAR_SHAKE    = "00014444-0405-0607-0809-0a0b0c0d11ff"  # handshake

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
OP_WATER_HARDNESS_REQ    = 0x68
OP_WATER_HARDNESS        = 0x67
OP_AUTO_LID_OPEN         = 0x43
OP_AUTO_LID_CLOSE        = 0x44
OP_AUTO_FLUSH            = 0x45
OP_AUTO_PREFLUSH         = 0x46
OP_AUTO_DEODORIZATION    = 0x42
OP_BEEP_TONE             = 0x40
OP_NIGHT_LIGHT           = 0x41
OP_HUMAN_SENSING         = 0x49
OP_ENERGY_SAVING         = 0x47
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
    Parse a received packet.  Returns (opCode, payload) or None if invalid.
    """
    if len(data) < 5 or data[0] != 0x55:
        return None
    op_code = data[3]
    length  = data[2]
    payload_end = 3 + length - 2  # length includes opCode + checksum
    payload = data[4:payload_end + 1]
    return op_code, payload


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

    async def setup(self) -> bool:
        """Subscribe to RX notifications.  Returns True if serial service found."""
        char_map = {
            c.uuid.lower(): c
            for svc in self._client.services
            for c in svc.characteristics
        }
        self._rx_char = char_map.get(CHAR_RX)
        self._tx_char = char_map.get(CHAR_TX)
        if not self._rx_char or not self._tx_char:
            return False
        await self._client.start_notify(self._rx_char, self._on_notification)
        _LOGGER.debug("Serial transport ready")
        return True

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
                fut.get_event_loop().call_soon_threadsafe(fut.set_result, payload)
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

    async def get_water_hardness(self) -> Optional[int]:
        data = await self.request(OP_WATER_HARDNESS_REQ, OP_WATER_HARDNESS_RESP)
        return data[0] if data else None
