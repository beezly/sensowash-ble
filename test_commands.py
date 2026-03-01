#!/usr/bin/env python3
import asyncio, sys
sys.path.insert(0, '.')
from sensowash import SensoWashClient

async def main():
    devices = await SensoWashClient.discover(timeout=10)
    if not devices:
        print('No device found'); return
    print(f'Connecting to {devices[0].name}...')
    async with SensoWashClient(devices[0].address) as t:
        info = await t.get_device_info()
        print(f'Connected: serial={info.serial_number} hw={info.hardware_revision} sw={info.software_revision}')
        state = await t.get_toilet_state_raw()
        print(f'State: {state}')
        errors = await t.get_error_codes()
        print(f'Errors: {errors}')
        print()
        print('Commands available:')
        print('  1 - rear wash')
        print('  2 - stop')
        print('  3 - flush')
        print('  4 - open lid')
        print('  5 - close lid')
        print('  6 - start dryer')
        print('  q - quit')
        while True:
            cmd = input('> ').strip()
            if cmd == 'q': break
            elif cmd == '1':
                await t.start_rear_wash()
                print('Rear wash started')
            elif cmd == '2':
                await t.stop()
                print('Stopped')
            elif cmd == '3':
                await t.flush()
                print('Flushed')
            elif cmd == '4':
                await t.open_lid()
                print('Lid opened')
            elif cmd == '5':
                await t.close_lid()
                print('Lid closed')
            elif cmd == '6':
                await t.start_dryer()
                print('Dryer started')
            state = await t.get_toilet_state_raw()
            print(f'State: {state}')

asyncio.run(main())
