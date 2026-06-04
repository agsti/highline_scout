from highliner.anchors import Anchor, save_anchors, load_anchors


def test_roundtrip(tmp_path):
    anchors = [
        Anchor(x=100.0, y=200.0, elev=540.5, sectors=((80.0, 100.0, 35.0),)),
        Anchor(x=150.0, y=210.0, elev=541.0,
               sectors=((250.0, 280.0, 40.0), (10.0, 30.0, 20.0))),
    ]
    path = tmp_path / "anchors.parquet"
    save_anchors(anchors, path)
    loaded = load_anchors(path)
    assert len(loaded) == 2
    assert loaded[0].sectors == ((80.0, 100.0, 35.0),)
    assert loaded[1].x == 150.0
    assert loaded[1].sectors[0] == (250.0, 280.0, 40.0)
