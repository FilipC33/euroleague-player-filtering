import pandas as pd
import streamlit as st
from euroleague_api.player_stats import PlayerStats

# 1. Load data from the live API 
player_stats = PlayerStats("E")
df = player_stats.get_player_stats_single_season(
    endpoint="traditional",
    season=2025,
    statistic_mode="PerGame"
)

st.title("EuroLeague Player Filter")

# 2. UI Controls (Sidebar)
max_mins = st.sidebar.number_input(
    "Max Minutes Played:",
    min_value=1,
    max_value=40,
    value=15,
    step=1
)
def format_minutes(decimal_minutes):
    minutes = int(decimal_minutes)
    seconds = int(round((decimal_minutes - minutes) * 60))
    return f"{minutes}:{seconds:02d}"

df["Min_display"] = df["minutesPlayed"].apply(format_minutes)
stat_to_sort = st.sidebar.selectbox(
    "Sort By Stat:",
    ["pointsScored", "assists", "totalRebounds", "freeThrowsPercentage", "threePointersPercentage", "pir"]
)
top_n = st.sidebar.slider("Show Top Players:", min_value=1, max_value=208, value=10)
df["player.team.name"] = df["player.team.name"].str.split(";").str[-1]
team_options = ["All"] + sorted(df["player.team.name"].unique().tolist())
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
qualified = df[df[volume_stat] >= min_volume]
st.subheader(f"Best {rate_stat} among players with {volume_stat} ≥ {min_volume}")
st.dataframe(
    qualified[["player.name", "player.team.name", volume_stat, rate_stat]]
    .sort_values(rate_stat, ascending=False)
    .reset_index(drop=True)
    .head(10)
)

# 3. Dynamic Pandas Filtering
filtered = df[df["minutesPlayed"] <= max_mins]

if selected_team != "All":
    filtered = filtered[filtered["player.team.name"] == selected_team]

sorted_df = filtered.sort_values(stat_to_sort, ascending=False)

# 4. Display Interactive Table
st.subheader(f"Top Players (≤ {max_mins} mins) sorted by {stat_to_sort}")
st.dataframe(
    sorted_df[["player.name", "player.team.name", "Min_display", stat_to_sort]]
    .reset_index(drop=True)
    .head(top_n)
)
