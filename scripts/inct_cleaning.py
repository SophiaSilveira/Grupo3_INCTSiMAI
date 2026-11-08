"""INCT flood data cleaning library.

One function per pipeline step:
    1. load_raw_data            read data.json into a long DataFrame (one row per level and neighborhood)
    2. normalize_data           standardize neighborhood names and numeric types
    3. detect_anomalies         run every check (see inct_checks.py), without changing the data
    4. generate_anomaly_report  run steps 1-3 and write the anomalies CSV
    5. apply_corrections        fix anomalies after reviewing the report
    6. revalidate               check the cleaned data again
    7. save_outputs             write the clean long CSV and return its path (the dashboard builds the vectors)

The original file is never modified. app.py provides the paths and calls generate_anomaly_report.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from .inct_checks import FIELDS, combine_anomalies, fold_name, make_anomalies, run_all_checks

logger = logging.getLogger(__name__)

_LEVEL_KEY = re.compile(r"^\s*(\d+)[_.](\d+)\s*m?\s*$", re.IGNORECASE)
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "´": "'", "`": "'", "ʼ": "'"})


def parse_level_key(key: str) -> float:
    """'3_1m' -> 3.1. Returns NaN when the key does not follow the pattern."""
    match = _LEVEL_KEY.match(str(key))
    return round(float(f"{match.group(1)}.{match.group(2)}"), 1) if match else float("nan")


def clean_name_text(name: str) -> str:
    """Unicode NFC, one kind of apostrophe, single spaces, no leading/trailing spaces."""
    text = unicodedata.normalize("NFC", str(name)).translate(_APOSTROPHES)
    return re.sub(r"\s+", " ", text).strip()


# --- Step 1 ------------------------------------------------------------------
def load_raw_data(path) -> pd.DataFrame:
    """Read the INCT JSON into a long DataFrame.

    The file is read as ordered pairs so repeated keys (a neighborhood twice in the same
    level) are kept as repeated rows instead of silently overwriting each other.
    The level comes from the key (e.g. '3_1m'), never from the position in the file.
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f, object_pairs_hook=list)
    if not isinstance(raw, list):
        raise ValueError("Expected a JSON object at the top level (level -> neighborhoods).")

    records = []
    for level_key, neighborhoods in raw:
        if not isinstance(neighborhoods, list):
            logger.warning("Level %r does not contain neighborhoods; skipped.", level_key)
            continue
        for name, values in neighborhoods:
            record = {"level_key": level_key, "level_m": parse_level_key(level_key), "neighborhood_raw": name}
            if isinstance(values, list):
                record.update(dict(values))
            else:
                logger.warning("Level %r, neighborhood %r has no field object.", level_key, name)
            records.append(record)

    df = pd.DataFrame(records)
    for field in FIELDS:
        if field not in df:
            df[field] = np.nan
    logger.info("Loaded %d rows, %d levels, %d neighborhood names.",
                len(df), df["level_key"].nunique(), df["neighborhood_raw"].nunique())
    return df


# --- Step 2 ------------------------------------------------------------------
def normalize_data(df: pd.DataFrame) -> tuple:
    """Standardize names and types. Returns (normalized DataFrame, table of what was changed).

    Names that differ only by accents, case, apostrophes or spaces are merged under the most
    common spelling. Names that are merely similar are NOT merged: check_similar_names reports them.
    Text found in numeric fields is converted to numbers (or null if it cannot be converted).
    """
    out = df.copy()
    changes = []

    cleaned = out["neighborhood_raw"].map(clean_name_text)
    keys = cleaned.map(fold_name)
    canonical = cleaned.groupby(keys).agg(lambda s: s.value_counts().sort_index().idxmax())
    out["neighborhood"] = keys.map(canonical)

    renamed = out[out["neighborhood"] != out["neighborhood_raw"]]
    counts = renamed.groupby(["neighborhood_raw", "neighborhood"]).size().reset_index(name="rows")
    changes.append(make_anomalies(
        "neighborhood_name_normalized", "normalization", "info", neighborhood=counts["neighborhood"],
        field="neighborhood", value=counts["neighborhood_raw"], expected=counts["neighborhood"],
        description=[f"{n} rows renamed to the standard spelling" for n in counts["rows"]]))

    for field in FIELDS:
        original = out[field]
        converted = pd.to_numeric(original, errors="coerce")
        is_text = original.map(lambda v: isinstance(v, str))
        failed = is_text & converted.isna()
        changes.append(make_anomalies(
            "type_coercion", "normalization", "warning", neighborhood=out.loc[is_text, "neighborhood"],
            level_m=out.loc[is_text, "level_m"], field=field, value=original[is_text], expected=converted[is_text],
            description=np.where(failed[is_text], "text could not be converted: set to null", "text converted to number")))
        out[field] = converted.astype(float)

    logger.info("Normalization: %d distinct names after merging spelling variants.", out["neighborhood"].nunique())
    return out, combine_anomalies(changes)


# --- Step 3 ------------------------------------------------------------------
def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """Run every check on the normalized data. Reads only; nothing is corrected here."""
    return run_all_checks(df)


# --- Step 4 (entry point called by app.py) -----------------------------------
def generate_anomaly_report(raw_path, output_path) -> pd.DataFrame:
    """Steps 1-3 end to end, then write the anomalies CSV (UTF-8 with BOM so Excel opens accents correctly)."""
    raw = load_raw_data(raw_path)
    normalized, changes = normalize_data(raw)
    report = combine_anomalies([changes, detect_anomalies(normalized)])

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False, encoding="utf-8-sig")

    summary = report.groupby(["severity", "type"]).size()
    logger.info("Anomaly report with %d rows written to %s\n%s", len(report), output_path, summary.to_string())
    return report


# --- Steps 5-7 (decided after reviewing the anomalies report) ----------------
def apply_corrections(df: pd.DataFrame, anomalies: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError("Step 5: correction policies are decided after reviewing the anomalies report.")


def revalidate(df: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError("Step 6: re-run the checks and assert the 94 x 71 grid is complete and consistent.")


def save_outputs(df: pd.DataFrame, output_path) -> Path:
    raise NotImplementedError("Step 7: write the clean long CSV and return its path (the dashboard builds the vectors).")
