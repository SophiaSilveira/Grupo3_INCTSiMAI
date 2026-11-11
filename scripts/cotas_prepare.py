"""Prepare the collected flood polygons for analysis.

Technical preparation only: the polygons come invalid from the source, which can break
spatial joins, and in degrees, which cannot be measured in meters.
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)

SOURCE_CRS = 4326
METRIC_CRS = 31982  # SIRGAS 2000 / UTM zone 22S, in meters


def prepare_cotas(raw_dir, output_path) -> gpd.GeoDataFrame:
    """Join the levels, repair the polygons, convert to meters and save as GeoParquet."""
    frames = [gpd.read_file(path) for path in sorted(Path(raw_dir).glob("*.geojson"))]
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=SOURCE_CRS)

    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf.to_crs(METRIC_CRS)

    gdf["level_m"] = (gdf["contourmax"] / 100).round(2)
    # Shape__Area and Shape__Length are in degrees, so they are not useful as measurements.
    gdf = gdf.drop(columns=["Shape__Area", "Shape__Length"])
    gdf = gdf.sort_values("level_m").reset_index(drop=True)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(output_path)
    logger.info("Saved %d levels to %s", len(gdf), output_path)
    return gdf
