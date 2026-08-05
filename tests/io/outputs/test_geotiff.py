import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine

from mufasa import BoundingBox, Map
from mufasa.io.outputs.base import OutputNode
from mufasa.io.outputs.geotiff import GeoTiffOutput


CRS_STR = "EPSG:32633"
BOUNDS  = BoundingBox(500000.0, 5200000.0, 500100.0, 5200100.0)
RES     = (10.0, 10.0)


def make_map(value: float = 1.0) -> Map:
    m = Map.from_bounds(BOUNDS, RES, CRS_STR)
    m.data[:] = value
    return m


class _FakePred:
    def __init__(self, m: Map):
        self._map = m
        self._successors = []

    @property
    def map(self) -> Map:
        return self._map


class TestGeoTiffOutputInit:
    def test_is_file_output_mixin(self):
        assert issubclass(GeoTiffOutput, OutputNode)

    def test_get_config_roundtrip(self, tmp_path):
        p = str(tmp_path / "out.tif")
        assert GeoTiffOutput(p).get_config() == {"path": p}


class TestGeoTiffOutputProcess:
    def test_process_stores_map_copy(self, tmp_path):
        out = GeoTiffOutput(str(tmp_path / "out.tif"))
        m = make_map(7.0)
        out._predecessors = [_FakePred(m)]
        out.process()
        assert out._map is not None
        assert out._map is not m

    def test_process_copy_is_independent(self, tmp_path):
        out = GeoTiffOutput(str(tmp_path / "out.tif"))
        m = make_map(1.0)
        out._predecessors = [_FakePred(m)]
        out.process()
        m.data[:] = 99.0
        assert out._map.data[0, 0] == 1.0

    def test_reset_clears_map(self, tmp_path):
        out = GeoTiffOutput(str(tmp_path / "out.tif"))
        out._predecessors = [_FakePred(make_map())]
        out.process()
        out.reset()
        assert out._map is None


class TestGeoTiffOutputSave:
    def test_save_writes_file(self, tmp_path):
        p = tmp_path / "out.tif"
        out = GeoTiffOutput(str(p))
        out._predecessors = [_FakePred(make_map(3.0))]
        out.process()
        out.save()
        assert p.exists()

    def test_save_no_map_is_noop(self, tmp_path):
        p = tmp_path / "out.tif"
        GeoTiffOutput(str(p)).save()
        assert not p.exists()

    def test_saved_data_matches_map(self, tmp_path):
        p = tmp_path / "out.tif"
        out = GeoTiffOutput(str(p))
        out._predecessors = [_FakePred(make_map(5.0))]
        out.process()
        out.save()
        with rasterio.open(str(p)) as src:
            data = src.read(1)
        assert np.allclose(data, 5.0)

    def test_saved_crs_matches_map(self, tmp_path):
        p = tmp_path / "out.tif"
        out = GeoTiffOutput(str(p))
        out._predecessors = [_FakePred(make_map())]
        out.process()
        out.save()
        with rasterio.open(str(p)) as src:
            assert src.crs == CRS.from_string(CRS_STR)

    def test_saved_transform_matches_map(self, tmp_path):
        p = tmp_path / "out.tif"
        m = make_map()
        out = GeoTiffOutput(str(p))
        out._predecessors = [_FakePred(m)]
        out.process()
        out.save()
        with rasterio.open(str(p)) as src:
            assert src.transform == m.transform

    def test_save_overwrites_on_second_call(self, tmp_path):
        p = tmp_path / "out.tif"
        out = GeoTiffOutput(str(p))
        pred = _FakePred(make_map(1.0))
        out._predecessors = [pred]
        out.process()
        out.save()
        pred._map = make_map(9.0)
        out.process()
        out.save()
        with rasterio.open(str(p)) as src:
            assert np.allclose(src.read(1), 9.0)
