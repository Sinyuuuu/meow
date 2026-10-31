"""Generate a deterministic moving-cat marker video for pipeline verification."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


POSITIONS = [
    ("REST", (220, 160)),
    ("FOOD", (500, 130)),
    ("WATER", (700, 125)),
    ("LITTER", (690, 370)),
    ("ACTIVITY", (340, 400)),
]


def draw_cat_marker(frame: np.ndarray, center: tuple[int, int]) -> None:
    """Draw a high-saturation marker with a simple cat silhouette."""
    x, y = center
    color = (190, 20, 220)
    cv2.ellipse(frame, (x, y), (48, 38), 0, 0, 360, color, -1)
    cv2.circle(frame, (x, y - 40), 30, color, -1)
    ears = [
        np.array([(x - 25, y - 56), (x - 17, y - 86), (x - 4, y - 61)]),
        np.array([(x + 25, y - 56), (x + 17, y - 86), (x + 4, y - 61)]),
    ]
    cv2.fillPoly(frame, ears, color)
    cv2.circle(frame, (x - 10, y - 43), 3, (40, 35, 35), -1)
    cv2.circle(frame, (x + 10, y - 43), 3, (40, 35, 35), -1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/demo.mp4")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--seconds-per-zone", type=float, default=3.2)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = 800, 500
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (width, height)
    )
    frames_per_zone = round(args.fps * args.seconds_per_zone)
    for zone, center in POSITIONS:
        for frame_index in range(frames_per_zone):
            frame = np.full((height, width, 3), (241, 236, 225), dtype=np.uint8)
            frame[:] = np.linspace((248, 243, 233), (219, 205, 188), height, dtype=np.uint8)[:, None, :]
            # A one-frame wrong-position spike proves the time debouncer ignores jitter.
            point = (680, 370) if zone == "REST" and frame_index == frames_per_zone - 5 else center
            draw_cat_marker(frame, point)
            cv2.putText(frame, "Meow House A01", (26, 468), cv2.FONT_HERSHEY_SIMPLEX, .72, (82, 66, 54), 2)
            cv2.putText(frame, f"Expected: {zone}", (580, 468), cv2.FONT_HERSHEY_SIMPLEX, .58, (82, 66, 54), 2)
            writer.write(frame)
    writer.release()
    print(f"Generated {output} ({len(POSITIONS) * frames_per_zone} frames)")


if __name__ == "__main__":
    main()
