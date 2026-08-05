import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import from_bounds as transform_from_bounds

from mufasa import BoundingBox, Map
from mufasa.io.inputs.base import InputNode
from mufasa.io.inputs.geotiff import GeoTiffInput
from mufasa.io.outputs.python_object import MapOutput


def _dispatched_map(node, crs, bbox, res) -> Map:
    """Configure and run node; return the map received by a downstream MapOutput."""
    out = MapOutput(snapshot_interval_s=0)(node)
    node.configure(crs, bbox, res)
    out.configure(crs, bbox, res)
    node.run()
    return out.result[0]


CRS_STR  = "EPSG:32633"
BBOX     = BoundingBox(500000.0, 5200000.0, 500100.0, 5200100.0)
RES      = (10.0, 10.0)


def write_test_tiff(path, data: np.ndarray, crs_str: str = CRS_STR,
                    bbox: BoundingBox = BBOX, nodata: float | None = None):
    """Write a small single-band GeoTIFF to *path*."""
    height, width = data.shape
    transform = transform_from_bounds(
        bbox.min_x, bbox.min_y, bbox.max_x, bbox.max_y, width, height
    )
    kwargs = dict(
        driver="GTiff", height=height, width=width, count=1,
        dtype=data.dtype, crs=CRS.from_string(crs_str), transform=transform,
    )
    if nodata is not None:
        kwargs["nodata"] = nodata
    with rasterio.open(path, "w", **kwargs) as dst:
        dst.write(data[np.newaxis, :])


class TestGeoTiffInputInit:
    def test_is_file_input_mixin(self):
        assert issubclass(GeoTiffInput, InputNode)

    def test_output_type_is_map(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.ones((10, 10), dtype=np.float64))
        node = GeoTiffInput(str(p))
        assert node.output_type is Map

    def test_get_config_roundtrip(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.ones((10, 10), dtype=np.float64))
        node = GeoTiffInput(str(p))
        assert node.get_config() == {"path": str(p)}


class TestGeoTiffInputLoad:
    def test_load_returns_one_map(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.ones((10, 10), dtype=np.float64))
        result = GeoTiffInput(str(p)).items()
        assert len(result) == 1
        assert isinstance(result[0], Map)

    def test_load_data_matches_written_values(self, tmp_path):
        data = np.full((10, 10), 3.14, dtype=np.float64)
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), data)
        result = GeoTiffInput(str(p)).items()
        assert np.allclose(result[0].data, data)

    def test_load_preserves_shape(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.zeros((10, 10), dtype=np.float64))
        m = GeoTiffInput(str(p)).items()[0]
        assert m.data.shape == (10, 10)

    def test_load_without_configure_uses_native_crs(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.zeros((10, 10), dtype=np.float64))
        m = GeoTiffInput(str(p)).items()[0]
        assert m.crs == CRS.from_string(CRS_STR)

    def test_load_without_configure_uses_native_bbox(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.zeros((10, 10), dtype=np.float64))
        m = GeoTiffInput(str(p)).items()[0]
        assert m.bbox == BBOX


