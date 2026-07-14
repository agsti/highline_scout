from highliner.etl.density.histogram import (
    bucket_for,
    bucket_overlaps,
    is_excluded,
    layer_mask,
)


def test_10m_buckets_and_upward_snapped_range_overlap() -> None:
    assert bucket_for(99.9) == 9
    assert bucket_for(100.0) == 10
    assert bucket_overlaps(2, 12.0, 98.0)
    assert not bucket_overlaps(1, 12.0, 98.0)
    assert not bucket_overlaps(10, 12.0, 98.0)


def test_mask_combines_layers_without_double_counting() -> None:
    assert layer_mask(["zepa", "enp"]) == 5
    assert is_excluded(5, layer_mask(["enp"]))
    assert not is_excluded(5, layer_mask(["zec"]))
