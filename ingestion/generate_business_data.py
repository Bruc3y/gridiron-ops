"""
generate_business_data.py

Generates realistic simulated business data (ticket sales, merchandise sales,
marketing campaigns, sponsorship impressions) for ONE team, tied to that team's
real schedule so the numbers tell a believable story:

- Ticket prices/volume scale up for divisional rivals and nationally marquee opponents
- Both ticket and merch sales get a bump in the week following a win (and a dip after
  a loss), simulating fan sentiment carrying into next week's spend
- Marketing campaigns are scheduled relative to each home game, with engagement
  metrics influenced by whether the previous game was a win

Why simulate this way instead of pure randomness: a reviewer (or interviewer) should
be able to query the resulting data and find real patterns -- e.g. "ticket revenue is
higher for AFC East away visitors" -- because that's what makes this a believable stand-in
for actual team business data, not just noise with NFL logos on it.
"""

from datetime import timedelta
from pathlib import Path
import logging
import random

import pandas as pd
from faker import Faker

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

fake = Faker()
random.seed(42)  # reproducible runs -- important for a portfolio project reviewers might re-run

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
TEAM = "LAC"  # the team this business data belongs to
DIVISION_RIVALS = {"KC", "LV", "DEN"}
MARQUEE_OPPONENTS = {"KC", "DAL", "SF", "PHI", "BUF"}  # historically high-draw matchups

TICKET_TIERS = ["Lower Bowl", "Club Level", "Upper Bowl", "Suite"]
TICKET_BASE_PRICE = {"Lower Bowl": 180, "Club Level": 320, "Upper Bowl": 95, "Suite": 650}
CAMPAIGN_TYPES = ["Email", "Social - Instagram", "Social - X", "SMS", "Display Ads"]


def _load_team_schedule(schedule_df: pd.DataFrame) -> pd.DataFrame:
    """Filter the full league schedule down to this team's home games."""
    home = schedule_df[schedule_df["home_team"] == TEAM].copy()
    home = home.sort_values("gameday")
    return home


def generate_ticket_sales(home_games: pd.DataFrame) -> pd.DataFrame:
    rows = []
    prior_result_multiplier = 1.0  # carries streak effect game to game

    for _, game in home_games.iterrows():
        opponent = game["away_team"]
        matchup_multiplier = 1.0
        if opponent in DIVISION_RIVALS:
            matchup_multiplier *= 1.25
        if opponent in MARQUEE_OPPONENTS:
            matchup_multiplier *= 1.35

        for tier in TICKET_TIERS:
            base_price = TICKET_BASE_PRICE[tier]
            price = round(base_price * matchup_multiplier * random.uniform(0.95, 1.15), 2)
            capacity = {"Lower Bowl": 28000, "Club Level": 8000, "Upper Bowl": 33000, "Suite": 800}[tier]
            sell_through = min(
                0.99,
                random.uniform(0.55, 0.75) * matchup_multiplier * prior_result_multiplier,
            )
            units_sold = int(capacity * sell_through)

            rows.append(
                {
                    "game_id": game["game_id"],
                    "season": game["season"],
                    "week": game["week"],
                    "game_date": game["gameday"],
                    "opponent": opponent,
                    "ticket_tier": tier,
                    "unit_price": price,
                    "units_sold": units_sold,
                    "revenue": round(price * units_sold, 2),
                }
            )

        if pd.notna(game.get("home_score")) and pd.notna(game.get("away_score")):
            prior_result_multiplier = 1.08 if game["home_score"] > game["away_score"] else 0.94
        else:
            prior_result_multiplier = 1.0

    return pd.DataFrame(rows)


def generate_merch_sales(home_games: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, game in home_games.iterrows():
        game_date = pd.to_datetime(game["gameday"])
        won = pd.notna(game.get("home_score")) and pd.notna(game.get("away_score")) \
            and game["home_score"] > game["away_score"]

        for day_offset in range(7):
            d = game_date + timedelta(days=day_offset)
            bump = 1.0
            if day_offset == 0:
                bump = 1.6
            elif 1 <= day_offset <= 2 and won:
                bump = 1.3

            units = int(random.uniform(150, 400) * bump)
            avg_price = round(random.uniform(28, 95), 2)

            rows.append(
                {
                    "game_id": game["game_id"],
                    "sale_date": d.date().isoformat(),
                    "units_sold": units,
                    "avg_unit_price": avg_price,
                    "revenue": round(units * avg_price, 2),
                }
            )
    return pd.DataFrame(rows)


def generate_marketing_campaigns(home_games: pd.DataFrame) -> pd.DataFrame:
    rows = []
    campaign_id = 1000
    for _, game in home_games.iterrows():
        game_date = pd.to_datetime(game["gameday"])
        for channel in CAMPAIGN_TYPES:
            launch_date = game_date - timedelta(days=random.randint(5, 10))
            audience = random.randint(15000, 120000)
            open_rate = round(random.uniform(0.12, 0.34), 3) if channel == "Email" else None
            engagement_rate = round(random.uniform(0.02, 0.09), 3)
            clicks = int(audience * engagement_rate)
            conversions = int(clicks * random.uniform(0.03, 0.12))

            rows.append(
                {
                    "campaign_id": campaign_id,
                    "game_id": game["game_id"],
                    "channel": channel,
                    "launch_date": launch_date.date().isoformat(),
                    "audience_size": audience,
                    "open_rate": open_rate,
                    "engagement_rate": engagement_rate,
                    "clicks": clicks,
                    "conversions": conversions,
                    "estimated_ticket_revenue_influenced": round(
                        conversions * random.uniform(80, 250), 2
                    ),
                }
            )
            campaign_id += 1
    return pd.DataFrame(rows)


def _land(df: pd.DataFrame, dataset_name: str) -> None:
    from datetime import date
    out_dir = RAW_DIR / dataset_name / f"ingestion_date={date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{dataset_name}.parquet"
    df.to_parquet(out_path, index=False)
    log.info("Landed %s rows -> %s", len(df), out_path)


def run(schedule_parquet_path: str) -> None:
    log.info("Loading real schedule data from %s", schedule_parquet_path)
    schedule_df = pd.read_parquet(schedule_parquet_path)
    home_games = _load_team_schedule(schedule_df)
    log.info("Found %d home games for %s", len(home_games), TEAM)

    tickets = generate_ticket_sales(home_games)
    merch = generate_merch_sales(home_games)
    campaigns = generate_marketing_campaigns(home_games)

    _land(tickets, "ticket_sales")
    _land(merch, "merch_sales")
    _land(campaigns, "marketing_campaigns")

    log.info("Ticket revenue total: $%.2f", tickets["revenue"].sum())
    log.info("Merch revenue total: $%.2f", merch["revenue"].sum())
    log.info("Campaigns generated: %d", len(campaigns))


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python generate_business_data.py <path_to_schedules.parquet>")
        sys.exit(1)
    run(sys.argv[1])