"""
NFL Stats Analysis
Query and analyze game data with ELO ratings and divisional breakdowns.
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "nfl_stats.db"

# ELO Configuration
ELO_START = 1500
ELO_K_FACTOR = 20
ELO_HOME_ADVANTAGE = 65  # ~65 ELO points home field advantage


def get_connection():
    """Get a connection to the database."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}. Run nfl_scraper.py first.")
    return sqlite3.connect(DB_PATH)


def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Execute a SQL query and return results as a DataFrame."""
    conn = get_connection()
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


# ============================================================================
# ELO Rating System
# ============================================================================


def expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate expected score for team A against team B."""
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def calculate_elo_ratings(
    season: int = None,
    start_year: int = None,
    reset_each_season: bool = True,
) -> pd.DataFrame:
    """
    Calculate ELO ratings for all teams based on game results.

    Args:
        season: If provided, only calculate for this single season
        start_year: If provided, start calculations from this year (teams start at 1500)
        reset_each_season: If True, regress ratings toward 1500 at start of each season

    Returns:
        DataFrame with team ELO ratings
    """
    conn = get_connection()

    # Get all games ordered by date
    if season:
        games = pd.read_sql_query(
            """
            SELECT season, week, home_team, away_team, home_score, away_score, is_playoff
            FROM games
            WHERE season = ? AND home_score IS NOT NULL
            ORDER BY season,
                CASE
                    WHEN week GLOB '[0-9]*' THEN CAST(week AS INTEGER)
                    ELSE 100  -- Playoffs come after regular season
                END
            """,
            conn,
            params=(season,),
        )
    elif start_year:
        games = pd.read_sql_query(
            """
            SELECT season, week, home_team, away_team, home_score, away_score, is_playoff
            FROM games
            WHERE season >= ? AND home_score IS NOT NULL
            ORDER BY season,
                CASE
                    WHEN week GLOB '[0-9]*' THEN CAST(week AS INTEGER)
                    ELSE 100
                END
            """,
            conn,
            params=(start_year,),
        )
    else:
        games = pd.read_sql_query(
            """
            SELECT season, week, home_team, away_team, home_score, away_score, is_playoff
            FROM games
            WHERE home_score IS NOT NULL
            ORDER BY season,
                CASE
                    WHEN week GLOB '[0-9]*' THEN CAST(week AS INTEGER)
                    ELSE 100
                END
            """,
            conn,
        )
    conn.close()

    # Initialize ratings
    ratings = {}
    rating_history = []
    current_season = None

    for _, game in games.iterrows():
        # Reset ratings at start of new season if configured
        if reset_each_season and game["season"] != current_season:
            if current_season is not None:
                # Regress ratings toward mean (1500) between seasons
                for team in ratings:
                    ratings[team] = ratings[team] * 0.75 + ELO_START * 0.25
            current_season = game["season"]

        home = game["home_team"]
        away = game["away_team"]

        # Initialize new teams
        if home not in ratings:
            ratings[home] = ELO_START
        if away not in ratings:
            ratings[away] = ELO_START

        # Get pre-game ratings
        home_rating = ratings[home]
        away_rating = ratings[away]

        # Calculate expected scores (with home advantage)
        home_expected = expected_score(home_rating + ELO_HOME_ADVANTAGE, away_rating)
        away_expected = 1 - home_expected

        # Actual result
        if game["home_score"] > game["away_score"]:
            home_actual, away_actual = 1, 0
        elif game["home_score"] < game["away_score"]:
            home_actual, away_actual = 0, 1
        else:
            home_actual, away_actual = 0.5, 0.5

        # Update ratings
        home_new = home_rating + ELO_K_FACTOR * (home_actual - home_expected)
        away_new = away_rating + ELO_K_FACTOR * (away_actual - away_expected)

        ratings[home] = home_new
        ratings[away] = away_new

        # Record history
        rating_history.append({
            "season": game["season"],
            "week": game["week"],
            "team": home,
            "elo": home_new,
            "opponent": away,
            "result": "W" if home_actual == 1 else ("L" if home_actual == 0 else "T"),
        })
        rating_history.append({
            "season": game["season"],
            "week": game["week"],
            "team": away,
            "elo": away_new,
            "opponent": home,
            "result": "W" if away_actual == 1 else ("L" if away_actual == 0 else "T"),
        })

    # Get final ratings
    final_ratings = pd.DataFrame([{"team": t, "elo": round(r, 1)} for t, r in ratings.items()])
    final_ratings = final_ratings.sort_values("elo", ascending=False).reset_index(drop=True)

    return final_ratings


