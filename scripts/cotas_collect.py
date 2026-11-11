"""Collection of the Porto Alegre flood level polygons (ArcGIS REST API).

Source: Prefeitura de Porto Alegre (SMAMUS), layer cotas_inundacao_300_535.

Each feature is saved exactly as the server sent it, one GeoJSON per feature, so the
server is not asked again. Files that already exist are skipped. A small manifest records
the source and the collection date of each file (the dashboard has to show both).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

LAYER_URL = (
    "https://gis-smamus.portoalegre.rs.gov.br/server/rest/services/"
    "01_PUBLICACOES/cotas_inundacao_300_535/FeatureServer/0"
)
TIMEOUT_S = 180
ATTEMPTS = 3
PAUSE_BETWEEN_REQUESTS_S = 1.0


def query(params: dict) -> requests.Response:
    """Query the layer, retrying temporary failures.

    The server can answer 200 with an error body instead of features, so the body is checked too.
    """
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = requests.get(f"{LAYER_URL}/query", params=params, timeout=TIMEOUT_S)
            response.raise_for_status()
            if "error" in response.json():
                raise ValueError(f"server error: {response.text[:200]}")
            return response
        except (requests.RequestException, ValueError) as error:
            logger.warning("Attempt %d/%d failed: %s", attempt, ATTEMPTS, error)
            if attempt == ATTEMPTS:
                raise
            time.sleep(5 * attempt)


def list_features() -> list:
    """Attributes of every feature, without geometry. The server decides which levels exist."""
    params = {"where": "1=1", "outFields": "objectid,contourmax", "returnGeometry": "false", "f": "json"}
    return [item["attributes"] for item in query(params).json()["features"]]


def download_feature(object_id: int, path: Path) -> None:
    """Save one feature as GeoJSON. Writes then renames, so an interrupted run leaves no partial file."""
    params = {"where": f"objectid={object_id}", "outFields": "*", "outSR": 4326, "f": "geojson"}
    response = query(params)
    if not response.json().get("features"):
        raise ValueError(f"objectid {object_id}: no features returned")
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(response.content)
    temporary.replace(path)


def collect_all(raw_dir, manifest_path) -> dict:
    """Download every feature that is not on disk yet and update the manifest."""
    raw_dir, manifest_path = Path(raw_dir), Path(manifest_path)
    raw_dir.mkdir(parents=True, exist_ok=True)

    collected = {}
    if manifest_path.exists():
        collected = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]

    features = list_features()
    logger.info("The server lists %d features.", len(features))
    for feature in sorted(features, key=lambda f: f["objectid"]):
        name = f"objectid_{feature['objectid']}.geojson"
        path = raw_dir / name
        if path.exists() and name in collected:
            logger.info("%s already downloaded", name)
            continue
        download_feature(feature["objectid"], path)
        collected[name] = {
            "objectid": feature["objectid"],
            "contourmax": feature["contourmax"],
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        manifest = {"source": "Prefeitura de Porto Alegre (SMAMUS)", "url": LAYER_URL, "files": collected}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        logger.info("%s saved (%.1f MB)", name, path.stat().st_size / 1e6)
        time.sleep(PAUSE_BETWEEN_REQUESTS_S)
    return collected
