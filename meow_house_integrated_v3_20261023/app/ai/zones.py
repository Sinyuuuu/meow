"""Resolution-independent ROI definitions and point-to-zone mapping."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.config import settings


ZONE_LABELS = {
    "FOOD": "進食區",
    "WATER": "飲水區",
    "LITTER": "貓砂區",
    "GENERAL": "一般活動範圍",
    # Kept only so historical Prototype records remain readable.
    "REST": "休息區（舊版）",
    "ACTIVITY": "活動區（舊版）",
}

ROI_ZONES = ("FOOD", "WATER", "LITTER")

ZONE_COLORS = {
    "REST": (178, 150, 235),
    "FOOD": (128, 184, 246),
    "WATER": (226, 184, 102),
    "LITTER": (194, 157, 207),
    "ACTIVITY": (145, 190, 130),
}

@dataclass(frozen=True)
class ZoneMapper:
    """Map bounding-box center points into configured polygonal ROIs."""

    rois: dict[str, list[tuple[float, float]]]

    @classmethod
    def default(cls) -> "ZoneMapper":
        """Load normalized polygon coordinates from the configured JSON file."""
        payload = json.loads(settings.roi_config_path.read_text(encoding="utf-8"))
        expected = set(ROI_ZONES)
        if set(payload) != expected:
            raise ValueError(f"ROI config must define exactly: {sorted(expected)}")
        return cls(
            {
                zone: [(float(point[0]), float(point[1])) for point in polygon]
                for zone, polygon in payload.items()
            }
        )

    def pixel_polygons(self, width: int, height: int) -> dict[str, list[tuple[int, int]]]:
        """Convert normalized ROI points into pixel coordinates."""
        return {
            zone: [(round(x * (width - 1)), round(y * (height - 1))) for x, y in polygon]
            for zone, polygon in self.rois.items()
        }

    def locate(self, point: tuple[float, float], width: int, height: int) -> str | None:
        """Return a functional ROI, GENERAL inside the frame, or None outside it."""
        x, y = point
        if x < 0 or y < 0 or x >= width or y >= height:
            return None
        normalized = (x / max(width - 1, 1), y / max(height - 1, 1))
        for zone, polygon in self.rois.items():
            if _point_in_polygon(normalized, polygon):
                return zone
        return "GENERAL"


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon with boundary points counted as inside."""
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (xi, yi) in enumerate(polygon):
        xj, yj = polygon[j]
        if _on_segment(point, (xi, yi), (xj, yj)):
            return True
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _on_segment(p, a, b, epsilon: float = 1e-9) -> bool:
    cross = (p[1] - a[1]) * (b[0] - a[0]) - (p[0] - a[0]) * (b[1] - a[1])
    if abs(cross) > epsilon:
        return False
    return min(a[0], b[0]) - epsilon <= p[0] <= max(a[0], b[0]) + epsilon and min(
        a[1], b[1]
    ) - epsilon <= p[1] <= max(a[1], b[1]) + epsilon
