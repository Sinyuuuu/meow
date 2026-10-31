from app.ai.detector import Detection


def test_detection_anchor_supports_center_and_floor_point():
    detection = Detection((10, 20, 50, 80), 0.9)
    assert detection.anchor("center") == (30, 50)
    assert detection.anchor("bottom_center") == (30, 80)
