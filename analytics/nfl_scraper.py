"""
NFL Game Data Loader
Loads team info and individual game results from CSV files or web scraping.
Stores in SQLite for ELO calculations and divisional analysis.

CSV files can be downloaded from pro-football-reference.com:
  1. Go to https://www.pro-football-reference.com/years/YYYY/games.htm
  2. Hover over the games table → "Share & Export" → "Get table as CSV"
  3. Save as games_YYYY.csv in the data/ folder
  4. Run: python nfl_scraper.py --csv data/
"""

import sqlite3
import time
from pathlib import Path

import httpx
import pandas as pd

# Configuration
BASE_URL = "https://www.pro-football-reference.com"
DB_PATH = Path(__file__).parent / "nfl_stats.db"
REQUEST_DELAY = 3  # Be respectful to the server

# NFL team data with divisions (current alignment since 2002)
NFL_TEAMS = {
    # AFC East
    "Buffalo Bills": ("AFC", "East"),
    "Miami Dolphins": ("AFC", "East"),
    "New England Patriots": ("AFC", "East"),
    "New York Jets": ("AFC", "East"),
    # AFC North
    "Baltimore Ravens": ("AFC", "North"),
    "Cincinnati Bengals": ("AFC", "North"),
    "Cleveland Browns": ("AFC", "North"),
    "Pittsburgh Steelers": ("AFC", "North"),
    # AFC South
    "Houston Texans": ("AFC", "South"),
    "Indianapolis Colts": ("AFC", "South"),
    "Jacksonville Jaguars": ("AFC", "South"),
    "Tennessee Titans": ("AFC", "South"),
    # AFC West
    "Denver Broncos": ("AFC", "West"),
    "Kansas City Chiefs": ("AFC", "West"),
    "Las Vegas Raiders": ("AFC", "West"),
    "Los Angeles Chargers": ("AFC", "West"),
    # NFC East
    "Dallas Cowboys": ("NFC", "East"),
    "New York Giants": ("NFC", "East"),
    "Philadelphia Eagles": ("NFC", "East"),
    "Washington Commanders": ("NFC", "East"),
    # NFC North
    "Chicago Bears": ("NFC", "North"),
    "Detroit Lions": ("NFC", "North"),
    "Green Bay Packers": ("NFC", "North"),
    "Minnesota Vikings": ("NFC", "North"),
    # NFC South
    "Atlanta Falcons": ("NFC", "South"),
    "Carolina Panthers": ("NFC", "South"),
    "New Orleans Saints": ("NFC", "South"),
    "Tampa Bay Buccaneers": ("NFC", "South"),
    # NFC West
    "Arizona Cardinals": ("NFC", "West"),
    "Los Angeles Rams": ("NFC", "West"),
    "San Francisco 49ers": ("NFC", "West"),
    "Seattle Seahawks": ("NFC", "West"),
}

# Historical team name mappings
TEAM_NAME_ALIASES = {
    "Oakland Raiders": "Las Vegas Raiders",
    "San Diego Chargers": "Los Angeles Chargers",
    "St. Louis Rams": "Los Angeles Rams",
    "Washington Redskins": "Washington Commanders",
    "Washington Football Team": "Washington Commanders",
}


def get_headers() -> dict:
    """Return headers for HTTP requests."""
    return {"User-Agent": "Mozilla/5.0 (educational NFL stats project)"}


def create_database():
    """Create the SQLite database and tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Teams table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            conference TEXT NOT NULL,
            division TEXT NOT NULL
        )
    """)

    # Games table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season INTEGER NOT NULL,
            week TEXT NOT NULL,
            game_date TEXT,
            day_of_week TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_score INTEGER,
            away_score INTEGER,
            home_yards INTEGER,
            away_yards INTEGER,
            home_turnovers INTEGER,
            away_turnovers INTEGER,
            is_playoff INTEGER DEFAULT 0,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(season, week, home_team, away_team),
            FOREIGN KEY (home_team) REFERENCES teams(name),
            FOREIGN KEY (away_team) REFERENCES teams(name)
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_season ON games(season)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_home ON games(home_team)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_away ON games(away_team)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_games_week ON games(week)")

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


