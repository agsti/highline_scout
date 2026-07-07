from highliner.core import config


def test_crs_constants() -> None:
    assert config.UTM_CRS == "EPSG:25831"
    assert config.WGS84_CRS == "EPSG:4326"


def test_defaults_are_sane() -> None:
    assert 40 <= config.SLOPE_MIN_DEG <= 80
    assert config.DROP_RADIUS_M > 0
    assert config.N_AZIMUTHS >= 8
    assert config.DATA_DIR.name == "data"


def test_chunked_precompute_constants_present() -> None:
    from highliner.core import config
    assert config.CHUNK_M > 0
    assert config.MAX_PAIR_LEN == 1000.0
    # halo must cover a full max-length line plus the sector radius
    assert config.CHUNK_HALO_M >= config.MAX_PAIR_LEN + config.DROP_RADIUS_M
    assert config.MAX_VIEW_CHUNKS > 0
    # envelope floors are looser than the strict serving defaults
    assert config.PRECOMPUTE_MIN_EXPOSURE_M <= config.DEFAULT_MIN_EXPOSURE_M
    assert config.PRECOMPUTE_MAX_DH_M >= config.DEFAULT_MAX_DH_M
    assert config.PRECOMPUTE_MIN_LEN_M <= config.DEFAULT_MIN_LEN_M
