"""Anomaly checks for the INCT flood data (long format, one row per level and neighborhood).

Every check receives the normalized DataFrame and returns a DataFrame with the
columns in ANOMALY_COLUMNS (empty when nothing is found). Checks only read the
data: they never change it. This file also holds the helpers shared with inct_cleaning.py.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

FIELDS = ["affected_buildings", "total_buildings", "percentage", "population", "affected_population"]

ANOMALY_COLUMNS = [
    "type", "category", "severity", "neighborhood", "level_m",
    "field", "value", "expected", "description",
]
SEVERITY_ORDER = ["error", "warning", "info"]

# --- Expected structure of the file (from the assignment) -------------------
LEVEL_MIN, LEVEL_MAX, LEVEL_STEP = 3.0, 10.0, 0.1
EXPECTED_NEIGHBORHOODS = 94
CONSTANT_FIELDS = ["total_buildings", "population"]  # should not change with the river level
KNOWN_COLUMNS = {"level_key", "level_m", "neighborhood", "neighborhood_raw", *FIELDS}

# --- Tunable thresholds ------------------------------------------------------
SIMILAR_NAME_RATIO = 0.88      # names this similar may be the same neighborhood
PCT_TOLERANCE = 1.0            # points allowed between percentage and affected/total*100 (the file stores whole numbers)
POP_TOLERANCE = 1.0            # people allowed between affected_population and population*percentage/100
JUMP_THRESHOLD_PCT = 25.0      # jump (in points of the neighborhood's buildings) in one 0.1 m step
REPEATED_MIN_LEVELS = 20       # same value in this many levels in a row (0 < affected < total) is worth reviewing
SPIKE_MIN_POINTS = 10.0        # a value this far above BOTH neighbors (in points of the neighborhood's buildings) is isolated
LOW_LEVEL_M, LOW_LEVEL_PCT = 4.0, 50.0   # a high percentage at a low level is suspicious
UNUSUAL_SIZE_FACTOR = 3.0       # fence width (in IQRs, on log10) for scale outliers
REFERENCE_CITY_POPULATION = 1_332_845   # Porto Alegre, IBGE Census 2022 (confirm before citing)
POPULATION_TOLERANCE = 0.05    # relative difference allowed for the sum of neighborhood populations


def fold_name(name: str) -> str:
    """Comparison key for neighborhood names: no accents, apostrophes, case or extra spaces."""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", "", text.casefold())
    return re.sub(r"\s+", " ", text).strip()


def make_anomalies(type_: str, category: str, severity: str, **columns) -> pd.DataFrame:
    """Build anomaly rows. Each column may be a scalar or an array-like (all the same length)."""
    columns = {k: (v.to_numpy() if isinstance(v, (pd.Series, pd.Index)) else v) for k, v in columns.items()}
    lengths = [len(v) for v in columns.values() if isinstance(v, (np.ndarray, list))]
    size = lengths[0] if lengths else 1
    data = {"type": type_, "category": category, "severity": severity, **columns}
    return pd.DataFrame(data, index=range(size)).reindex(columns=ANOMALY_COLUMNS)


def empty_anomalies() -> pd.DataFrame:
    return pd.DataFrame(columns=ANOMALY_COLUMNS)


def combine_anomalies(parts: list) -> pd.DataFrame:
    """Concatenate anomaly tables, skipping empty ones, sorted by severity and location."""
    parts = [p for p in parts if p is not None and not p.empty]
    if not parts:
        return empty_anomalies()
    out = pd.concat(parts, ignore_index=True)
    out["severity"] = pd.Categorical(out["severity"], categories=SEVERITY_ORDER, ordered=True)
    out = out.sort_values(["severity", "category", "type", "neighborhood", "level_m"], kind="stable")
    out["severity"] = out["severity"].astype(str)
    return out.reset_index(drop=True)


def expected_levels() -> np.ndarray:
    """The 71 river levels of the simulation: 3.0, 3.1, ..., 10.0."""
    return np.round(np.arange(LEVEL_MIN, LEVEL_MAX + LEVEL_STEP / 2, LEVEL_STEP), 1)


# --- Structure ---------------------------------------------------------------
def check_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Level keys that cannot be parsed, are off the 3.0-10.0 grid, or are missing."""
    expected = expected_levels()
    unparsable = df[df["level_m"].isna()]
    known = df.dropna(subset=["level_m"])
    off_grid = known[~known["level_m"].round(1).isin(expected)]
    missing = np.setdiff1d(expected, known["level_m"].round(1).unique())
    return combine_anomalies([
        make_anomalies("unparsable_level_key", "structure", "error", neighborhood=unparsable["neighborhood"],
                       field="level_key", value=unparsable["level_key"],
                       description="level key could not be converted to a number"),
        make_anomalies("unexpected_level", "structure", "error", neighborhood=off_grid["neighborhood"],
                       level_m=off_grid["level_m"], description="level is not on the 3.0-10.0 grid (step 0.1)"),
        make_anomalies("missing_level", "structure", "error", level_m=missing,
                       description="expected level is absent from the file"),
    ])