class TestGeoTiffInputConfigure:
    def test_configure_reprojects_to_pipeline_grid(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.ones((10, 10), dtype=np.float64))
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)
        assert m.data.shape == (10, 10)

    def test_configure_sets_correct_crs(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.zeros((10, 10), dtype=np.float64))
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)
        assert m.crs == CRS.from_string(CRS_STR)

    def test_configure_sets_correct_bbox(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.zeros((10, 10), dtype=np.float64))
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)
        assert m.bbox == BBOX

    def test_reconfigure_with_different_resolution(self, tmp_path):
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.zeros((10, 10), dtype=np.float64))
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, (5.0, 5.0))
        assert m.data.shape == (20, 20)

    def test_output_transform_matches_pipeline_template(self, tmp_path):
        """Output transform is pixel-perfectly aligned with Map.from_bounds."""
        p = tmp_path / "test.tif"
        write_test_tiff(str(p), np.ones((10, 10), dtype=np.float64))
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)
        assert m.transform == Map.from_bounds(BBOX, RES, CRS_STR).transform

    def test_source_larger_than_pipeline_bbox_is_clipped(self, tmp_path):
        """Source raster larger than pipeline bbox is cropped to the pipeline extent."""
        large_bbox = BoundingBox(
            BBOX.min_x - 50.0, BBOX.min_y - 50.0,
            BBOX.max_x + 50.0, BBOX.max_y + 50.0,
        )
        p = tmp_path / "large.tif"
        write_test_tiff(str(p), np.ones((20, 20), dtype=np.float64), bbox=large_bbox)
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)
        assert m.data.shape == (10, 10)
        assert m.bbox == BBOX
        assert np.all(m.data > 0)

    def test_source_smaller_than_pipeline_bbox_pads_zeros(self, tmp_path):
        """Area of the pipeline bbox not covered by the source is filled with 0."""
        inner_bbox = BoundingBox(
            BBOX.min_x + 50.0, BBOX.min_y + 50.0,
            BBOX.max_x,        BBOX.max_y,
        )
        p = tmp_path / "inner.tif"
        write_test_tiff(str(p), np.ones((5, 5), dtype=np.float64), bbox=inner_bbox)
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)
        assert m.data.shape == (10, 10)
        assert np.all(m.data[5:, :5] == 0.0)
        assert np.any(m.data[:5, 5:] > 0)


class TestGeoTiffInputReprojection:
    """Tests for source files in a different CRS than the pipeline."""

    def test_wgs84_source_is_reprojected_to_pipeline_crs(self, tmp_path):
        """A WGS84 source is fully reprojected to the pipeline UTM CRS."""
        t = Transformer.from_crs(CRS_STR, "EPSG:4326", always_xy=True)
        min_lon, min_lat = t.transform(BBOX.min_x, BBOX.min_y)
        max_lon, max_lat = t.transform(BBOX.max_x, BBOX.max_y)
        wgs84_bbox = BoundingBox(min_lon, min_lat, max_lon, max_lat)

        p = tmp_path / "wgs84.tif"
        write_test_tiff(str(p), np.ones((10, 10), dtype=np.float64),
                        crs_str="EPSG:4326", bbox=wgs84_bbox)
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)

        assert m.crs == CRS.from_string(CRS_STR)
        assert m.bbox == BBOX
        assert m.data.shape == (10, 10)

    def test_wgs84_source_data_is_reprojected_correctly(self, tmp_path):
        """Constant 1.0 in WGS84 reprojects to ≈1.0 across the pipeline grid."""
        t = Transformer.from_crs(CRS_STR, "EPSG:4326", always_xy=True)
        min_lon, min_lat = t.transform(BBOX.min_x, BBOX.min_y)
        max_lon, max_lat = t.transform(BBOX.max_x, BBOX.max_y)
        wgs84_bbox = BoundingBox(min_lon, min_lat, max_lon, max_lat)

        p = tmp_path / "wgs84.tif"
        write_test_tiff(str(p), np.ones((50, 50), dtype=np.float64),
                        crs_str="EPSG:4326", bbox=wgs84_bbox)
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)

        assert np.all(m.data > 0.5)


class TestGeoTiffInputNodataHandling:
    """Tests for GeoTIFFs that carry a nodata value."""

    def test_all_nodata_source_gives_zero_output(self, tmp_path):
        """A source where every pixel is nodata produces an all-zero output Map."""
        NODATA = -9999.0
        data = np.full((10, 10), NODATA, dtype=np.float32)
        p = tmp_path / "all_nodata.tif"
        write_test_tiff(str(p), data, nodata=NODATA)
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)
        assert np.all(m.data == 0.0)

    def test_partial_nodata_valid_pixels_are_preserved(self, tmp_path):
        """Valid pixels are preserved; nodata pixels become 0 in the output."""
        NODATA = -9999.0
        data = np.full((10, 10), 2.5, dtype=np.float32)
        data[:3, :] = NODATA   # top 3 rows nodata
        p = tmp_path / "partial_nodata.tif"
        write_test_tiff(str(p), data, nodata=NODATA)
        m = _dispatched_map(GeoTiffInput(str(p)), CRS_STR, BBOX, RES)
        assert np.all(m.data[0, :] == 0.0)
        assert np.allclose(m.data[5:, :], 2.5, atol=0.01)
