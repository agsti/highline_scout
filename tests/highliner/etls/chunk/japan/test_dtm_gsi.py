import numpy as np

from highliner.etls.chunk.dtm_core import NODATA
from highliner.etls.chunk.japan import dtm_gsi


def test_gsi_rgb_decoder_handles_signed_heights_and_nodata() -> None:
    rgb = np.array([[[0, 128]], [[1, 0]], [[244, 0]]], dtype="uint8")
    decoded = dtm_gsi._decode(rgb)
    assert decoded[0, 0] == 5.0
    assert decoded[0, 1] == NODATA
