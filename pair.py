#!/usr/bin/env python3
import asyncio, json, pathlib, sys
from bleak import BleakClient, BleakScanner
sys.path.insert(0, '.')
from sensowash.constants import DEVICE_NAME_PREFIXES
from sensowash.serial import CHAR_SHAKE
KEY_FILE = pathlib.Path.home() / '.sensowash_pairing_key.json'
async def main():
    print('Scanning (10s)...')
    devices = await BleakScanner.discover(timeout=10)
    found = [d for d in devices if d.name and any(d.name.lower().startswith(p.lower()) for p in DEVICE_NAME_PREFIXES)]
    if not found:
        print('No devices found.'); return
    device = found[0]
    print(f'Found: {device.name} @ {device.address}')
    async with BleakClient(device) as client:
        char_map = {c.uuid.lower(): c for svc in client.services for c in svc.characteristics}
        shake_char = char_map.get(CHAR_SHAKE)
        if not shake_char:
            print('Shake characteristic not found'); return
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        async def on_shake(_char, data: bytearray):
            if not fut.done():
                loop.call_soon_threadsafe(fut.set_result, bytes(data))
        await client.start_notify(shake_char, on_shake)
        await client.write_gatt_char(shake_char, bytes(4), response=True)
        print('Press the Bluetooth button on your toilet (waiting 30s)...')
        try:
            key = await asyncio.wait_for(fut, timeout=5.0)
            print(f'Pairing key: {key.hex()}')
            KEY_FILE.write_text(json.dumps(list(key)))
            print(f'Saved to {KEY_FILE}')
        except asyncio.TimeoutError:
            print('Timed out.')
asyncio.run(main())
