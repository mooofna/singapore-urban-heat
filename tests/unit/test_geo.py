import math

import numpy as np
import pytest
import rasterio
import shapely
from affine import Affine
from hypothesis import given
from hypothesis import strategies as st
from libpysal.graph import Graph

from sgheat.config import AoiConfig
from sgheat.geo import aoi, hexgrid, zonal

SPEC = hexgrid.HexGridSpec(radius_m=200.0)


class TestHexGrid:
    def test_geometry_constants(self):
        poly = SPEC.polygons(np.array([3]), np.array([-2]))[0]
        assert poly.area == pytest.approx(1.5 * math.sqrt(3) * 200.0**2)
        cx, cy = SPEC.centres(np.array([3]), np.array([-2]))
        dists = [math.dist((cx[0], cy[0]), v) for v in list(poly.exterior.coords)[:-1]]
        np.testing.assert_allclose(dists, 200.0)
        assert SPEC.flat_width_m == pytest.approx(math.sqrt(3) * 200.0)

    @given(st.integers(-500, 500), st.integers(-500, 500))
    def test_axial_round_trip(self, q, r):
        x, y = SPEC.centres(np.array([q]), np.array([r]))
        qq, rr = SPEC.axial(x, y)
        assert (qq[0], rr[0]) == (q, r)

    @given(st.floats(-1e5, 1e5), st.floats(-1e5, 1e5))
    def test_point_lies_in_its_hexagon(self, x, y):
        q, r = SPEC.axial(np.array([x]), np.array([y]))
        poly = SPEC.polygons(q, r)[0]
        assert poly.buffer(1e-6).contains(shapely.Point(x, y))

    def test_neighbours_share_one_edge(self):
        centre = SPEC.polygons(np.array([0]), np.array([0]))[0]
        for dq, dr in hexgrid.NEIGHBOUR_OFFSETS:
            other = SPEC.polygons(np.array([dq]), np.array([dr]))[0]
            shared = centre.intersection(other)
            assert shared.length == pytest.approx(200.0, rel=1e-9)
            assert shared.area == pytest.approx(0.0, abs=1e-6)

    def test_grid_tiles_without_gaps(self):
        land = shapely.box(0, 0, 5000, 3000)
        grid = hexgrid.build_grid(land, SPEC, min_land_frac=1e-9, crs=32648)
        assert grid.geometry.union_all().covers(land)
        assert grid.land_area_m2.sum() == pytest.approx(land.area, rel=1e-9)
        assert grid.geometry.area.sum() == pytest.approx(len(grid) * SPEC.area_m2)
        assert grid.zone_id.is_unique

    def test_min_land_fraction(self):
        land = shapely.box(0, 0, 5000, 3000)
        grid = hexgrid.build_grid(land, SPEC, min_land_frac=0.5, crs=32648)
        assert (grid.land_frac >= 0.5).all()
        assert (grid.land_frac <= 1 + 1e-9).all()

    def test_stable_ids(self):
        a = hexgrid.build_grid(shapely.box(0, 0, 3000, 3000), SPEC, 0.5, 32648)
        b = hexgrid.build_grid(shapely.box(-1000, 0, 3000, 3000), SPEC, 0.5, 32648)
        common = set(a.zone_id) & set(b.zone_id)
        assert len(common) == len(a)

    def test_adjacency_matches_polygon_contiguity(self):
        grid = hexgrid.build_grid(shapely.Point(0, 0).buffer(2500), SPEC, 0.5, 32648)
        focal, neighbour = hexgrid.adjacency(grid.q.to_numpy(), grid.r.to_numpy())
        ours = set(zip(focal.tolist(), neighbour.tolist(), strict=True))
        g = Graph.build_contiguity(grid.geometry.reset_index(drop=True), rook=True)
        adj = g.adjacency.reset_index()
        adj = adj[adj["weight"] > 0]
        theirs = set(zip(adj["focal"].tolist(), adj["neighbor"].tolist(), strict=True))
        assert ours == theirs
        interior_degree = np.bincount(focal).max()
        assert interior_degree == 6


