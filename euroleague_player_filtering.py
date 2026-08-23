import os
import time

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Arc
import pandas as pd
import requests
import streamlit as st
from euroleague_api.player_stats import PlayerStats
from euroleague_api.shot_data import ShotData
from euroleague_api.standings import Standings

SEASON = 2025

DATA_DIR = "data_cache"
os.makedirs(DATA_DIR, exist_ok=True)


# Data loading

def _fetch_game_with_retry(shot_data: ShotData, season: int, game_code: int,
                            max_retries: int = 5) -> pd.DataFrame:
    """Fetch one game's shot data, retrying with backoff on 429s."""
    delay = 2.0
    for attempt in range(max_retries):
        try:
            return shot_data.get_game_shot_data(season, game_code)
        except requests.exceptions.HTTPError as err:
            status = err.response.status_code if err.response is not None else "?"
            if status == 429:
                time.sleep(delay)
                delay *= 2
                continue
            print(f"SKIPPED game {game_code}: HTTP {status}")
            return pd.DataFrame()
        except requests.exceptions.JSONDecodeError:
            print(f"SKIPPED game {game_code}: empty/invalid response body")
            return pd.DataFrame()
        except Exception as e:
            print(f"SKIPPED game {game_code}: unexpected error: {e}")
            return pd.DataFrame()
    print(f"GAVE UP on game {game_code} after {max_retries} retries")
    return pd.DataFrame()

# Load a season of shot data from disk cache

@st.cache_data(show_spinner="Loading full season shot data...") 
def load_shot_data(season: int, n_games: int = 399) -> pd.DataFrame: #399 games have been played in 2025-26 season
    """Load a season of shot data, from disk cache if we have it."""
    parquet_path = os.path.join(DATA_DIR, f"shots_{season}.parquet")
    if os.path.exists(parquet_path):
        return pd.read_parquet(parquet_path)

    shot_data = ShotData("E")
    all_games = []
    skipped = 0

# Loops through every possible game code (1 to 399) and fetches each one individually,

    for game_code in range(1, n_games + 1):
        df = _fetch_game_with_retry(shot_data, season, game_code)
        if not df.empty:
            all_games.append(df)
        else:
            skipped += 1
        time.sleep(2.0)

    print(f"Loaded {len(all_games)} games, skipped {skipped} (out of {n_games})")

    df = pd.concat(all_games, ignore_index=True)
    df["Result"] = df["ACTION"].str.contains("Missed").map({True: "Missed", False: "Made"})

    df.to_parquet(parquet_path)
    return df


@st.cache_data(show_spinner="Loading player stats...")
def load_player_stats(season: int) -> pd.DataFrame:
    """Load per-game player stats, from disk cache if we have it."""
    parquet_path = os.path.join(DATA_DIR, f"player_stats_{season}.parquet")
    if os.path.exists(parquet_path):
        return pd.read_parquet(parquet_path)

    player_stats = PlayerStats("E")
    df = player_stats.get_player_stats_single_season(
        endpoint="traditional",
        season=season,
        statistic_mode="PerGame",
    )

    df.to_parquet(parquet_path)
    return df


@st.cache_data(show_spinner="Loading team names...")
def build_team_code_to_name_map(season: int) -> dict:
    """Map team code (e.g. "IST") to full team name, via standings."""
    standings = Standings("E")
    df = standings.get_standings(season=season, round_number=1)
    return dict(zip(df["club.code"], df["club.name"]))


# Court + shot chart
# Draw a FIBA half-court in the same cm coordinate system as the shot data.

def draw_court(ax):
    """Draw a FIBA half-court, in the same cm coordinate system as the shot data."""
    ax.set_facecolor("#0e1117")
    line_color = "white"
    lw = 1.5

    ax.add_patch(Rectangle((-750, -150), 1500, 1550, fill=False,
                            edgecolor=line_color, linewidth=lw))
    ax.add_patch(Circle((0, 0), radius=22.5, fill=False,
                         edgecolor=line_color, linewidth=lw))
    ax.plot([-90, 90], [-15, -15], color=line_color, linewidth=lw)
    ax.add_patch(Arc((0, 0), 250, 250, theta1=0, theta2=180,
                      edgecolor=line_color, linewidth=lw))
    ax.add_patch(Rectangle((-245, -150), 490, 580, fill=False,
                            edgecolor=line_color, linewidth=lw))
    ax.add_patch(Arc((0, 430), 360, 360, theta1=0, theta2=180,
                      edgecolor=line_color, linewidth=lw))
    ax.add_patch(Arc((0, 430), 360, 360, theta1=180, theta2=360,
                      edgecolor=line_color, linewidth=lw, linestyle="dashed"))

    corner_y = 90
    ax.plot([-660, -660], [-150, corner_y], color=line_color, linewidth=lw)
    ax.plot([660, 660], [-150, corner_y], color=line_color, linewidth=lw)
    ax.add_patch(Arc((0, 0), 1350, 1350, theta1=12, theta2=168,
                      edgecolor=line_color, linewidth=lw))

    ax.set_xlim(-800, 800)
    ax.set_ylim(-200, 900)
    ax.set_aspect("equal")
    ax.axis("off")


