from app.ai.zones import ZoneMapper


def test_default_zone_centers():
    mapper = ZoneMapper.default()
    cases = {
        (100, 300): "WATER",
        (400, 300): "FOOD",
        (100, 750): "LITTER",
        (300, 550): "GENERAL",
    }
    for point, expected in cases.items():
        assert mapper.locate(point, 511, 912) == expected


def test_outside_returns_none():
    mapper = ZoneMapper.default()
    assert mapper.locate((-10, -10), 511, 912) is None

