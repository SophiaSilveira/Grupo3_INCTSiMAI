"""Collector for the street centerlines (Eixos de Logradouros) of Porto Alegre.

Source: Prefeitura de Porto Alegre / SMAMUS - Mapas Digitais
    https://prefeitura.poa.br/smamus/planejamento-urbano/mapas-digitais

This script only collects: it downloads the shapefile ZIP as it comes and records
where and when it was collected. Nothing is changed in the data. Cleaning lives in
logradouros_cleaning.py, which reads the ZIP saved here.

    1. download_zip      download the ZIP once and keep it in dados/originais (cache)
    2. write_metadata    record URL, collection date, size and checksum next to the raw file

Notes:
    - robots.txt allows /sites/default/files/ (checked on 2026-11-10).
    - The ZIP is ~7 MB: EixosLogradouros.shp/.dbf/.shx/.prj/.CPG (+ .sbn/.sbx/.shp.xml).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://prefeitura.poa.br/sites/default/files/usu_img/planejamento_urbano/Mapas%20Digitais"
SOURCE_PAGE = "https://prefeitura.poa.br/smamus/planejamento-urbano/mapas-digitais"
ZIP_URL = f"{BASE_URL}/Shapefile_Logradouros.zip"
METADATA_ZIP_URL = f"{BASE_URL}/Metadados_Logradouros.zip"   # field dictionary published with the data

RAW_DIR = Path("dados/originais/logradouros")
USER_AGENT = "Grupo3-INCTSiMAI/0.1 (projeto academico PUCRS)"


# --- Step 1: Download (cached) -----------------------------------------------
def download_zip(url: str = ZIP_URL, raw_dir: Path = RAW_DIR, force: bool = False) -> Path:
    """Download the ZIP once. If the file is already there, reuse it (no new request)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / Path(url).name
    if zip_path.exists() and not force:
        logger.info("Using cached file %s", zip_path)
        return zip_path

    logger.info("Downloading %s", url)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    response.raise_for_status()
    zip_path.write_bytes(response.content)
    write_metadata(zip_path, url, last_modified=response.headers.get("Last-Modified"))
    return zip_path


# --- Step 2: Collection metadata ---------------------------------------------
def write_metadata(zip_path: Path, url: str, last_modified: str | None = None) -> Path:
    """Save where and when the data was collected (required by the assignment for Tela 2)."""
    content = zip_path.read_bytes()
    metadata = {
        "source": "Prefeitura de Porto Alegre - SMAMUS - Mapas Digitais",
        "source_page": SOURCE_PAGE,
        "url": url,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server_last_modified": last_modified,   # when the Prefeitura last updated the file
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    meta_path = zip_path.with_suffix(".metadata.json")
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Metadata written to %s", meta_path)
    return meta_path


def collect_streets(force: bool = False) -> Path:
    """Download the shapefile ZIP and its metadata ZIP (if needed). Returns the shapefile ZIP path."""
    download_zip(METADATA_ZIP_URL, force=force)   # field dictionary, used to interpret the codes
    return download_zip(ZIP_URL, force=force)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    collect_streets()
