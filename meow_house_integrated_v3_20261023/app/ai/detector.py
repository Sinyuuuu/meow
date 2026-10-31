"""Cat detector adapters for real YOLO inference and deterministic pipeline tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


@dataclass(frozen=True)
class Detection:
    bbox: tuple[int, int, int, int]
    confidence: float
    class_name: str = "cat"

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def anchor(self, mode: str = "center") -> tuple[int, int]:
        """Return the point used for ROI mapping.

        ``bottom_center`` better approximates where a cat touches the floor,
        while ``center`` preserves the simple classroom-demo interpretation.
        """
        if mode == "bottom_center":
            x1, _y1, x2, y2 = self.bbox
            return ((x1 + x2) // 2, y2)
        if mode != "center":
            raise ValueError(f"Unknown zone point mode: {mode}")
        return self.center


class CatDetector(Protocol):
    def detect(self, frame: np.ndarray) -> Detection | None: ...


class YoloCatDetector:
    """Ultralytics YOLO adapter that returns the highest-confidence cat."""

    def __init__(
        self,
        model_path: str = "yolo11n.pt",
        confidence: float = 0.35,
        image_size: int = 960,
    ):
        # Keep third-party runtime settings inside this project in restricted environments.
        runtime_dir = Path(
            os.getenv(
                "YOLO_CONFIG_DIR",
                str(Path(__file__).resolve().parents[2] / "work" / "ultralytics"),
            )
        )
        runtime_dir.mkdir(parents=True, exist_ok=True)
        os.environ["YOLO_CONFIG_DIR"] = str(runtime_dir)
        from ultralytics import YOLO

        self.model = YOLO(model_path)
        self.confidence = confidence
        self.image_size = image_size

    def detect(self, frame: np.ndarray) -> Detection | None:
        """Detect class `cat`; missing detections return None and never crash the loop."""
        results = self.model.predict(
            frame,
            classes=[15],
            conf=self.confidence,
            imgsz=self.image_size,
            verbose=False,
        )
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return None
        boxes = results[0].boxes
        best_index = int(boxes.conf.argmax().item())
        x1, y1, x2, y2 = boxes.xyxy[best_index].cpu().tolist()
        confidence = float(boxes.conf[best_index].cpu().item())
        return Detection((round(x1), round(y1), round(x2), round(y2)), confidence)


class DemoColorCatDetector:
    """Detect the magenta demo-cat marker used only for deterministic integration tests."""

    def detect(self, frame: np.ndarray) -> Detection | None:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower = np.array([140, 80, 80], dtype=np.uint8)
        upper = np.array([179, 255, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(contour) < 100:
            return None
        x, y, width, height = cv2.boundingRect(contour)
        return Detection((x, y, x + width, y + height), 0.99)
