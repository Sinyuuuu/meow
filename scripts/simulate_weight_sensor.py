"""Send an authenticated, explicitly SIMULATED HX711 sequence to FastAPI."""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone

import httpx


DEFAULT_PATTERN = (120.0, 120.2, 110.0, 110.1, 110.2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate Meow House HX711 measurements")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--device-uid", default="SIM-HX711-001")
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--start-sequence", type=int, default=int(time.time() * 1000))
    args = parser.parse_args()

    service_key = os.getenv("MEOW_SERVICE_KEY", "").strip()
    device_key = os.getenv("MEOW_DEVICE_KEY", "").strip()
    if not service_key and not device_key:
        raise SystemExit("Set MEOW_SERVICE_KEY or MEOW_DEVICE_KEY locally; no key is printed.")
    headers = {"X-Device-Key": device_key} if device_key else {"X-Service-Key": service_key}
    started = datetime.now(timezone.utc)

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=10) as client:
        for index, grams in enumerate(DEFAULT_PATTERN):
            payload = {
                "device_uid": args.device_uid,
                "sequence_no": args.start_sequence + index,
                "measured_at": (started + timedelta(seconds=index)).isoformat(),
                "raw_value": int(grams * 1000),
                "raw_weight_grams": grams,
                "filtered_weight_grams": grams,
                "quality": "GOOD",
                "firmware_version": "simulator-1.0",
                "simulated": True,
            }
            response = client.post("/api/ingest/measurements", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            print(
                f"sequence={payload['sequence_no']} grams={grams:.1f} "
                f"accepted={result['accepted']} duplicate={result['duplicate']}"
            )
            if args.interval > 0:
                time.sleep(args.interval)
    print("SIMULATED sequence complete. Check GET /api/feeding/events as an authorized user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