def get_elo_history(team: str, season: int = None) -> pd.DataFrame:
    """Get ELO rating progression for a specific team."""
    conn = get_connection()

    if season:
        games = pd.read_sql_query(
            """
            SELECT season, week, home_team, away_team, home_score, away_score
            FROM games
            WHERE season = ? AND (home_team LIKE ? OR away_team LIKE ?)
            ORDER BY CASE WHEN week GLOB '[0-9]*' THEN CAST(week AS INTEGER) ELSE 100 END
            """,
            conn,
            params=(season, f"%{team}%", f"%{team}%"),
        )
    else:
        games = pd.read_sql_query(
            """
            SELECT season, week, home_team, away_team, home_score, away_score
            FROM games
            WHERE home_team LIKE ? OR away_team LIKE ?
            ORDER BY season, CASE WHEN week GLOB '[0-9]*' THEN CAST(week AS INTEGER) ELSE 100 END
            """,
            conn,
            params=(f"%{team}%", f"%{team}%"),
        )
    conn.close()

    # Recalculate to get this team's history
    ratings = calculate_elo_ratings(season)
    return ratings[ratings["team"].str.contains(team, case=False)]


# ============================================================================
# Divisional Analysis
# ============================================================================


def get_divisional_records(season: int) -> pd.DataFrame:
    """Get win-loss records within and outside division for each team."""
    return query(
        """
        WITH game_results AS (
            SELECT
                g.season,
                g.home_team as team,
                g.away_team as opponent,
                CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END as win,
                CASE WHEN g.home_score < g.away_score THEN 1 ELSE 0 END as loss,
                CASE WHEN g.home_score = g.away_score THEN 1 ELSE 0 END as tie,
                t1.division as team_div,
                t2.division as opp_div,
                t1.conference as team_conf,
                t2.conference as opp_conf
            FROM games g
            JOIN teams t1 ON g.home_team = t1.name
            JOIN teams t2 ON g.away_team = t2.name
            WHERE g.season = ? AND g.is_playoff = 0

            UNION ALL

            SELECT
                g.season,
                g.away_team as team,
                g.home_team as opponent,
                CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END as win,
                CASE WHEN g.away_score < g.home_score THEN 1 ELSE 0 END as loss,
                CASE WHEN g.away_score = g.home_score THEN 1 ELSE 0 END as tie,
                t1.division as team_div,
                t2.division as opp_div,
                t1.conference as team_conf,
                t2.conference as opp_conf
            FROM games g
            JOIN teams t1 ON g.away_team = t1.name
            JOIN teams t2 ON g.home_team = t2.name
            WHERE g.season = ? AND g.is_playoff = 0
        )
        SELECT
            team,
            team_conf || ' ' || team_div as division,
            SUM(CASE WHEN team_div = opp_div AND team_conf = opp_conf THEN win ELSE 0 END) as div_wins,
            SUM(CASE WHEN team_div = opp_div AND team_conf = opp_conf THEN loss ELSE 0 END) as div_losses,
            SUM(CASE WHEN team_div != opp_div OR team_conf != opp_conf THEN win ELSE 0 END) as non_div_wins,
            SUM(CASE WHEN team_div != opp_div OR team_conf != opp_conf THEN loss ELSE 0 END) as non_div_losses,
            SUM(win) as total_wins,
            SUM(loss) as total_losses
        FROM game_results
        GROUP BY team, team_conf, team_div
        ORDER BY total_wins DESC, div_wins DESC
        """,
        (season, season),
    )


