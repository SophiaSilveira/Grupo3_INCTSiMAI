"""INCT flood data cleaning library.

One function per pipeline step:
    1. load_raw_data            read data.json into a long DataFrame (one row per level and neighborhood)
    2. normalize_data           standardize neighborhood names and numeric types
    3. detect_anomalies         run every check (see inct_checks.py), without changing the data
    4. generate_anomaly_report  run steps 1-3 and write the anomalies CSV
    5. apply_corrections        fix anomalies after reviewing the report
    6. revalidate               check the cleaned data again
    7. save_outputs             write the clean data as JSON (vectors per neighborhood) and return its path

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

from .inct_checks import (
    EXPECTED_NEIGHBORHOODS, FIELDS, LEVEL_MIN, LEVEL_STEP,
    combine_anomalies, expected_levels, fold_name, make_anomalies, run_all_checks,
)

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


# --- Step 5 ------------------------------------------------------------------
def apply_corrections(df: pd.DataFrame, anomalies: pd.DataFrame) -> tuple:
    """Correct affected_buildings and recompute the fields derived from it.

    Rule 1: a zero flagged as 'zero_after_affected' is replaced by a straight line between the
            nearest valid levels of the same neighborhood (rounded).
    Rule 2: no value may be higher than a later level of the same neighborhood: it is lowered to the
            lowest later value. This assumes the later values are the correct ones.
    Rows that changed get percentage and affected_population recalculated with the rule found in the
    file (rounded up). Warnings and info anomalies (high_at_low_level, big_jump, repeated_value) are
    kept untouched. Returns (corrected DataFrame, table with one row per corrected value).
    """
    out = df.sort_values(["neighborhood", "level_m"]).reset_index(drop=True)
    original = out[["affected_buildings", "percentage", "affected_population"]].copy()

    zeros = anomalies[anomalies["type"] == "zero_after_affected"]
    zero_keys = set(zip(zeros["neighborhood"], zeros["level_m"]))
    is_zero_rule = np.array([key in zero_keys for key in zip(out["neighborhood"], out["level_m"])], dtype=bool)

    # rule 1: the flagged zeros become empty and are filled by interpolation
    out.loc[is_zero_rule, "affected_buildings"] = np.nan
    out["affected_buildings"] = out.groupby("neighborhood")["affected_buildings"].transform(
        lambda s: s.interpolate(limit_direction="both").round())

    # rule 2: a value cannot be higher than any later level (lowest value from the end backwards)
    out["affected_buildings"] = out.groupby("neighborhood")["affected_buildings"].transform(
        lambda s: s[::-1].cummin()[::-1])

    # derived fields of the rows that changed, with the rule used in the file (rounded up)
    changed = out["affected_buildings"] != original["affected_buildings"]
    out.loc[changed, "percentage"] = np.ceil(out.loc[changed, "affected_buildings"] / out.loc[changed, "total_buildings"] * 100)
    out.loc[changed, "affected_population"] = np.ceil(out.loc[changed, "population"] * out.loc[changed, "percentage"] / 100)

    parts = []
    for field in original.columns:
        rows = out[out[field] != original[field]]
        if field == "affected_buildings":
            reason = np.where(is_zero_rule[rows.index], "zero replaced by interpolation between neighbors",
                              "lowered to the lowest value of the later levels")
        else:
            reason = "recalculated because affected_buildings changed"
        parts.append(pd.DataFrame({
            "neighborhood": rows["neighborhood"], "level_m": rows["level_m"], "field": field,
            "value_before": original.loc[rows.index, field], "value_after": rows[field], "reason": reason}))
    corrections = pd.concat(parts, ignore_index=True).sort_values(["neighborhood", "level_m", "field"], ignore_index=True)

    logger.info("Corrected %d affected_buildings values (%d zero rule, %d lowering rule).",
                int(changed.sum()), int(is_zero_rule.sum()), int(changed.sum() - is_zero_rule.sum()))
    return out, corrections


# --- Step 6 ------------------------------------------------------------------
def revalidate(df: pd.DataFrame) -> pd.DataFrame:
    """Check the corrected data again. Raises ValueError if the grid is incomplete or any error remains.

    Returns the anomalies that are allowed to remain (warnings and info kept on purpose).
    """
    levels = expected_levels()
    levels_per_neighborhood = df.groupby("neighborhood")["level_m"].nunique()
    incomplete = (
        len(levels_per_neighborhood) != EXPECTED_NEIGHBORHOODS
        or (levels_per_neighborhood != len(levels)).any()
        or len(df) != EXPECTED_NEIGHBORHOODS * len(levels)
        or df[FIELDS].isna().any().any()
    )
    if incomplete:
        raise ValueError("The neighborhood x level grid is not complete (expected 94 x 71 without empty values).")

    remaining = detect_anomalies(df)
    errors = remaining[remaining["severity"] == "error"]
    if not errors.empty:
        raise ValueError(f"{len(errors)} errors remain after the corrections:\n{errors.groupby('type').size().to_string()}")

    logger.info("Revalidation passed: grid complete and no errors. %d warnings/info kept on purpose.", len(remaining))
    return remaining


# --- Step 7 ------------------------------------------------------------------
def save_outputs(df: pd.DataFrame, output_path) -> Path:
    """Write the clean data as JSON, one entry per neighborhood, and return its path.

    total_buildings and population are single numbers (they do not change with the level).
    The other three fields are vectors with one value per level, in order from the lowest level.
    Position of a river level in every vector: round((level - level_min) / level_step),
    that is, round((level - 3.0) * 10).
    """
    neighborhoods = {}
    for name, rows in df.sort_values(["neighborhood", "level_m"]).groupby("neighborhood"):
        neighborhoods[name] = {
            "total_buildings": int(rows["total_buildings"].iloc[0]),
            "population": int(rows["population"].iloc[0]),
            "affected_buildings": rows["affected_buildings"].astype(int).tolist(),
            "percentage": rows["percentage"].astype(int).tolist(),
            "affected_population": rows["affected_population"].astype(int).tolist(),
        }
    content = {"level_min": LEVEL_MIN, "level_step": LEVEL_STEP, "level_count": len(expected_levels()),
               "neighborhoods": neighborhoods}

    # one line per vector keeps the file readable
    text = json.dumps(content, ensure_ascii=False, indent=2)
    text = re.sub(r"\[\s+([^\[\]]*?)\s+\]", lambda m: "[" + re.sub(r"\s+", " ", m.group(1)) + "]", text)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    logger.info("Clean file with %d neighborhoods written to %s", len(neighborhoods), output_path)
    return output_path


# --- Entry point: steps 1 to 7 ------------------------------------------------
def clean_inct_data(raw_path, anomalies_path, clean_path) -> Path:
    """Run the whole pipeline and return the path of the clean JSON that the dashboard must use.

    Also writes the anomalies report and, next to the clean file, corrections.csv.
    """
    report = generate_anomaly_report(raw_path, anomalies_path)           # steps 1-4
    normalized, _ = normalize_data(load_raw_data(raw_path))
    corrected, corrections = apply_corrections(normalized, report)      # step 5
    revalidate(corrected)                                                # step 6

    corrections_path = Path(clean_path).with_name("corrections.csv")
    corrections_path.parent.mkdir(parents=True, exist_ok=True)
    corrections.to_csv(corrections_path, index=False, encoding="utf-8-sig")
    return save_outputs(corrected, clean_path)                           # step 7
