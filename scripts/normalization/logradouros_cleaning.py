"""Cleaning library for the street centerlines (Eixos de Logradouros) of Porto Alegre.

Reads the raw ZIP saved by logradouro_collect.py (never modified) and writes
dados/processados/logradouros.geojson (clean segments, EPSG:4326).

One function per step, like inct_cleaning.py:
    1. load_raw_streets     read the shapefile straight from the ZIP
    2. normalize_streets    keep useful columns, readable names, standard text (no rows removed)
    3. apply_corrections    remove what cannot be used, classify the rest, compute length, reproject
    4. save_outputs         write the GeoJSON

Data dictionary: Metadados_Logradouros.zip (same page). It documents the field names but NOT the
codes of CDTIPO ("situação") and CDIDECAT ("categoria"); the classes below come from inspecting
the data and are hypotheses to confirm with the Prefeitura.
"""
from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np

logger = logging.getLogger(__name__)

RAW_ZIP = Path("dados/originais/logradouros/Shapefile_Logradouros.zip")
SHP_NAME = "EixosLogradouros.shp"
OUTPUT_GEOJSON = Path("dados/processados/logradouros.geojson")
TARGET_CRS = "EPSG:4326"

# Raw column -> clean name. Dropped: CDIDELOG (always equal to CDLOG), GEOM_LEN (always 0),
# SEL and LABEL (map-editing helpers), FGCOMP, NMIDEABR (abbreviation, NMIDELOG has the full name).
COLUMNS = {
    "CDLOG": "street_code",        # Código do Logradouro
    "CDSEG": "segment_code",       # segment code (not in the dictionary)
    "CDIDECAT": "category",        # Categoria do Logradouro (R, AV, PCA, LAGO, ...)
    "NMIDEPRE": "name_prefix",     # Complemento do nome (DA, DO, DOS...)
    "NMIDELOG": "street_name",     # Nome do Logradouro
    "CDTIPO": "status_code",       # Situação do Logradouro (codes not documented)
    "NRIMPINI": "odd_start", "NRIMPFIN": "odd_end",
    "NRPARINI": "even_start", "NRPARFIN": "even_end",
    "MTORIGEM": "source_method",   # BASE 1:1000, IMAGEM...
    "MTQUAL": "quality",           # CONFIAVEL, DUVIDOSO, VIRTUAL...
    "MTVETOR": "edit_note",        # MOVIDO, QUEBRADO, EXCLUIR, PROBLEMA - SOLUCAO FUTURA...
}
VALID_QUALITY = {"CONFIAVEL", "DUVIDOSO", "VIRTUAL", "IMAGEM"}

# Hypotheses from the data (see module docstring).
NON_STREET_STATUS = {1}                                   # lakes, islands, streams, property limits
NON_STREET_CATEGORIES = {"LAGO", "I", "RIO", "AR", "CN"}  # Guaíba shore, islands, rivers, arroios, canals
PEDESTRIAN_CATEGORIES = {"ESC", "PSL", "CICL"}            # stairs, footbridges, bike paths
AREA_OUTLINE_STATUS = {3}                                 # squares and parks drawn as closed outlines

MIN_LENGTH_M = 1.0             # shorter segments are probably digitizing leftovers


# --- Step 1: Load raw data ---------------------------------------------------
def load_raw_streets(zip_path: Path = RAW_ZIP) -> gpd.GeoDataFrame:
    """Read the shapefile from the ZIP. Text encoding comes from the .CPG (UTF-8)."""
    gdf = gpd.read_file(f"zip://{Path(zip_path).resolve()}!{SHP_NAME}")
    logger.info("Loaded %d segments, CRS: %s", len(gdf), gdf.crs.name if gdf.crs else None)
    return gdf


# --- Step 2: Normalization ---------------------------------------------------
def normalize_streets(raw: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep useful columns with readable names and standardize text. No row is removed."""
    # 2.1 Keep 13 of the 19 columns (drop always-equal, always-zero and map-editing fields) and rename them.
    out = raw[[*COLUMNS, "geometry"]].rename(columns=COLUMNS)

    # 2.2 Collapse repeated spaces in names (17), so one street does not appear under two spellings.
    for field in ["street_name", "name_prefix", "category"]:
        out[field] = out[field].str.replace(r"\s+", " ", regex=True).str.strip()

    # 2.3 Write quality in uppercase (2 'confiavel'), so it falls in the same category as the rest.
    quality = out["quality"].str.strip().str.upper()

    # 2.4 Set unknown quality codes to null (7: '620', '540', '76', '0'...).
    out["quality"] = quality.where(quality.isna() | quality.isin(VALID_QUALITY))

    # 2.5 Uppercase edit notes too (2 'movido'), for the same reason as 2.3.
    out["edit_note"] = out["edit_note"].str.strip().str.upper()
    return out


# --- Step 3: Corrections -----------------------------------------------------
def apply_corrections(df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Remove only what cannot be used; everything else is kept and classified."""
    # 3.1 Remove segments without geometry (17): they cannot be mapped or intersected with the flood.
    out = df[df.geometry.notna() & ~df.geometry.is_empty]

    # 3.2 Remove exact copies of another segment (2), keeping the first, so no street is counted twice.
    out = out[~out.geometry.to_wkb().duplicated(keep="first")]

    # 3.3 Remove segments shorter than 1 m (4): digitizing leftovers that only add noise to the graph.
    out = out[out.geometry.length >= MIN_LENGTH_M].copy()

    # 3.4 Classify what is not a street (islands, lakes, rivers, park outlines, stairs) instead of deleting it.
    out["feature_class"] = np.select(
        [out["status_code"].isin(NON_STREET_STATUS) | out["category"].isin(NON_STREET_CATEGORIES),
         out["category"].isin(PEDESTRIAN_CATEGORIES),
         out["status_code"].isin(AREA_OUTLINE_STATUS)],
        ["not_street", "pedestrian", "area_outline"], default="street")

    # 3.5 Flag segments the Prefeitura itself marked as doubtful, to delete or with a pending problem.
    out["is_flagged"] = out["quality"].isin({"DUVIDOSO"}) | out["edit_note"].isin(
        {"EXCLUIR", "PROBLEMA -  SOLUCAO FUTURA"})

    # 3.6 Length in meters, computed while still in TM-POA (in degrees it would be meaningless).
    out["length_m"] = out.geometry.length.round(1)

    logger.info("Corrections: %d -> %d segments; classes: %s", len(df), len(out),
                out["feature_class"].value_counts().to_dict())

    # 3.7 Reproject to latitude/longitude (EPSG:4326), the CRS of web maps and of the flood layer.
    return out.to_crs(TARGET_CRS)


# --- Step 4: Save outputs ----------------------------------------------------
def save_outputs(streets: gpd.GeoDataFrame, geojson_path: Path = OUTPUT_GEOJSON) -> Path:
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    streets.to_file(geojson_path, driver="GeoJSON")
    logger.info("Saved %d segments to %s", len(streets), geojson_path)
    return geojson_path


def clean_streets(zip_path: Path = RAW_ZIP) -> Path:
    """Steps 1-4 end to end. Returns the path of the clean GeoJSON."""
    streets = apply_corrections(normalize_streets(load_raw_streets(zip_path)))
    return save_outputs(streets)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    clean_streets()