def get_conference_records(season: int) -> pd.DataFrame:
    """Get win-loss records within and outside conference."""
    return query(
        """
        WITH game_results AS (
            SELECT
                g.home_team as team,
                t1.conference as team_conf,
                t2.conference as opp_conf,
                CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END as win,
                CASE WHEN g.home_score < g.away_score THEN 1 ELSE 0 END as loss
            FROM games g
            JOIN teams t1 ON g.home_team = t1.name
            JOIN teams t2 ON g.away_team = t2.name
            WHERE g.season = ? AND g.is_playoff = 0

            UNION ALL

            SELECT
                g.away_team as team,
                t1.conference as team_conf,
                t2.conference as opp_conf,
                CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END as win,
                CASE WHEN g.away_score < g.home_score THEN 1 ELSE 0 END as loss
            FROM games g
            JOIN teams t1 ON g.away_team = t1.name
            JOIN teams t2 ON g.home_team = t2.name
            WHERE g.season = ? AND g.is_playoff = 0
        )
        SELECT
            team,
            team_conf as conference,
            SUM(CASE WHEN team_conf = opp_conf THEN win ELSE 0 END) as conf_wins,
            SUM(CASE WHEN team_conf = opp_conf THEN loss ELSE 0 END) as conf_losses,
            SUM(CASE WHEN team_conf != opp_conf THEN win ELSE 0 END) as non_conf_wins,
            SUM(CASE WHEN team_conf != opp_conf THEN loss ELSE 0 END) as non_conf_losses
        FROM game_results
        GROUP BY team, team_conf
        ORDER BY conf_wins DESC
        """,
        (season, season),
    )


def get_division_standings(season: int, conference: str = None, division: str = None) -> pd.DataFrame:
    """Get standings for a division or all divisions."""
    base_query = """
        WITH game_results AS (
            SELECT home_team as team,
                   CASE WHEN home_score > away_score THEN 1 ELSE 0 END as win,
                   home_score as pf, away_score as pa
            FROM games WHERE season = ? AND is_playoff = 0
            UNION ALL
            SELECT away_team as team,
                   CASE WHEN away_score > home_score THEN 1 ELSE 0 END as win,
                   away_score as pf, home_score as pa
            FROM games WHERE season = ? AND is_playoff = 0
        )
        SELECT
            t.conference || ' ' || t.division as division,
            t.name as team,
            SUM(gr.win) as wins,
            COUNT(*) - SUM(gr.win) as losses,
            SUM(gr.pf) as points_for,
            SUM(gr.pa) as points_against,
            SUM(gr.pf) - SUM(gr.pa) as point_diff
        FROM teams t
        JOIN game_results gr ON t.name = gr.team
    """

    params = [season, season]

    if conference and division:
        base_query += " WHERE t.conference = ? AND t.division = ?"
        params.extend([conference, division])
    elif conference:
        base_query += " WHERE t.conference = ?"
        params.append(conference)

    base_query += " GROUP BY t.name, t.conference, t.division ORDER BY t.conference, t.division, wins DESC"

    return query(base_query, tuple(params))