def populate_teams():
    """Populate the teams table with NFL team data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for name, (conference, division) in NFL_TEAMS.items():
        cursor.execute(
            "INSERT OR IGNORE INTO teams (name, conference, division) VALUES (?, ?, ?)",
            (name, conference, division),
        )

    conn.commit()
    conn.close()
    print(f"Populated {len(NFL_TEAMS)} teams")


def normalize_team_name(name: str) -> str:
    """Normalize team name to current franchise name."""
    name = name.strip()
    return TEAM_NAME_ALIASES.get(name, name)


def parse_games_dataframe(df: pd.DataFrame, year: int) -> list[dict]:
    """
    Parse a games DataFrame (from CSV or HTML) into our schema.

    Args:
        df: DataFrame with game data
        year: Season year

    Returns:
        List of game dictionaries
    """
    # Handle multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)

    # Filter out header rows that appear mid-table
    df = df[df["Week"].notna() & (df["Week"] != "Week")].copy()

    # Determine playoff games
    playoff_weeks = ["Wild Card", "Division", "Conf. Champ.", "SuperBowl", "Super Bowl"]

    games_data = []
    for _, row in df.iterrows():
        week = str(row["Week"]).strip()

        # Skip if no valid game data
        if pd.isna(row.get("PtsW")) or pd.isna(row.get("PtsL")):
            continue

        # Determine home/away teams
        winner = normalize_team_name(str(row.get("Winner/tie", row.get("Winner", ""))))
        loser = normalize_team_name(str(row.get("Loser/tie", row.get("Loser", ""))))

        # Check if winner was away (has @ symbol in the unnamed column)
        # CSV exports may have different column names
        at_col = None
        for col in df.columns:
            if "Unnamed" in str(col) or col == "":
                at_col = col
                break

        winner_at_indicator = str(row.get(at_col, "")) if at_col else ""
        winner_was_away = "@" in winner_at_indicator

        if winner_was_away:
            home_team, away_team = loser, winner
            home_score = int(row["PtsL"])
            away_score = int(row["PtsW"])
            home_yards = row.get("YdsL")
            away_yards = row.get("YdsW")
            home_to = row.get("TOL")
            away_to = row.get("TOW")
        else:
            home_team, away_team = winner, loser
            home_score = int(row["PtsW"])
            away_score = int(row["PtsL"])
            home_yards = row.get("YdsW")
            away_yards = row.get("YdsL")
            home_to = row.get("TOW")
            away_to = row.get("TOL")

        # Parse yards and turnovers
        try:
            home_yards = int(home_yards) if pd.notna(home_yards) else None
            away_yards = int(away_yards) if pd.notna(away_yards) else None
            home_to = int(home_to) if pd.notna(home_to) else None
            away_to = int(away_to) if pd.notna(away_to) else None
        except (ValueError, TypeError):
            home_yards = away_yards = home_to = away_to = None

        is_playoff = 1 if any(pw in week for pw in playoff_weeks) else 0

        games_data.append({
            "season": year,
            "week": week,
            "game_date": str(row.get("Date", "")),
            "day_of_week": str(row.get("Day", "")),
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "home_yards": home_yards,
            "away_yards": away_yards,
            "home_turnovers": home_to,
            "away_turnovers": away_to,
            "is_playoff": is_playoff,
        })

    return games_data


def load_csv(csv_path: Path, force: bool = False) -> bool:
    """
    Load games from a CSV file.

    Expected filename format: games_YYYY.csv or YYYY.csv
    CSV should have pro-football-reference format.

    Args:
        csv_path: Path to CSV file
        force: If True, overwrite existing data

    Returns:
        True if successful, False otherwise
    """
    import re

    # Extract year from filename
    match = re.search(r"(\d{4})", csv_path.stem)
    if not match:
        print(f"Could not determine year from filename: {csv_path.name}")
        print("Expected format: games_YYYY.csv or YYYY.csv")
        return False

    year = int(match.group(1))

    conn = sqlite3.connect(DB_PATH)

    # Check if we already have data for this year
    if not force:
        existing = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM games WHERE season = ?",
            conn,
            params=(year,),
        )
        if existing["count"].iloc[0] > 0:
            print(f"Games for {year} already exist. Use --force to overwrite.")
            conn.close()
            return False

    print(f"Loading {csv_path} for {year} season...")

    try:
        df = pd.read_csv(csv_path)
        games_data = parse_games_dataframe(df, year)

        if not games_data:
            print(f"No game data parsed from {csv_path}")
            conn.close()
            return False

        games_df = pd.DataFrame(games_data)

        # Delete existing data if forcing
        if force:
            conn.execute("DELETE FROM games WHERE season = ?", (year,))

        # Insert new data
        games_df.to_sql("games", conn, if_exists="append", index=False)
        conn.commit()

        regular = len(games_df[games_df["is_playoff"] == 0])
        playoff = len(games_df[games_df["is_playoff"] == 1])
        print(f"Loaded {regular} regular season + {playoff} playoff games for {year}")
        conn.close()
        return True

    except Exception as e:
        print(f"Error loading {csv_path}: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        return False


def load_csv_directory(csv_dir: Path, force: bool = False):
    """
    Load all CSV files from a directory.

    Args:
        csv_dir: Directory containing CSV files
        force: If True, overwrite existing data
    """
    create_database()
    populate_teams()

    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {csv_dir}")
        return

    print(f"Found {len(csv_files)} CSV files")
    for csv_path in csv_files:
        load_csv(csv_path, force=force)


def scrape_games(year: int, force: bool = False) -> bool:
    """
    Scrape all games for a specific season from the web.

    Args:
        year: NFL season year
        force: If True, overwrite existing data for this year

    Returns:
        True if successful, False otherwise
    """
    conn = sqlite3.connect(DB_PATH)

    # Check if we already have data for this year
    if not force:
        existing = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM games WHERE season = ?",
            conn,
            params=(year,),
        )
        if existing["count"].iloc[0] > 0:
            print(f"Games for {year} already exist. Use --force to overwrite.")
            conn.close()
            return False

    url = f"{BASE_URL}/years/{year}/games.htm"
    print(f"Scraping {url}...")

    try:
        response = httpx.get(url, headers=get_headers(), follow_redirects=True)
        response.raise_for_status()

        # Parse tables from the page
        tables = pd.read_html(response.text)

        if not tables:
            print(f"No tables found for {year}")
            conn.close()
            return False

        # The games table is typically the first one
        df = tables[0]
        games_data = parse_games_dataframe(df, year)

        if not games_data:
            print(f"No game data parsed for {year}")
            conn.close()
            return False

        games_df = pd.DataFrame(games_data)

        # Delete existing data if forcing
        if force:
            conn.execute("DELETE FROM games WHERE season = ?", (year,))

        # Insert new data
        games_df.to_sql("games", conn, if_exists="append", index=False)
        conn.commit()

        regular = len(games_df[games_df["is_playoff"] == 0])
        playoff = len(games_df[games_df["is_playoff"] == 1])
        print(f"Successfully scraped {regular} regular season + {playoff} playoff games for {year}")
        conn.close()
        return True

    except httpx.HTTPError as e:
        print(f"Error fetching {url}: {e}")
        conn.close()
        return False
    except Exception as e:
        print(f"Error processing {year}: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        return False


def scrape_years(start_year: int, end_year: int, force: bool = False):
    """
    Scrape multiple years of game data.

    Args:
        start_year: First year to scrape
        end_year: Last year to scrape (inclusive)
        force: If True, overwrite existing data
    """
    create_database()
    populate_teams()

    for year in range(start_year, end_year + 1):
        scrape_games(year, force=force)
        if year < end_year:
            print(f"Waiting {REQUEST_DELAY}s before next request...")
            time.sleep(REQUEST_DELAY)


def get_available_years() -> list[int]:
    """Get list of years already in the database."""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    result = pd.read_sql_query("SELECT DISTINCT season FROM games ORDER BY season", conn)
    conn.close()
    return result["season"].tolist()


def get_stats() -> dict:
    """Get database statistics."""
    if not DB_PATH.exists():
        return {"teams": 0, "games": 0, "seasons": []}

    conn = sqlite3.connect(DB_PATH)
    teams = pd.read_sql_query("SELECT COUNT(*) as count FROM teams", conn)["count"].iloc[0]
    games = pd.read_sql_query("SELECT COUNT(*) as count FROM games", conn)["count"].iloc[0]
    seasons = get_available_years()
    conn.close()

    return {"teams": teams, "games": games, "seasons": seasons}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Load NFL game data from CSV files or web scraping",
        epilog="""
