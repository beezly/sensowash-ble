#!/usr/bin/env python3
"""
SensoWash Occupied Monitor
==========================
Polls the seat sensor every 2 seconds and displays whether the toilet
is currently occupied, with comedy ASCII art.

Usage:
    python examples/occupied.py <address>
    SENSOWASH_KEY=aabbccdd python examples/occupied.py <address>
"""

import asyncio
import os
import sys

sys.path.insert(0, ".")
from sensowash import SensoWashClient

VACANT = r"""

        _________
       |         |
       |  FREE!  |
       |_________|
            |
       _____|_____
      /           \
     |             |
      \           /
   ____\_________/____
  |                   |
  |___________________|

     VACANT  (o_o)

"""

OCCUPIED = r"""

           \O/
            |
           /|\
       ____|_____
      /     |    \
     |      |     |
      \     |    /
   ____\____|___/____
  |                   |
  |___________________|

    OCCUPIED  (>_<)

"""

UNKNOWN = r"""

        _________
       |         |
       |    ?    |
       |_________|
            |
       _____|_____
      /           \
     |             |
      \           /
   ____\_________/____
  |                   |
  |___________________|

   UNKNOWN  (-_-)

"""


def clear():
    print("\033[2J\033[H", end="")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python examples/occupied.py <address>")
        print("       SENSOWASH_KEY=<hex> python examples/occupied.py <address>")
        sys.exit(1)

    address = sys.argv[1]
    key_hex = os.environ.get("SENSOWASH_KEY", "").strip()
    pairing_key = bytes.fromhex(key_hex) if key_hex else None

    print(f"Connecting to {address}...")
    async with SensoWashClient(address, pairing_key=pairing_key) as toilet:
        if toilet.protocol != "serial":
            print("\u26a0\ufe0f  Seat sensor is only available on serial-protocol devices.")
            print(f"   This device uses the {toilet.protocol!r} protocol.")
            sys.exit(1)

        print("Connected! Monitoring seat\u2026 (Ctrl+C to stop)")
        await asyncio.sleep(0.5)

        last_state = None
        while True:
            seated = await toilet.get_is_seated()
            if seated != last_state:
                clear()
                if seated is None:
                    print(UNKNOWN)
                elif seated:
                    print(OCCUPIED)
                else:
                    print(VACANT)
                last_state = seated
            await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\U0001f6bd  Bye!")