def get_division_strength(
    season: int = None,
    start_year: int = None,
    team: str = None,
) -> pd.DataFrame:
    """
    Calculate division strength based on how division rivals perform against non-division opponents.

    For each team, this shows the combined W/L record of their division rivals
    when playing teams outside the division.

    Args:
        season: Single season year (if provided, only this year)
        start_year: Start year for multi-year calculation
        team: Optional team name to filter results

    Returns:
        DataFrame with division strength metrics
    """
    # Build the WHERE clause for season filtering
    if season:
        season_filter = "g.season = ?"
        params = [season, season, season]
    elif start_year:
        season_filter = "g.season >= ?"
        params = [start_year, start_year, start_year]
    else:
        season_filter = "1=1"  # No filter - all years
        params = []

    base_query = f"""
        WITH division_games AS (
            -- Identify all division matchups
            SELECT g.id,
                   g.home_team, g.away_team,
                   t1.conference as home_conf, t1.division as home_div,
                   t2.conference as away_conf, t2.division as away_div
            FROM games g
            JOIN teams t1 ON g.home_team = t1.name
            JOIN teams t2 ON g.away_team = t2.name
            WHERE {season_filter} AND g.is_playoff = 0
        ),
        non_div_results AS (
            -- Get results for non-division games only
            SELECT
                g.home_team as team,
                t.conference, t.division,
                CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END as win,
                CASE WHEN g.home_score < g.away_score THEN 1 ELSE 0 END as loss
            FROM games g
            JOIN teams t ON g.home_team = t.name
            JOIN division_games dg ON g.id = dg.id
            WHERE {season_filter} AND g.is_playoff = 0
              AND NOT (dg.home_conf = dg.away_conf AND dg.home_div = dg.away_div)

            UNION ALL

            SELECT
                g.away_team as team,
                t.conference, t.division,
                CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END as win,
                CASE WHEN g.away_score < g.home_score THEN 1 ELSE 0 END as loss
            FROM games g
            JOIN teams t ON g.away_team = t.name
            JOIN division_games dg ON g.id = dg.id
            WHERE {season_filter} AND g.is_playoff = 0
              AND NOT (dg.home_conf = dg.away_conf AND dg.home_div = dg.away_div)
        ),
        team_non_div AS (
            -- Each team's non-division record
            SELECT team, conference, division,
                   SUM(win) as wins, SUM(loss) as losses
            FROM non_div_results
            GROUP BY team, conference, division
        ),
        division_strength AS (
            -- For each team, sum up their division RIVALS' non-division records
            SELECT
                t1.name as team,
                t1.conference || ' ' || t1.division as division,
                SUM(t2.wins) as rivals_wins,
                SUM(t2.losses) as rivals_losses,
                ROUND(100.0 * SUM(t2.wins) / (SUM(t2.wins) + SUM(t2.losses)), 1) as rivals_win_pct
            FROM teams t1
            JOIN team_non_div t2
              ON t1.conference = t2.conference
             AND t1.division = t2.division
             AND t1.name != t2.team
            GROUP BY t1.name, t1.conference, t1.division
        )
        SELECT * FROM division_strength
    """

    if team:
        base_query += " WHERE team LIKE ?"
        params.append(f"%{team}%")

    base_query += " ORDER BY rivals_win_pct DESC"

    return query(base_query, tuple(params))


def get_all_division_strengths(
    season: int = None,
    start_year: int = None,
) -> pd.DataFrame:
    """
    Get division strength rankings - which divisions are toughest based on
    combined non-division performance of all teams in each division.

    Args:
        season: Single season year
        start_year: Start year for multi-year calculation

    Returns:
        DataFrame with division strength rankings
    """
    # Build the WHERE clause for season filtering
    if season:
        season_filter = "g.season = ?"
        params = (season, season, season)
    elif start_year:
        season_filter = "g.season >= ?"
        params = (start_year, start_year, start_year)
    else:
        season_filter = "1=1"
        params = ()

    return query(
        f"""
        WITH division_games AS (
            SELECT g.id,
                   t1.conference as home_conf, t1.division as home_div,
                   t2.conference as away_conf, t2.division as away_div
            FROM games g
            JOIN teams t1 ON g.home_team = t1.name
            JOIN teams t2 ON g.away_team = t2.name
            WHERE {season_filter} AND g.is_playoff = 0
        ),
        non_div_results AS (
            SELECT
                t.conference, t.division,
                CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END as win,
                CASE WHEN g.home_score < g.away_score THEN 1 ELSE 0 END as loss
            FROM games g
            JOIN teams t ON g.home_team = t.name
            JOIN division_games dg ON g.id = dg.id
            WHERE {season_filter} AND g.is_playoff = 0
              AND NOT (dg.home_conf = dg.away_conf AND dg.home_div = dg.away_div)

            UNION ALL

            SELECT
                t.conference, t.division,
                CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END as win,
                CASE WHEN g.away_score < g.home_score THEN 1 ELSE 0 END as loss
            FROM games g
            JOIN teams t ON g.away_team = t.name
            JOIN division_games dg ON g.id = dg.id
            WHERE {season_filter} AND g.is_playoff = 0
              AND NOT (dg.home_conf = dg.away_conf AND dg.home_div = dg.away_div)
        )
        SELECT
            conference || ' ' || division as division,
            SUM(win) as wins,
            SUM(loss) as losses,
            ROUND(100.0 * SUM(win) / (SUM(win) + SUM(loss)), 1) as win_pct
        FROM non_div_results
        GROUP BY conference, division
        ORDER BY win_pct DESC
        """,
        params,
    )