Examples:
  python nfl_scraper.py --csv data/           # Load all CSVs from data/ folder
  python nfl_scraper.py --csv data/2023.csv   # Load single CSV file
  python nfl_scraper.py --year 2024           # Scrape single year from web
  python nfl_scraper.py --list                # Show database stats
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csv", type=str, help="CSV file or directory to load")
    parser.add_argument("--year", type=int, help="Single year to scrape from web")
    parser.add_argument("--start-year", type=int, default=2004, help="Start year for range scrape (default: 2004)")
    parser.add_argument("--end-year", type=int, default=2024, help="End year for range scrape (default: 2024)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing data")
    parser.add_argument("--list", action="store_true", help="Show database stats")
    parser.add_argument("--init", action="store_true", help="Initialize database without loading data")

    args = parser.parse_args()

    if args.list:
        stats = get_stats()
        print(f"Teams: {stats['teams']}")
        print(f"Games: {stats['games']}")
        if stats["seasons"]:
            print(f"Seasons: {', '.join(map(str, stats['seasons']))}")
        else:
            print("No seasons loaded yet.")
    elif args.init:
        create_database()
        populate_teams()
    elif args.csv:
        csv_path = Path(args.csv)
        if not csv_path.exists():
            print(f"Error: {csv_path} does not exist")
        elif csv_path.is_dir():
            load_csv_directory(csv_path, force=args.force)
        else:
            create_database()
            populate_teams()
            load_csv(csv_path, force=args.force)
    elif args.year:
        create_database()
        populate_teams()
        scrape_games(args.year, force=args.force)
    else:
        scrape_years(args.start_year, args.end_year, force=args.force)
