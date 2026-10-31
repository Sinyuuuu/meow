"""CLI entrypoint for webcam, MP4, or deterministic pipeline monitoring."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.ai.monitor import AIMonitor, build_detector
from app.config import settings
from app.database import init_db


def parse_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def main() -> None:
    parser = argparse.ArgumentParser(description="Meow House AI Monitor")
    parser.add_argument("--source", default=str(settings.camera_source), help="camera index or mp4 path")
    parser.add_argument("--detector", choices=("yolo", "demo-color"), default="yolo")
    parser.add_argument("--threshold", type=float, default=settings.zone_switch_seconds)
    parser.add_argument("--output", default="outputs/annotated_demo.mp4")
    parser.add_argument("--display", action="store_true", help="open an OpenCV preview; press Q to stop")
    parser.add_argument("--max-frames", type=int)
    args = parser.parse_args()
    init_db()
    source = parse_source(args.source)
    detector = build_detector(args.detector)
    monitor = AIMonitor(
        source=source,
        detector=detector,
        pet_id=settings.default_pet_id,
        threshold_seconds=args.threshold,
        output_path=PROJECT_ROOT / args.output if args.output else None,
    )
    status = monitor.run(display=args.display, max_frames=args.max_frames)
    print(
        f"Done: frames={status.frame_count}, current_zone={status.current_zone}, "
        f"message={status.message}"
    )


if __name__ == "__main__":
    main()