# ============================================================================
# General Queries
# ============================================================================


def get_team_schedule(team: str, season: int) -> pd.DataFrame:
    """Get a team's schedule and results for a season."""
    return query(
        """
        SELECT
            week,
            game_date,
            CASE WHEN home_team LIKE ? THEN away_team ELSE home_team END as opponent,
            CASE WHEN home_team LIKE ? THEN 'vs' ELSE '@' END as location,
            CASE WHEN home_team LIKE ? THEN home_score ELSE away_score END as team_score,
            CASE WHEN home_team LIKE ? THEN away_score ELSE home_score END as opp_score,
            CASE
                WHEN (home_team LIKE ? AND home_score > away_score) OR
                     (away_team LIKE ? AND away_score > home_score) THEN 'W'
                WHEN home_score = away_score THEN 'T'
                ELSE 'L'
            END as result
        FROM games
        WHERE season = ? AND (home_team LIKE ? OR away_team LIKE ?)
        ORDER BY CASE WHEN week GLOB '[0-9]*' THEN CAST(week AS INTEGER) ELSE 100 END
        """,
        (f"%{team}%",) * 6 + (season,) + (f"%{team}%",) * 2,
    )


def get_head_to_head(team1: str, team2: str, start_year: int = None) -> pd.DataFrame:
    """Get head-to-head matchup history between two teams."""
    if start_year:
        return query(
            """
            SELECT
                season, week, game_date,
                home_team, away_team,
                home_score, away_score,
                CASE
                    WHEN home_team LIKE ? AND home_score > away_score THEN ?
                    WHEN away_team LIKE ? AND away_score > home_score THEN ?
                    WHEN home_score = away_score THEN 'Tie'
                    ELSE (SELECT name FROM teams WHERE name LIKE ? OR name LIKE ? LIMIT 1)
                END as winner
            FROM games
            WHERE season >= ? AND (
                (home_team LIKE ? AND away_team LIKE ?) OR
                (home_team LIKE ? AND away_team LIKE ?)
            )
            ORDER BY season DESC, week
            """,
            (
                f"%{team1}%", team1, f"%{team1}%", team1,
                f"%{team2}%", f"%{team2}%",
                start_year,
                f"%{team1}%", f"%{team2}%",
                f"%{team2}%", f"%{team1}%",
            ),
        )
    return query(
        """
        SELECT
            season, week, game_date,
            home_team, away_team,
            home_score, away_score
        FROM games
        WHERE (home_team LIKE ? AND away_team LIKE ?) OR
              (home_team LIKE ? AND away_team LIKE ?)
        ORDER BY season DESC, week
        """,
        (f"%{team1}%", f"%{team2}%", f"%{team2}%", f"%{team1}%"),
    )


def biggest_upsets(season: int, limit: int = 10) -> pd.DataFrame:
    """Find biggest point differential upsets (home team lost by large margin)."""
    return query(
        """
        SELECT
            week, game_date,
            home_team, away_team,
            home_score, away_score,
            ABS(home_score - away_score) as margin
        FROM games
        WHERE season = ? AND is_playoff = 0
        ORDER BY margin DESC
        LIMIT ?
        """,
        (season, limit),
    )


