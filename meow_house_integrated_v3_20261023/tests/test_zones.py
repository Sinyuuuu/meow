from app.ai.zones import ZoneMapper


def test_default_zone_centers():
    mapper = ZoneMapper.default()
    cases = {
        (100, 100): "REST",
        (500, 100): "FOOD",
        (700, 100): "WATER",
        (700, 400): "LITTER",
        (300, 400): "ACTIVITY",
    }
    for point, expected in cases.items():
        assert mapper.locate(point, 800, 500) == expected


def test_outside_returns_none():
    mapper = ZoneMapper.default()
    assert mapper.locate((-10, -10), 800, 500) is None