class TestAoi:
    def test_grid_snaps_to_landsat_lattice(self):
        land = shapely.box(350_007.0, 140_011.0, 360_003.0, 150_002.0)
        grid = aoi.analysis_grid(land, AoiConfig())
        assert grid.transform.c % 30 == 15
        assert grid.transform.f % 30 == 15
        left, _, right, _ = grid.bounds
        assert left <= 350_007 - 1000
        assert right >= 360_003 + 1000
        landsat_2018 = Affine(30.0, 0.0, 290085.0, 0.0, -30.0, 275715.0)
        landsat_9 = Affine(30.0, 0.0, 287085.0, 0.0, -30.0, 275415.0)
        assert aoi.same_lattice(landsat_2018, grid)
        assert aoi.same_lattice(landsat_9, grid)
        assert not aoi.same_lattice(Affine(30.0, 0.0, 290100.0, 0.0, -30.0, 275715.0), grid)

    def test_land_mask(self):
        grid = aoi.PixelGrid(Affine(30, 0, 0, 0, -30, 300), width=10, height=10, crs_epsg=32648)
        mask = aoi.land_mask(shapely.box(0, 0, 150, 300), grid)
        assert mask[:, :5].all()
        assert not mask[:, 5:].any()


class TestZonal:
    grid = aoi.PixelGrid(Affine(30, 0, 0, 0, -30, 300), width=10, height=10, crs_epsg=32648)

    def coverage(self, geoms):
        ids = [f"z{i}" for i in range(len(geoms))]
        return zonal.coverage_on_grid(geoms, ids, self.grid)

    def test_constant_raster_mean(self):
        cov = self.coverage([shapely.box(10, 10, 170, 200), shapely.Point(200, 100).buffer(60)])
        mean, weight = cov.mean(np.full((10, 10), 7.5))
        np.testing.assert_allclose(mean, 7.5)
        assert weight[0] == pytest.approx(160 * 190 / 900)

    def test_all_nan_zone_is_nan_not_zero(self):
        cov = self.coverage([shapely.box(0, 0, 60, 60)])
        values = np.full((10, 10), np.nan)
        mean, weight = cov.mean(values)
        assert np.isnan(mean[0])
        assert weight[0] == 0
        assert np.isnan(cov.total(values)[0])

    def test_mask_restricts_mean(self):
        cov = self.coverage([shapely.box(0, 0, 300, 300)])
        values = np.arange(100, dtype=float).reshape(10, 10)
        mask = np.zeros((10, 10), bool)
        mask[0, 0] = True
        mean, weight = cov.mean(values, mask)
        assert mean[0] == 0.0
        assert weight[0] == 1.0

    def test_sum_is_mass_conserving(self):
        rng = np.random.default_rng(1)
        pop = rng.uniform(0, 50, (10, 10))
        spec = hexgrid.HexGridSpec(radius_m=40.0)
        hexes = hexgrid.build_grid(shapely.box(0, 0, 300, 300), spec, 1e-9, 32648)
        parts = list(hexes.land_geometry)
        cov = self.coverage(parts)
        assert np.nansum(cov.total(pop)) == pytest.approx(pop.sum(), rel=1e-6)

    def test_file_raster_cell_ids(self, tmp_path):
        path = tmp_path / "r.tif"
        data = np.arange(100, dtype="float32").reshape(10, 10)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=10,
            height=10,
            count=1,
            dtype="float32",
            crs="EPSG:32648",
            transform=Affine(30, 0, 0, 0, -30, 300),
        ) as dst:
            dst.write(data, 1)
        cov = zonal.coverage_on_raster([shapely.box(0, 0, 45, 45)], ["a"], path, 32648)
        assert cov.total(data)[0] == pytest.approx(80 * 0.5 + 81 * 0.25 + 90 * 1.0 + 91 * 0.5)

    def test_save_load(self, tmp_path):
        cov = self.coverage([shapely.box(0, 0, 100, 100), shapely.box(100, 100, 200, 300)])
        cov.save(tmp_path / "c.npz")
        back = zonal.CoverageMatrix.load(tmp_path / "c.npz")
        assert back.zone_ids == cov.zone_ids
        assert (back.matrix != cov.matrix).nnz == 0

    def test_shape_mismatch(self):
        cov = self.coverage([shapely.box(0, 0, 100, 100)])
        with pytest.raises(ValueError, match="does not match"):
            cov.mean(np.zeros((5, 5)))