def summary_stats() -> pd.DataFrame:
    """Get summary statistics across all seasons."""
    return query("""
        SELECT
            season,
            COUNT(*) as games,
            SUM(CASE WHEN is_playoff = 0 THEN 1 ELSE 0 END) as regular,
            SUM(is_playoff) as playoff,
            ROUND(AVG(home_score + away_score), 1) as avg_total_pts,
            SUM(CASE WHEN home_score > away_score THEN 1 ELSE 0 END) as home_wins,
            ROUND(100.0 * SUM(CASE WHEN home_score > away_score THEN 1 ELSE 0 END) / COUNT(*), 1) as home_win_pct
        FROM games
        GROUP BY season
        ORDER BY season DESC
    """)


# ============================================================================
# CLI
# ============================================================================


def print_df(df: pd.DataFrame, title: str = None):
    """Pretty print a DataFrame."""
    if title:
        print(f"\n{'=' * 60}")
        print(f" {title}")
        print("=" * 60)
    print(df.to_string(index=False))
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze NFL game data")
    parser.add_argument("--summary", action="store_true", help="Show summary stats")
    parser.add_argument("--elo", action="store_true", help="Calculate current ELO ratings")
    parser.add_argument("--year", type=int, help="Season to analyze (single year)")
    parser.add_argument("--start-year", type=int, help="Start year for ELO calculation (use with --elo)")
    parser.add_argument("--team", type=str, help="Team name to look up")
    parser.add_argument("--vs", type=str, help="Head-to-head opponent (use with --team)")
    parser.add_argument("--division", action="store_true", help="Show divisional records")
    parser.add_argument("--standings", action="store_true", help="Show division standings")
    parser.add_argument("--div-strength", action="store_true", help="Division strength (rivals' non-div record)")
    parser.add_argument("--sql", type=str, help="Run a custom SQL query")
    parser.add_argument("--limit", type=int, default=10, help="Limit results")

    args = parser.parse_args()

    try:
        if args.sql:
            print_df(query(args.sql), "Custom Query")

        elif args.elo:
            start = args.start_year
            year = args.year
            if year:
                title = f"ELO Ratings ({year})"
                df = calculate_elo_ratings(season=year)
            elif start:
                title = f"ELO Ratings (since {start})"
                df = calculate_elo_ratings(start_year=start)
            else:
                title = "ELO Ratings (all time)"
                df = calculate_elo_ratings()
            print_df(df, title)

        elif args.team and args.vs:
            print_df(get_head_to_head(args.team, args.vs), f"{args.team} vs {args.vs}")

        elif args.team and args.year:
            print_df(get_team_schedule(args.team, args.year), f"{args.team} {args.year} Schedule")

        elif args.division and args.year:
            print_df(get_divisional_records(args.year), f"Divisional Records {args.year}")

        elif args.standings and args.year:
            print_df(get_division_standings(args.year), f"Division Standings {args.year}")

        elif args.div_strength:
            year = args.year
            start = args.start_year
            team = args.team

            # Determine title suffix
            if year:
                title_suffix = f"({year})"
            elif start:
                title_suffix = f"(since {start})"
            else:
                title_suffix = "(all time)"

            if team:
                print_df(
                    get_division_strength(season=year, start_year=start, team=team),
                    f"Division Strength for {team} {title_suffix}",
                )
            else:
                print_df(
                    get_all_division_strengths(season=year, start_year=start),
                    f"Division Strength Rankings {title_suffix}",
                )
                print_df(
                    get_division_strength(season=year, start_year=start),
                    f"Per-Team Division Strength {title_suffix}",
                )

        elif args.year:
            print_df(get_division_standings(args.year), f"Standings {args.year}")
            print_df(biggest_upsets(args.year, args.limit), f"Biggest Margins {args.year}")

        elif args.summary or not any(vars(args).values()):
            print_df(summary_stats(), "Summary Statistics")
            print_df(calculate_elo_ratings().head(args.limit), f"Current ELO Rankings (Top {args.limit})")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Run: python nfl_scraper.py")
