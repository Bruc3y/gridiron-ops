"""
fetch_nfl_data.py

Pulls real NFL reference and schedule data from the nflverse project (via nfl_data_py)
and lands it as raw, untouched files -- this is the "Bronze" landing step.

Design choice: we save one file per (dataset, ingestion_date) rather than overwriting
in place. This mirrors how a real ingestion job should behave -- every run produces an
immutable snapshot, so you can always trace what the pipeline saw on a given day and
reprocess history if a downstream bug is found.
"""

from datetime import date, datetime
from pathlib import Path
import logging

import nfl_data_py as nfl
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
SEASONS = [2022, 2023, 2024]


def _land(df: pd.DataFrame, dataset_name: str, ingestion_date: date) -> Path:
    """Write a dataframe to the bronze landing zone, partitioned by ingestion date."""
    out_dir = RAW_DIR / dataset_name / f"ingestion_date={ingestion_date.isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{dataset_name}.parquet"
    df.to_parquet(out_path, index=False)
    log.info("Landed %s rows -> %s", len(df), out_path)
    return out_path


def fetch_schedules(ingestion_date: date) -> pd.DataFrame:
    log.info("Pulling schedules for seasons: %s", SEASONS)
    df = nfl.import_schedules(SEASONS)
    df["_ingested_at"] = datetime.utcnow().isoformat()
    df["_source"] = "nflverse:schedules"
    _land(df, "schedules", ingestion_date)
    return df


def fetch_team_descriptions(ingestion_date: date) -> pd.DataFrame:
    log.info("Pulling team reference data")
    df = nfl.import_team_desc()
    df["_ingested_at"] = datetime.utcnow().isoformat()
    df["_source"] = "nflverse:team_desc"
    _land(df, "teams", ingestion_date)
    return df


def fetch_rosters(ingestion_date: date) -> pd.DataFrame:
    log.info("Pulling rosters for seasons: %s", SEASONS)
    df = nfl.import_seasonal_rosters(SEASONS)
    df["_ingested_at"] = datetime.utcnow().isoformat()
    df["_source"] = "nflverse:rosters"
    _land(df, "rosters", ingestion_date)
    return df


def run() -> None:
    today = date.today()
    log.info("=== NFL ingestion run starting: %s ===", today)

    results = {
        "schedules": fetch_schedules(today),
        "teams": fetch_team_descriptions(today),
        "rosters": fetch_rosters(today),
    }

    for name, df in results.items():
        log.info("Summary | %-12s rows=%-6d cols=%-3d", name, len(df), df.shape[1])

    log.info("=== NFL ingestion run complete ===")


if __name__ == "__main__":
    run()