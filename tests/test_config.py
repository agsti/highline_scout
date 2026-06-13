from highliner.core import config


def test_crs_constants() -> None:
    assert config.UTM_CRS == "EPSG:25831"
    assert config.WGS84_CRS == "EPSG:4326"


def test_defaults_are_sane() -> None:
    assert 40 <= config.SLOPE_MIN_DEG <= 80
    assert config.DROP_RADIUS_M > 0
    assert config.N_AZIMUTHS >= 8
    assert config.DATA_DIR.name == "data"


def test_analysis_job_constants() -> None:
    assert config.MAX_ANALYZE_TILES > 0
    assert config.HUEY_DB.name == "huey.db"
    assert config.HUEY_DB.parent == config.DATA_DIR
