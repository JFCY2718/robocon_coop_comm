"""Frame-level debug logger: CSV or JSONL output.

Writes one record per decoded frame, recording timestamp, msg_id, seq,
confidence, valid, and latency_ms.  Useful for real-camera debugging and
bit-error-rate analysis.

For CSV output, *extra_columns* must be declared at construction time so
the header row matches data rows exactly.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path


class FrameLogger:
    """Log decoded beacon frames to CSV or JSONL.

    Usage::

        logger = FrameLogger(
            "/tmp/beacon_log.csv", format="csv",
            extra_columns=["pattern", "bitmask", "D0", "D1", "D2"],
        )
        logger.log(
            timestamp=time.time(),
            msg_id=4, seq=1,
            valid=True, confidence=0.95,
            latency_ms=12.3,
            extra={"pattern": "111111", "bitmask": "0x3F", "D0": 1, "D1": 1, "D2": 1},
        )
        logger.close()
    """

    CSV_HEADER = [
        "timestamp",
        "msg_id",
        "seq",
        "valid",
        "confidence",
        "latency_ms",
    ]

    def __init__(
        self,
        path: str | Path,
        format: str = "csv",
        extra_columns: list[str] | None = None,
    ) -> None:
        path = Path(path)
        self._format = format.lower()
        if self._format not in ("csv", "jsonl"):
            raise ValueError(f"Unsupported format: {format!r}; use 'csv' or 'jsonl'")
        self._path = path
        self._extra_columns: list[str] = list(extra_columns) if extra_columns else []

        self._fh = open(path, "w", newline="") if self._format == "csv" else open(path, "w")
        self._csv_writer = None
        if self._format == "csv":
            self._csv_writer = csv.writer(self._fh)
            # Write the full header including extra columns up front so
            # DictReader always has matching column count.
            self._csv_writer.writerow(self.CSV_HEADER + self._extra_columns)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    @property
    def extra_columns(self) -> list[str]:
        """Extra column names declared at construction time."""
        return list(self._extra_columns)

    def log(
        self,
        *,
        timestamp: float | None = None,
        msg_id: int,
        seq: int,
        valid: bool,
        confidence: float,
        latency_ms: float,
        extra: dict | None = None,
    ) -> None:
        """Write one frame record.

        Args:
            timestamp: epoch seconds; uses ``time.time()`` if None.
            msg_id: decoded message id.
            seq: decoded sequence bit.
            valid: whether the decode passed validation.
            confidence: 0.0 – 1.0.
            latency_ms: frame-grab → decode latency in milliseconds.
            extra: additional key-value pairs.  For CSV output the keys
                must be a subset of *extra_columns* declared at init time.
        """
        if timestamp is None:
            timestamp = time.time()
        if self._format == "csv":
            row = [
                f"{timestamp:.6f}", msg_id, seq, int(valid),
                f"{confidence:.4f}", f"{latency_ms:.3f}",
            ]
            # Emit extra columns in declared order so row width matches header.
            if extra is not None:
                for col in self._extra_columns:
                    row.append(str(extra.get(col, "")))
            elif self._extra_columns:
                row.extend([""] * len(self._extra_columns))
            self._csv_writer.writerow(row)  # type: ignore[union-attr]
        else:
            record = {
                "timestamp": timestamp,
                "msg_id": msg_id,
                "seq": seq,
                "valid": valid,
                "confidence": confidence,
                "latency_ms": latency_ms,
            }
            if extra:
                record.update(extra)
            self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def close(self) -> None:
        """Flush and close the output file."""
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> "FrameLogger":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