def check_neighborhoods(df: pd.DataFrame) -> pd.DataFrame:
    """Neighborhood count and neighborhoods missing from levels that exist in the file."""
    names = df["neighborhood"].dropna().unique()
    parts = []
    if len(names) != EXPECTED_NEIGHBORHOODS:
        parts.append(make_anomalies(
            "neighborhood_count_mismatch", "structure", "error", value=len(names),
            expected=EXPECTED_NEIGHBORHOODS, description="distinct neighborhood names in the file"))
    levels = sorted(df["level_m"].dropna().unique())
    present = pd.MultiIndex.from_frame(df[["level_m", "neighborhood"]].dropna())
    missing = pd.MultiIndex.from_product([levels, names]).difference(present)
    parts.append(make_anomalies(
        "missing_neighborhood", "structure", "error", neighborhood=missing.get_level_values(1),
        level_m=missing.get_level_values(0), description="neighborhood present at other levels but not at this one"))
    return combine_anomalies(parts)


def check_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """More than one record for the same level and neighborhood."""
    key = ["level_m", "neighborhood"]
    dup = df[df.duplicated(key, keep=False)]
    identical = df.duplicated(key + FIELDS, keep=False).loc[dup.index]
    text = np.where(identical, "identical duplicate record", "conflicting records for the same level and neighborhood")
    return make_anomalies("duplicate_record", "structure", "error", neighborhood=dup["neighborhood"],
                          level_m=dup["level_m"], description=text)


def check_nulls(df: pd.DataFrame) -> pd.DataFrame:
    """Missing or non-numeric values in the five data fields."""
    parts = []
    for field in FIELDS:
        rows = df[df[field].isna()]
        parts.append(make_anomalies("null_value", "structure", "error", neighborhood=rows["neighborhood"],
                                    level_m=rows["level_m"], field=field, description="value is missing"))
    return combine_anomalies(parts)


