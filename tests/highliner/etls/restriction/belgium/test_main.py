def test_belgium_restrictions_reuse_natura_layer_ids() -> None:
    from highliner.etls.restriction.belgium import main

    assert set(main.SPECS) == {"zepa", "zec"}