def plot_shot_chart(player_shots: pd.DataFrame, player_name: str):
    fig, ax = plt.subplots(figsize=(8, 7.5))
    fig.patch.set_facecolor("#0e1117")

    draw_court(ax)

# Splits the player's shots into two groups and plots them as separate scatter layers so they get different colors (green/red)


    made = player_shots[player_shots["Result"] == "Made"]
    missed = player_shots[player_shots["Result"] == "Missed"]

    ax.scatter(made["COORD_X"], made["COORD_Y"], c="#00c04b", s=40,
               alpha=0.75, label="Made", edgecolors="none")
    ax.scatter(missed["COORD_X"], missed["COORD_Y"], c="#ff4b4b", s=40,
               alpha=0.75, label="Missed", edgecolors="none")

    ax.set_title(player_name, color="white", fontsize=14, pad=10)
    legend = ax.legend(loc="upper right", facecolor="#0e1117", edgecolor="white")
    for text in legend.get_texts():
        text.set_color("white")

    return fig


# Data loading

# Fetches one game's shots. If the API returns 429 (rate limited), which happened often, it waits and tries again
# Any other error (game doesn't exist, bad response) just gets skipped

shots_df = load_shot_data(SEASON)
player_df = load_player_stats(SEASON)

# player.team.name sometimes comes back as "OldName;NewName" for teams (eg. Nick Clathes - AS Monaco; KK Partizan)
# keeps only the current name.
player_df["player.team.name"] = player_df["player.team.name"].str.split(";").str[-1]

# Shot data only has team codes (e.g. "IST" for Anadolu Efes Istanbul); map to full names for display
_team_code_to_name = build_team_code_to_name_map(SEASON)
shots_df["TEAM_NAME"] = shots_df["TEAM"].map(_team_code_to_name).fillna(shots_df["TEAM"])


# Page layout

tab1, tab2 = st.tabs(["Player Filter", "Shot Chart"])

with tab1:
    st.title("EuroLeague Player Filter")

    # Reformat minutes played as MM:SS for display.
    def format_minutes(decimal_minutes):
        minutes = int(decimal_minutes)
        seconds = int(round((decimal_minutes - minutes) * 60))
        return f"{minutes}:{seconds:02d}"

    filter_df = player_df.copy()
    filter_df["Min_display"] = filter_df["minutesPlayed"].apply(format_minutes)

    # Sidebar controls
    max_mins = st.sidebar.number_input(
        "Max Minutes Played:", min_value=1, max_value=40, value=15, step=1
    )
    stat_to_sort = st.sidebar.selectbox(
        "Sort By Stat:",
        ["pointsScored", "assists", "totalRebounds", "freeThrowsPercentage",
         "threePointersPercentage", "pir"]
    )
    top_n = st.sidebar.slider("Show Top Players:", min_value=1, max_value=208, value=10)

    team_options = ["All"] + sorted(filter_df["player.team.name"].unique().tolist())
    selected_team = st.sidebar.selectbox("Filter By Team:", options=team_options)

    st.sidebar.subheader("Advanced Filter")
    volume_stat = st.sidebar.selectbox(
        "Minimum volume in:",
        ["freeThrowsAttempted", "twoPointersAttempted", "threePointersAttempted", "assists"]
    )
    min_volume = st.sidebar.number_input(f"Minimum {volume_stat}:", min_value=0.0, value=3.5, step=0.5)
    rate_stat = st.sidebar.selectbox(
        "Best rate in:",
        ["freeThrowsPercentage", "twoPointersPercentage", "threePointersPercentage"]
    )

    # Main filtered table
    filtered = filter_df[filter_df["minutesPlayed"] <= max_mins]
    if selected_team != "All":
        filtered = filtered[filtered["player.team.name"] == selected_team]
    sorted_df = filtered.sort_values(stat_to_sort, ascending=False)

    st.subheader(f"Top Players (≤ {max_mins} mins) sorted by {stat_to_sort}")
    st.dataframe(
        sorted_df[["player.name", "player.team.name", "Min_display", stat_to_sort]]
        .reset_index(drop=True)
        .head(top_n)
    )

    # Advanced filter table
    qualified = filter_df[filter_df[volume_stat] >= min_volume]
    st.subheader(f"Best {rate_stat} among players with {volume_stat} ≥ {min_volume}")
    st.dataframe(
        qualified[["player.name", "player.team.name", volume_stat, rate_stat]]
        .sort_values(rate_stat, ascending=False)
        .reset_index(drop=True)
        .head(10)
    )



with tab2:
    st.title("Shot Chart")

    choose_team = st.selectbox("Choose Team:", sorted(shots_df["TEAM_NAME"].unique().tolist()))

    players_on_team = shots_df[shots_df["TEAM_NAME"] == choose_team]["PLAYER"].unique().tolist()
    choose_player = st.selectbox("Choose Player:", sorted(players_on_team))

    # -1, -1 coordinates mean no real shot location (e.g. free throws).
    player_shots = shots_df[
        (shots_df["PLAYER"] == choose_player) & (shots_df["COORD_X"] != -1)
    ]

    st.pyplot(plot_shot_chart(player_shots, choose_player))