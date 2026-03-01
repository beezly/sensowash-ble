"""
Custom exceptions for the sensowash library.
"""


class SensoWashError(Exception):
    """Base exception for all sensowash errors."""


class ConnectionError(SensoWashError):
    """Raised when connection to the toilet fails."""


class PairingRequired(SensoWashError):
    """Raised when a serial-protocol device needs pairing before commands will work.

    Call SensoWashClient.pair(address) to obtain a pairing key, then pass it
    as pairing_key= when constructing SensoWashClient.
    """


class PairingTimeout(SensoWashError):
    """Raised when the pairing handshake times out (button not pressed in time)."""


class CommandTimeout(SensoWashError):
    """Raised when a command sent to the toilet receives no response."""


class UnsupportedFeature(SensoWashError):
    """Raised when a method is called that this toilet model does not support."""
