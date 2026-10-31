import threading

import numpy as np

import app.runtime as runtime_module
from app.ai.detector import DemoColorCatDetector
from app.ai.monitor import AIMonitor
from app.runtime import MonitorManager


def test_stop_during_detector_loading_is_honored(monkeypatch):
    loading_started = threading.Event()
    release_loading = threading.Event()

    def slow_detector(_name):
        loading_started.set()
        release_loading.wait(timeout=2)
        return object()

    monkeypatch.setattr(runtime_module, "build_detector", slow_detector)
    manager = MonitorManager()
    status = manager.start(source=0, detector_name="yolo")
    assert status.message == "正在載入 AI 模型…"
    assert loading_started.wait(timeout=1)
    assert manager.get_status().message == "正在載入 AI 模型…"

    manager.stop()
    release_loading.set()
    manager._thread.join(timeout=2)

    final = manager.get_status()
    assert final.running is False
    assert final.message == "已停止監測"


def test_live_frame_callback_avoids_windows_file_replacement(monkeypatch):
    frames: list[bytes] = []
    monitor = AIMonitor(
        source=0,
        detector=DemoColorCatDetector(),
        frame_callback=frames.append,
    )

    def fail_if_disk_write_is_used(*_args, **_kwargs):
        raise AssertionError("web monitor frames should stay in memory")

    monkeypatch.setattr("app.ai.monitor.cv2.imwrite", fail_if_disk_write_is_used)
    monitor._save_live_frame(np.zeros((32, 32, 3), dtype=np.uint8))

    assert len(frames) == 1
    assert frames[0].startswith(b"\xff\xd8")
