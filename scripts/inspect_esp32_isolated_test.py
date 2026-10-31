"""Print a credential-free summary of the isolated ESP32 test database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "tests" / ".tmp" / "esp32_hardware_test.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect isolated ESP32 measurements")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--device-uid", default="ESP32-SIM-A01")
    args = parser.parse_args()
    database = args.database.expanduser().resolve()
    if not database.is_file():
        raise SystemExit(f"Isolated database not found: {database}")

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        device = connection.execute(
            "SELECT id FROM iot_devices WHERE device_uid = ?", (args.device_uid,)
        ).fetchone()
        if device is None:
            raise SystemExit("Test device not found")
        rows = connection.execute(
            """
            SELECT sequence_no, measured_at, filtered_weight_grams, quality, simulated
            FROM sensor_readings
            WHERE device_id = ?
            ORDER BY measured_at, id
            """,
            (device["id"],),
        ).fetchall()
        events = connection.execute(
            """
            SELECT status, estimated_consumed_grams, simulated
            FROM feeding_events
            WHERE device_id = ?
            ORDER BY started_at, id
            """,
            (device["id"],),
        ).fetchall()
    finally:
        connection.close()

    print(f"database=isolated_sqlite device_uid={args.device_uid}")
    print(f"sensor_readings={len(rows)} feeding_events={len(events)}")
    for row in rows[-20:]:
        print(
            f"sequence={row['sequence_no']} measured_at={row['measured_at']} "
            f"grams={row['filtered_weight_grams']:.1f} quality={row['quality']} "
            f"simulated={bool(row['simulated'])}"
        )
    for event in events[-10:]:
        print(
            f"feeding_status={event['status']} "
            f"estimated_grams={event['estimated_consumed_grams']:.1f} "
            f"simulated={bool(event['simulated'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

