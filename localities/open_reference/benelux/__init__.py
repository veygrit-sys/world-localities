"""Dutch and Luxembourg source projections (legacy import path)."""

from pathlib import Path

from ..published_points import FIELDS, SOURCES, indexed_paths as _indexed_paths, key, manifest, point_rows

ROOT = Path(__file__).parent
SOURCE_IDS = {country: SOURCES[country][1] for country in ("NL", "LU")}


def indexed_paths(db, countries):
    selected = SOURCE_IDS.keys() if countries is None else SOURCE_IDS.keys() & countries
    yield from _indexed_paths(db, selected)
