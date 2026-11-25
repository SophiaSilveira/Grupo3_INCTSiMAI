"""Prepare the street network used by the route dashboard (Tela 2).

For every street segment, finds the lowest Guaíba level whose flood polygon touches it
(blocking_level_m). Segments never touched get no value. Also gives each segment two
node ids (its endpoints), so the dashboard can build the graph without geometry work.
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import shapely

logger = logging.getLogger(__name__)

METRIC_CRS = 31982
ROUTABLE_CLASSES = {"street", "pedestrian"}
SNAP_M = 1.0  # endpoints closer than this are treated as the same intersection


CATEGORY_NAMES = {
    "R": "Rua", "AV": "Avenida", "BC": "Beco", "AC": "Acesso", "ESTR": "Estrada", "PSG": "Passagem",
    "TRAV": "Travessa", "TRVS": "Travessa", "PCA": "Praça", "LG": "Largo", "AL": "Alameda",
    "VDT": "Viaduto", "TUN": "Túnel", "ESC": "Escadaria", "PT": "Ponte", "VIA": "Via",
}
LOWERCASE_WORDS = {"da", "das", "de", "do", "dos", "e"}


def readable(name):
    words = name.lower().split()
    return " ".join(w if i and w in LOWERCASE_WORDS else w.capitalize() for i, w in enumerate(words))


def full_name(streets):
    category = streets["category"].map(CATEGORY_NAMES).fillna(streets["category"])
    parts = [category, streets["name_prefix"].fillna(""), streets["street_name"].fillna("")]
    names = parts[0].str.cat(parts[1:], sep=" ")
    return names.map(readable)


def node_ids(points):
    return [f"{round(x / SNAP_M)}_{round(y / SNAP_M)}" for x, y in shapely.get_coordinates(points)]


def prepare_routes(cotas_path, streets_path, output_path) -> gpd.GeoDataFrame:
    cotas = gpd.read_parquet(cotas_path).to_crs(METRIC_CRS).sort_values("level_m")
    streets = gpd.read_file(streets_path)
    streets = streets[streets["feature_class"].isin(ROUTABLE_CLASSES)].to_crs(METRIC_CRS)

    out = gpd.GeoDataFrame({
        "street_code": streets["street_code"].values,
        "name": full_name(streets).values,
        "length_m": streets["length_m"].values,
        "blocking_level_m": float("nan"),
    }, geometry=streets.geometry.values, crs=METRIC_CRS)

    lines = out.geometry.values
    for level, polygon in zip(cotas["level_m"], cotas.geometry):
        shapely.prepare(polygon)
        pending = out["blocking_level_m"].isna().values
        hit = pending.copy()
        hit[pending] = shapely.intersects(polygon, lines[pending])
        out.loc[hit, "blocking_level_m"] = level

    out["node_a"] = node_ids(shapely.get_point(lines, 0))
    out["node_b"] = node_ids(shapely.get_point(lines, -1))
    out = out[out["node_a"] != out["node_b"]].to_crs(4326)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path)
    logger.info("Saved %d routable segments (%d reached by some level) to %s",
                len(out), out["blocking_level_m"].notna().sum(), output_path)
    return out
