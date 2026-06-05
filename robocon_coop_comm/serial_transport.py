"""Serial transport abstraction for R1 main controller -> LED MCU link.

Provides:
    - SerialTransport: abstract base class (protocol)
    - MemorySerialTransport: in-memory fake for testing
    - PySerialTransport: real serial port via pyserial (optional dependency)

Default tests MUST NOT open /dev/ttyUSB0 or any real serial device.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SerialTransport(ABC):
    """Abstract serial transport interface."""

    @abstractmethod
    def write(self, data: bytes) -> int:
        """Write data to the transport. Returns number of bytes written."""

    @abstractmethod
    def read(self, size: int) -> bytes:
        """Read up to *size* bytes from the transport."""

    @abstractmethod
    def close(self) -> None:
        """Close the transport."""


class MemorySerialTransport(SerialTransport):
    """In-memory serial transport for unit tests.

    - Written data is accumulated in an internal buffer.
    - Read data comes from a manually injected buffer.
    """

    def __init__(self) -> None:
        self._written = bytearray()
        self._read_buf = bytearray()
        self._closed = False

    def _check_open(self) -> None:
        if self._closed:
            raise IOError("MemorySerialTransport is closed")

    def write(self, data: bytes) -> int:
        self._check_open()
        self._written.extend(data)
        return len(data)

    def read(self, size: int) -> bytes:
        self._check_open()
        chunk = bytes(self._read_buf[:size])
        self._read_buf = self._read_buf[size:]
        return chunk

    def close(self) -> None:
        self._closed = True

    # -- test helpers --

    def get_written_data(self) -> bytes:
        """Return a copy of all data written so far."""
        return bytes(self._written)

    def clear_written_data(self) -> None:
        """Clear the written-data buffer."""
        self._written.clear()

    def inject_read_data(self, data: bytes) -> None:
        """Inject data that will be returned by subsequent read() calls."""
        self._read_buf.extend(data)


class PySerialTransport(SerialTransport):
    """Real serial port transport via pyserial.

    pyserial is NOT a default dependency. Importing this class is safe;
    constructing it raises ImportError if pyserial is not installed.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0) -> None:
        try:
            import serial  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "pyserial is required for PySerialTransport. "
                "Install it with: pip install pyserial"
            ) from None
        self._serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)

    def write(self, data: bytes) -> int:
        return self._serial.write(data)

    def read(self, size: int) -> bytes:
        return self._serial.read(size)

    def close(self) -> None:
        self._serial.close()
