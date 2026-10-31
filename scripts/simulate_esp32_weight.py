"""Exercise the existing ESP32/HX711 ingest API with idempotent samples.

The API's device-scoped ``sequence_no`` is the idempotency/event identifier.
Credentials are read only from ``MEOW_DEVICE_KEY`` and are never printed.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


WEIGHT_PATTERN_GRAMS = (100.0, 99.0, 97.0, 95.0, 90.0)
INGEST_PATH = "/api/ingest/measurements"


def build_payload(
    *,
    device_uid: str,
    sequence_no: int,
    measured_at: datetime,
    grams: float,
) -> dict[str, Any]:
    """Build one explicitly simulated payload using the production API schema."""
    return {
        "device_uid": device_uid,
        "sequence_no": sequence_no,
        "measured_at": measured_at.astimezone(timezone.utc).isoformat(),
        "raw_value": int(grams * 1_000),
        "raw_weight_grams": grams,
        "filtered_weight_grams": grams,
        "quality": "GOOD",
        "firmware_version": "python-esp32-simulator-1.0",
        "simulated": True,
    }


def safe_result(response: httpx.Response) -> tuple[bool, bool | None, str]:
    """Return safe response fields without echoing credentials or server details."""
    try:
        body = response.json()
    except ValueError:
        return False, None, "non-json response"
    accepted = body.get("accepted") is True
    duplicate = body.get("duplicate") if isinstance(body.get("duplicate"), bool) else None
    return accepted, duplicate, "accepted" if accepted else "rejected"


def send_with_retry(
    client: httpx.Client,
    *,
    payload: dict[str, Any],
    headers: dict[str, str],
    max_attempts: int,
    retry_delay: float,
    simulate_first_failure: bool,
) -> tuple[bool, bool | None]:
    """Send one payload, retrying the exact same event ID after network failure."""
    event_id = f"{payload['device_uid']}:{payload['sequence_no']}"
    for attempt in range(1, max_attempts + 1):
        if simulate_first_failure and attempt == 1:
            print(
                f"event_id={event_id} attempt={attempt} status=NETWORK_ERROR "
                "result=simulated_disconnect"
            )
            if attempt < max_attempts and retry_delay:
                time.sleep(retry_delay)
            continue
        try:
            response = client.post(INGEST_PATH, json=payload, headers=headers)
        except httpx.RequestError as exc:
            print(
                f"event_id={event_id} attempt={attempt} status=NETWORK_ERROR "
                f"result={type(exc).__name__}"
            )
            if attempt < max_attempts and retry_delay:
                time.sleep(retry_delay * attempt)
            continue

        accepted, duplicate, result = safe_result(response)
        print(
            f"event_id={event_id} attempt={attempt} http={response.status_code} "
            f"accepted={accepted} duplicate={duplicate} result={result}"
        )
        if 200 <= response.status_code < 300 and accepted:
            return True, duplicate
        if response.status_code in {400, 401, 403, 404, 409, 422}:
            return False, duplicate
        if attempt < max_attempts and retry_delay:
            time.sleep(retry_delay * attempt)
    return False, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send an idempotent ESP32/HX711 weight simulation"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--device-uid", default="TEST-ESP32-HX711-001")
    parser.add_argument("--interval", type=float, default=0.15)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=0.2)
    parser.add_argument(
        "--weights",
        default=",".join(str(weight) for weight in WEIGHT_PATTERN_GRAMS),
        help="Comma-separated gram values (default: 100,99,97,95,90)",
    )
    parser.add_argument(
        "--start-sequence",
        type=int,
        default=None,
        help="First device-scoped event ID; defaults to a unique time-based integer",
    )
    parser.add_argument(
        "--simulate-failure-index",
        type=int,
        default=2,
        help="Zero-based sample that fails once before retry; use -1 to disable",
    )
    parser.add_argument(
        "--replay-index",
        type=int,
        default=2,
        help="Zero-based sample replayed after the sequence to prove deduplication",
    )
    args = parser.parse_args()

    if args.max_attempts < 1 or args.max_attempts > 10:
        raise SystemExit("--max-attempts must be between 1 and 10")
    if args.interval < 0 or args.retry_delay < 0:
        raise SystemExit("intervals must be non-negative")
    try:
        weights = tuple(float(value.strip()) for value in args.weights.split(","))
    except ValueError as exc:
        raise SystemExit("--weights must be comma-separated numbers") from exc
    if not weights or any(weight < -500 or weight > 20_000 for weight in weights):
        raise SystemExit("--weights must contain values between -500 and 20000 grams")

    device_key = os.getenv("MEOW_DEVICE_KEY", "").strip()
    if not device_key:
        raise SystemExit("Set MEOW_DEVICE_KEY locally; the key is never printed.")

    headers = {"X-Device-Key": device_key}
    start_sequence = args.start_sequence if args.start_sequence is not None else time.time_ns()
    started = datetime.now(timezone.utc)
    payloads = [
        build_payload(
            device_uid=args.device_uid,
            sequence_no=start_sequence + index,
            measured_at=started + timedelta(seconds=index),
            grams=grams,
        )
        for index, grams in enumerate(weights)
    ]

    failures = 0
    with httpx.Client(
        base_url=args.base_url.rstrip("/"),
        timeout=args.timeout,
        follow_redirects=False,
    ) as client:
        for index, payload in enumerate(payloads):
            ok, _duplicate = send_with_retry(
                client,
                payload=payload,
                headers=headers,
                max_attempts=args.max_attempts,
                retry_delay=args.retry_delay,
                simulate_first_failure=index == args.simulate_failure_index,
            )
            failures += int(not ok)
            if args.interval:
                time.sleep(args.interval)

        if 0 <= args.replay_index < len(payloads):
            print("replay_check=begin")
            ok, duplicate = send_with_retry(
                client,
                payload=payloads[args.replay_index],
                headers=headers,
                max_attempts=args.max_attempts,
                retry_delay=args.retry_delay,
                simulate_first_failure=False,
            )
            if not ok or duplicate is not True:
                failures += 1
                print("replay_check=failed")
            else:
                print("replay_check=passed")

    if failures:
        print(f"simulation=FAILED failures={failures}")
        return 1
    print(f"simulation=PASSED samples={len(payloads)} credentials_printed=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

