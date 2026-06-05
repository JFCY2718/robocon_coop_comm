"""Tests for serial transport abstraction."""

from __future__ import annotations

import pytest

from robocon_coop_comm.serial_transport import MemorySerialTransport


class TestMemorySerialTransport:
    def test_write_and_get_written(self) -> None:
        t = MemorySerialTransport()
        n = t.write(b"\xAA\x55\x04\x01")
        assert n == 4
        assert t.get_written_data() == b"\xAA\x55\x04\x01"

    def test_write_accumulates(self) -> None:
        t = MemorySerialTransport()
        t.write(b"\xAA")
        t.write(b"\x55")
        assert t.get_written_data() == b"\xAA\x55"

    def test_read_injected_data(self) -> None:
        t = MemorySerialTransport()
        t.inject_read_data(b"\x01\x02\x03")
        assert t.read(2) == b"\x01\x02"
        assert t.read(2) == b"\x03"

    def test_read_empty_returns_empty(self) -> None:
        t = MemorySerialTransport()
        assert t.read(4) == b""

    def test_clear_written_data(self) -> None:
        t = MemorySerialTransport()
        t.write(b"\xAA\x55")
        t.clear_written_data()
        assert t.get_written_data() == b""

    def test_close_then_write_raises(self) -> None:
        t = MemorySerialTransport()
        t.close()
        with pytest.raises(IOError, match="closed"):
            t.write(b"\xAA")

    def test_close_then_read_raises(self) -> None:
        t = MemorySerialTransport()
        t.close()
        with pytest.raises(IOError, match="closed"):
            t.read(1)

    def test_close_idempotent(self) -> None:
        t = MemorySerialTransport()
        t.close()
        t.close()  # should not raise


class TestPySerialTransportImport:
    """PySerialTransport should not break module import when pyserial is absent."""

    def test_import_module_without_pyserial(self) -> None:
        import importlib
        import sys

        # Temporarily hide pyserial if it exists
        saved = sys.modules.get("serial")
        sys.modules["serial"] = None  # type: ignore[assignment]
        try:
            # Re-import to verify the module loads fine
            mod = importlib.import_module("robocon_coop_comm.serial_transport")
            # The class should be importable
            assert hasattr(mod, "PySerialTransport")
            # Constructing should raise ImportError
            with pytest.raises(ImportError, match="pyserial"):
                mod.PySerialTransport("/dev/null")
        finally:
            if saved is not None:
                sys.modules["serial"] = saved
            else:
                sys.modules.pop("serial", None)