def check_unexpected_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Columns that are not part of the documented 5 fields."""
    extra = sorted(set(df.columns) - KNOWN_COLUMNS)
    if not extra:
        return empty_anomalies()
    return make_anomalies("unexpected_field", "structure", "warning", field=extra,
                          description="field is not described in the assignment")


def check_similar_names(df: pd.DataFrame) -> pd.DataFrame:
    """Different names that look alike: possible spelling variants of one neighborhood (manual review)."""
    names = sorted(df["neighborhood"].dropna().unique())
    keys = [fold_name(n) for n in names]
    rows = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            ratio = SequenceMatcher(None, keys[i], keys[j]).ratio()
            if ratio >= SIMILAR_NAME_RATIO:
                rows.append((names[i], names[j], ratio))
    return make_anomalies("similar_neighborhood_names", "structure", "warning",
                          neighborhood=[r[0] for r in rows], value=[r[0] for r in rows],
                          expected=[r[1] for r in rows],
                          description=[f"similarity {r[2]:.2f}: review whether they are the same neighborhood" for r in rows])


# --- Constants ---------------------------------------------------------------
def check_constant_fields(df: pd.DataFrame) -> pd.DataFrame:
    """total_buildings and population should be the same at every level of a neighborhood."""
    parts = []
    for field in CONSTANT_FIELDS:
        mode = df.groupby("neighborhood")[field].transform(lambda s: s.mode().iloc[0] if s.notna().any() else np.nan)
        rows = df[df[field].notna() & (df[field] != mode)]
        parts.append(make_anomalies(
            "non_constant_field", "constants", "error", neighborhood=rows["neighborhood"], level_m=rows["level_m"],
            field=field, value=rows[field], expected=mode.loc[rows.index],
            description="differs from the most common value of this neighborhood"))
    return combine_anomalies(parts)


# --- Coherence between fields -----------------------------------------------
def check_coherence(df: pd.DataFrame) -> pd.DataFrame:
    """Ranges and formulas: affected <= total, percentage = affected/total*100, affected_population = population*percentage/100."""
    parts = []

    for field in FIELDS:
        rows = df[df[field] < 0]
        parts.append(make_anomalies("negative_value", "coherence", "error", neighborhood=rows["neighborhood"],
                                    level_m=rows["level_m"], field=field, value=rows[field],
                                    description="negative value"))

    rows = df[df["affected_buildings"] > df["total_buildings"]]
    parts.append(make_anomalies("affected_exceeds_total", "coherence", "error", neighborhood=rows["neighborhood"],
                                level_m=rows["level_m"], field="affected_buildings", value=rows["affected_buildings"],
                                expected=rows["total_buildings"], description="affected buildings above total buildings"))

    rows = df[df["total_buildings"] == 0]
    parts.append(make_anomalies("zero_total_buildings", "coherence", "warning", neighborhood=rows["neighborhood"],
                                level_m=rows["level_m"], field="total_buildings", value=0,
                                description="percentage is undefined when total_buildings is 0"))

    rows = df[(df["percentage"] < 0) | (df["percentage"] > 100)]
    parts.append(make_anomalies("percentage_out_of_range", "coherence", "error", neighborhood=rows["neighborhood"],
                                level_m=rows["level_m"], field="percentage", value=rows["percentage"],
                                expected="0 to 100", description="percentage outside 0-100"))

    valid = df[(df["total_buildings"] > 0) & df["affected_buildings"].notna() & df["percentage"].notna()]
    expected_pct = valid["affected_buildings"] / valid["total_buildings"] * 100
    diff = (valid["percentage"] - expected_pct).abs()
    scale = (valid["percentage"] <= 1) & (expected_pct > 1) & ((valid["percentage"] * 100 - expected_pct).abs() <= 1)
    too_far = diff > PCT_TOLERANCE + 1e-9
    for name, mask, text in [
        ("percentage_scale_suspect", too_far & scale, "looks like a 0-1 fraction instead of 0-100"),
        ("percentage_mismatch", too_far & ~scale, "differs from affected_buildings / total_buildings * 100"),
    ]:
        rows = valid[mask]
        parts.append(make_anomalies(name, "coherence", "error", neighborhood=rows["neighborhood"],
                                    level_m=rows["level_m"], field="percentage", value=rows["percentage"],
                                    expected=expected_pct[mask].round(4),
                                    description=[f"{text} (abs diff {d:.3f})" for d in diff[mask]]))

    valid = df[df[["population", "percentage", "affected_population"]].notna().all(axis=1)]
    expected_pop = valid["population"] * valid["percentage"] / 100
    diff = (valid["affected_population"] - expected_pop).abs()
    mask = diff > POP_TOLERANCE
    rows = valid[mask]
    parts.append(make_anomalies("affected_population_mismatch", "coherence", "error", neighborhood=rows["neighborhood"],
                                level_m=rows["level_m"], field="affected_population", value=rows["affected_population"],
                                expected=expected_pop[mask].round(2),
                                description=[f"differs from population * percentage / 100 (abs diff {d:.2f})" for d in diff[mask]]))

    rows = df[df["affected_population"] > df["population"]]
    parts.append(make_anomalies("affected_population_exceeds_population", "coherence", "error",
                                neighborhood=rows["neighborhood"], level_m=rows["level_m"],
                                field="affected_population", value=rows["affected_population"],
                                expected=rows["population"], description="affected population above neighborhood population"))
    return combine_anomalies(parts)


# --- Behavior along the river level -----------------------------------------
def _sorted_series(df: pd.DataFrame) -> pd.DataFrame:
    """Rows with a valid level, ordered by neighborhood and level (for per-neighborhood comparisons)."""
    return df.dropna(subset=["level_m"]).sort_values(["neighborhood", "level_m"])


def check_decreasing_values(df: pd.DataFrame) -> pd.DataFrame:
    """affected_buildings must not decrease when the river rises."""
    s = _sorted_series(df).dropna(subset=["affected_buildings"])
    grouped = s.groupby("neighborhood")
    previous, previous_level = grouped["affected_buildings"].shift(), grouped["level_m"].shift()
    mask = s["affected_buildings"] < previous
    rows = s[mask]
    return make_anomalies(
        "value_decreased", "behavior", "error", neighborhood=rows["neighborhood"], level_m=rows["level_m"],
        field="affected_buildings", value=rows["affected_buildings"], expected=previous[mask],
        description=[f"dropped from {p:g} at {pl:g} m (should not decrease)" for p, pl in zip(previous[mask], previous_level[mask])])


def check_jumps(df: pd.DataFrame) -> pd.DataFrame:
    """Large increases of affected buildings in a single 0.1 m step (can be real, can be a typo)."""
    s = _sorted_series(df).dropna(subset=["affected_buildings"])
    s = s[s["total_buildings"] > 0]
    previous = s.groupby("neighborhood")["affected_buildings"].shift()
    step_pct = (s["affected_buildings"] - previous) / s["total_buildings"] * 100
    mask = step_pct > JUMP_THRESHOLD_PCT
    rows = s[mask]
    return make_anomalies("big_jump", "behavior", "info", neighborhood=rows["neighborhood"], level_m=rows["level_m"],
                          field="affected_buildings", value=rows["affected_buildings"], expected=previous[mask],
                          description=[f"+{p:.1f} points of the neighborhood's buildings in one 0.1 m step" for p in step_pct[mask]])


def check_zero_after_affected(df: pd.DataFrame) -> pd.DataFrame:
    """affected_buildings is 0 after the neighborhood already had affected buildings (missing data filled with 0?)."""
    s = _sorted_series(df).dropna(subset=["affected_buildings"])
    highest_before = s.groupby("neighborhood")["affected_buildings"].transform(lambda x: x.cummax().shift())
    mask = (s["affected_buildings"] == 0) & (highest_before > 0)
    rows = s[mask]
    return make_anomalies("zero_after_affected", "behavior", "error", neighborhood=rows["neighborhood"],
                          level_m=rows["level_m"], field="affected_buildings", value=0, expected=highest_before[mask],
                          description="zero after the neighborhood already had affected buildings")


def check_isolated_high_values(df: pd.DataFrame) -> pd.DataFrame:
    """A value far above both the previous and the next level (probably a typo)."""
    s = _sorted_series(df).dropna(subset=["affected_buildings"])
    s = s[s["total_buildings"] > 0]
    grouped = s.groupby("neighborhood")["affected_buildings"]
    previous, following = grouped.shift(), grouped.shift(-1)
    rise_pct = (s["affected_buildings"] - np.maximum(previous, following)) / s["total_buildings"] * 100
    mask = (s["affected_buildings"] > previous) & (s["affected_buildings"] > following) & (rise_pct >= SPIKE_MIN_POINTS)
    rows = s[mask]
    return make_anomalies(
        "isolated_high_value", "behavior", "error", neighborhood=rows["neighborhood"], level_m=rows["level_m"],
        field="affected_buildings", value=rows["affected_buildings"], expected=np.maximum(previous, following)[mask],
        description=[f"much higher than the previous ({p:g}) and the next ({n:g}) level" for p, n in zip(previous[mask], following[mask])])


def check_repeated_values(df: pd.DataFrame) -> pd.DataFrame:
    """The same affected_buildings for many levels in a row while the river keeps rising (possible copied data)."""
    s = _sorted_series(df).dropna(subset=["affected_buildings"])
    new_run = s["affected_buildings"] != s.groupby("neighborhood")["affected_buildings"].shift()
    runs = s.groupby(new_run.cumsum()).agg(
        neighborhood=("neighborhood", "first"), start=("level_m", "min"), end=("level_m", "max"),
        length=("level_m", "size"), value=("affected_buildings", "first"), total=("total_buildings", "first"))
    runs = runs[(runs["length"] >= REPEATED_MIN_LEVELS) & (runs["value"] > 0) & (runs["value"] < runs["total"])]
    return make_anomalies("repeated_value", "behavior", "info", neighborhood=runs["neighborhood"], level_m=runs["start"],
                          field="affected_buildings", value=runs["value"],
                          description=[f"same value from {r.start:g} to {r.end:g} m ({r.length} levels in a row)" for r in runs.itertuples()])


def check_high_at_low_level(df: pd.DataFrame) -> pd.DataFrame:
    """A high percentage of affected buildings at a very low river level."""
    rows = df[(df["level_m"] <= LOW_LEVEL_M) & (df["percentage"] > LOW_LEVEL_PCT)]
    return make_anomalies("high_at_low_level", "behavior", "warning", neighborhood=rows["neighborhood"],
                          level_m=rows["level_m"], field="percentage", value=rows["percentage"],
                          description=f"more than {LOW_LEVEL_PCT:g}% affected at {LOW_LEVEL_M:g} m or lower")


# --- Scale and totals --------------------------------------------------------
def check_unusual_sizes(df: pd.DataFrame) -> pd.DataFrame:
    """Neighborhoods whose total_buildings or population is far from the others (IQR fence on log10)."""
    parts = []
    for field in CONSTANT_FIELDS:
        per_neighborhood = df.groupby("neighborhood")[field].median()
        per_neighborhood = per_neighborhood[per_neighborhood > 0]
        logs = np.log10(per_neighborhood)
        q1, q3 = logs.quantile(0.25), logs.quantile(0.75)
        low, high = q1 - UNUSUAL_SIZE_FACTOR * (q3 - q1), q3 + UNUSUAL_SIZE_FACTOR * (q3 - q1)
        outliers = per_neighborhood[(logs < low) | (logs > high)]
        parts.append(make_anomalies("unusual_size", "scale", "info", neighborhood=outliers.index, field=field,
                                    value=outliers.values, expected=f"{10 ** low:.0f} to {10 ** high:.0f}",
                                    description="median value far from the other neighborhoods"))
    return combine_anomalies(parts)


def check_population_total(df: pd.DataFrame) -> pd.DataFrame:
    """The sum of neighborhood populations should be close to the city population (IBGE Census 2022)."""
    total = df.groupby("neighborhood")["population"].agg(lambda s: s.mode().iloc[0] if s.notna().any() else 0).sum()
    if abs(total - REFERENCE_CITY_POPULATION) / REFERENCE_CITY_POPULATION <= POPULATION_TOLERANCE:
        return empty_anomalies()
    return make_anomalies("population_sum_mismatch", "scale", "warning", field="population", value=int(total),
                          expected=REFERENCE_CITY_POPULATION,
                          description=f"sum of neighborhood populations differs from the city total by more than {POPULATION_TOLERANCE:.0%}")


ALL_CHECKS = [
    check_levels, check_neighborhoods, check_duplicates, check_nulls, check_unexpected_fields, check_similar_names,
    check_constant_fields, check_coherence,
    check_decreasing_values, check_zero_after_affected, check_isolated_high_values,
    check_jumps, check_repeated_values, check_high_at_low_level,
    check_unusual_sizes, check_population_total,
]


def run_all_checks(df: pd.DataFrame) -> pd.DataFrame:
    """Run every check in ALL_CHECKS and return one sorted anomaly table."""
    return combine_anomalies([check(df) for check in ALL_CHECKS])
