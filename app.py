from dash import Dash, Input, Output, dcc, html
import dash_bootstrap_components as dbc
from flask import Flask, render_template, request, has_request_context, Response, make_response, redirect, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_scss import Scss
from flask_sqlalchemy import SQLAlchemy
import json
import os
import pandas as pd
import plotly.express as px
import random
import re
from urllib.parse import parse_qs
from io import StringIO
from replay_parser import fetch_stats_concurrently
import pytz
from datetime import datetime
from collections import defaultdict

from showdown_client import (
    ShowdownUnavailableError,
    ShowdownUserError,
    fetch_current_ratings,
    get_sprite_url,
    replay_search,
    calculate_streaks
)
from sqlalchemy import select
from models import MatchHistory, PlayerRating, ReplayCache, db

app = Flask(__name__)
Scss(app)

db_url = os.getenv("DATABASE_URL", "sqlite:///elo.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
}

db.init_app(app)

with app.app_context():
    db.create_all()

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

# embedded Dash app inside Flask
dash_app = Dash(
    __name__,
    server=app,
    url_base_pathname="/elo/",
    external_stylesheets=[
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css",
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap",
        "/static/styles.css",
    ],
)

# static shell: dcc.Location tracks URL query parameters (?username=xxx&format=yyy)
dash_app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        html.Div(id="page-content"),
    ]
)

@dash_app.callback(
    Output("page-content", "children"),
    Input("url", "search"),
)
def render_page_content(search_str):
    if not search_str:
        return dbc.Container(
            [html.H4("Select a valid user and format from the main page.", className="text-muted mt-4")],
            fluid=True,
            style={"padding": "20px 30px"},
        )

    # parse query parameters from the browser iframe URL
    parsed = parse_qs(search_str.lstrip("?"))
    current_username = parsed.get("username", [None])[0]
    selected_format = parsed.get("format", [None])[0]

    if not current_username or not selected_format:
        return dbc.Container(
            [html.H4("Select a valid user and format from the main page.", className="text-muted mt-4")],
            fluid=True,
            style={"padding": "20px 30px"},
        )
    # cookie for user timezone
    user_tz = request.cookies.get("user_tz", "UTC") if has_request_context() else "UTC"

    stmt = (
        select(
            PlayerRating.userid,
            PlayerRating.format,
            PlayerRating.elo,
            PlayerRating.gxe,
            PlayerRating.timestamp,
            PlayerRating.wins,
            PlayerRating.losses,
        )
        .where(
            PlayerRating.userid == current_username,
            PlayerRating.format == selected_format,
        )
        .order_by(PlayerRating.timestamp)
    )
    plots_df = pd.read_sql(stmt, db.session.connection())

    ### if there is data in plots_df, format time and prep the plot with correct time ###
    if not plots_df.empty:
        plots_df["timestamp"] = pd.to_datetime(plots_df["timestamp"])

        if plots_df["timestamp"].dt.tz is None:
            plots_df["timestamp"] = plots_df["timestamp"].dt.tz_localize("UTC")

        try:
            plots_df["timestamp"] = plots_df["timestamp"].dt.tz_convert(user_tz)
        except Exception:
            pass

        plots_df["timestamp_str"] = plots_df["timestamp"].dt.strftime("%b %d, %Y %I:%M %p")

    # layout for Plotly figures matching the CSS theme
    plotly_layout_defaults = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#f1f2f6", family="Inter, sans-serif"),
        margin=dict(l=40, r=20, t=40, b=40),
        autosize=True,
    )

    # empty df
    if plots_df.empty or plots_df["format"].empty:
        fig = px.line(title="No data for this user/format", template="plotly_dark")
        fig.update_layout(**plotly_layout_defaults)
        
        pie_fig = px.pie(title="No data for this user/format", template="plotly_dark")
        pie_fig.update_layout(**plotly_layout_defaults)

        peak_elo, peak_gxe, current_elo, current_gxe, total_games, wins, losses = 1000, 0, 1000, 0, 0, 0, 0

    # single data point
    elif len(plots_df) == 1:
        plots_df["elo"] = round(plots_df["elo"])
        fig = px.scatter(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"Elo Progression — {selected_format}",
            template="plotly_dark",
        )
        fig.update_traces(marker=dict(color="#6c5ce7", size=10))
        fig.update_layout(
            **plotly_layout_defaults,
            xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
            yaxis=dict(gridcolor="rgba(255, 255, 255, 0.08)", zeroline=False, dtick=50),
        )

        latest = plots_df.tail(1)
        wins = int(latest["wins"].iloc[0])
        losses = int(latest["losses"].iloc[0])
        pie_df = pd.DataFrame({"result": ["Wins", "Losses"], "count": [wins, losses]})

        pie_fig = px.pie(
            pie_df,
            values="count",
            names="result",
            color="result",
            color_discrete_map={"Wins": "#2ed573", "Losses": "#ff4757"},
            hole=0.7,
            template="plotly_dark",
        )
        pie_fig.update_traces(
            textposition="inside",
            textinfo="percent",
            marker=dict(line=dict(color="#121824", width=2)),
            hoverinfo="label+value",
            textfont={"color": "white", "size": 13},
        )
        pie_fig.update_layout(**plotly_layout_defaults, showlegend=True, legend_itemclick=False)

        peak_elo = int(plots_df["elo"].max())
        peak_gxe = plots_df["gxe"].max()
        current_elo = int(latest["elo"].iloc[0])
        current_gxe = float(latest["gxe"].iloc[0])
        total_games = int(latest["wins"].iloc[0] + latest["losses"].iloc[0])

    # multiple data points
    else:
        plots_df["elo"] = round(plots_df["elo"])
        fig = px.line(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"Elo Progression — {selected_format}",
            template="plotly_dark",
        )
        fig.update_traces(
            line_color="#6c5ce7",
            line_width=3,
            fill="tozeroy",
            fillcolor="rgba(108, 92, 231, 0.15)",
        )

        min_elo = max(plots_df["elo"].min() - 50, 900)
        fig.update_layout(
            **plotly_layout_defaults,
            yaxis=dict(
                gridcolor="rgba(255, 255, 255, 0.08)",
                zeroline=False,
                range=[min_elo, plots_df["elo"].max() + 50],
            ),
        )
        fig.update_xaxes(type="category", showgrid=False, zeroline=False, showticklabels=False)

        latest = plots_df.tail(1)
        wins = int(latest["wins"].iloc[0])
        losses = int(latest["losses"].iloc[0])
        pie_df = pd.DataFrame({"result": ["Wins", "Losses"], "count": [wins, losses]})

        pie_fig = px.pie(
            pie_df,
            values="count",
            names="result",
            color="result",
            color_discrete_map={"Wins": "#2ed573", "Losses": "#ff4757"},
            hole=0.7,
            template="plotly_dark",
        )
        pie_fig.update_traces(
            textposition="inside",
            textinfo="percent",
            marker=dict(line=dict(color="#121824", width=2)),
            hoverinfo="label+value",
            textfont={"color": "white", "size": 13},
        )
        pie_fig.update_layout(**plotly_layout_defaults, showlegend=True, legend_itemclick=False)

        peak_elo = int(plots_df["elo"].max())
        peak_gxe = plots_df["gxe"].max()
        current_elo = int(latest["elo"].iloc[0])
        current_gxe = float(latest["gxe"].iloc[0])
        total_games = int((latest["wins"] + latest["losses"]).iloc[0])

        recent_matches = (
            db.session.query(MatchHistory.indicator)
            .filter_by(userid=current_username, format=selected_format)
            .order_by(MatchHistory.timestamp.desc())
            .limit(10)
            .all()
        )
        wins = sum(1 for i in recent_matches if i.indicator == "W")
        losses = sum(1 for i in recent_matches if i.indicator == "L")

    all_matches = (
        db.session.query(MatchHistory.indicator)
        .filter_by(userid=current_username, format=selected_format)
        .order_by(MatchHistory.timestamp.asc())
        .all()
    )
    match_indicators = [m.indicator for m in all_matches]
    longest_streak, current_streak = calculate_streaks(match_indicators)

    try:
        local_tz = pytz.timezone(user_tz)
    except Exception:
        local_tz = pytz.utc

    # get local time now and set to midnight (00:00:00)
    local_now = datetime.now(local_tz)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

    # convert local midnight to utc for database querying
    utc_midnight = local_midnight.astimezone(pytz.utc)

    # find the last rating recorded before local midnight today
    start_of_day_rating = (
        db.session.query(PlayerRating.elo)
        .filter(
            PlayerRating.userid == current_username,
            PlayerRating.format == selected_format,
            PlayerRating.timestamp < utc_midnight,
        )
        .order_by(PlayerRating.timestamp.desc())
        .first()
    )

    if start_of_day_rating and start_of_day_rating.elo:
        today_diff = int(round(current_elo - start_of_day_rating.elo))
        if today_diff > 0:
            today_diff_str = f"+{today_diff}"
        elif today_diff < 0:
            today_diff_str = f"{today_diff}"
        else:
            today_diff_str = "0"
    else:
        # if no games played before today, compare against initial entry of the day or show 0
        today_diff_str = "0"

    # --- CARDS WITH MATCHING CSS CLASSES ---
    teams_stats = dbc.Card(
        [
            dbc.CardHeader("Match History & Teams"),
            dbc.CardBody(
                [
                    dbc.Spinner(
                        html.Div(id="replays-container"),
                        color="primary",
                        type="border",
                        size="md",
                    )
                ],
                style={"padding": "16px"},
            ),
        ],
        className="card h-100",
    )

    mvp_mon = "N/A"

    cache_row = (
        db.session.query(ReplayCache.teams_json)
        .filter(
            ReplayCache.userid == current_username,
            ReplayCache.format == selected_format,
        )
        .order_by(ReplayCache.updated_at.desc())
        .first()
    )

    if cache_row and cache_row.teams_json:
        teams_dict = cache_row.teams_json
        if isinstance(teams_dict, str):
            try:
                teams_dict = json.loads(teams_dict)
            except Exception:
                teams_dict = {}

        if teams_dict:
            target_replays = list(teams_dict.keys())[:10]

            mon_brought_counts = defaultdict(int)
            for r_id in target_replays:
                pokemon_list = teams_dict.get(r_id, [])
                for mon in pokemon_list:
                    mon_brought_counts[mon] += 1

            if mon_brought_counts:
                # find replay stats only for tiebreaking move counts
                stats_map = fetch_stats_concurrently(target_replays, current_username, max_workers=5)
                mon_move_counts = defaultdict(int)

                for r_id in target_replays:
                    r_stats = stats_map.get(r_id)
                    if r_stats:
                        for mon, move_count in r_stats.get("moves_used", {}).items():
                            mon_move_counts[mon] += move_count

                # sort primarily by brought count, secondary by total moves used
                sorted_mons = sorted(
                    mon_brought_counts.keys(),
                    key=lambda mon: (mon_brought_counts[mon], mon_move_counts.get(mon, 0)),
                    reverse=True,
                )
                mvp_mon = sorted_mons[0]

    card_stats = dbc.Card(
    [
        dbc.CardHeader("Player Statistics"),
        dbc.CardBody(
            [
                # Row 1: Elo
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div("Current Elo", className="stat-label"),
                                html.Div(f"{current_elo}", className="stat-value primary-stat"),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.Div("Peak Elo", className="stat-label"),
                                html.Div(f"{peak_elo}", className="stat-value"),
                            ],
                            width=6,
                        ),
                    ],
                    className="mb-3",
                ),
                # Row 2: GXE
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div("Current GXE", className="stat-label"),
                                html.Div(f"{current_gxe}%", className="stat-value primary-stat"),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.Div("Peak GXE", className="stat-label"),
                                html.Div(f"{peak_gxe}%", className="stat-value"),
                            ],
                            width=6,
                        ),
                    ],
                ),
                html.Hr(style={"borderColor": "rgba(255, 255, 255, 0.08)", "margin": "16px 0"}),
                # Row 3: Recent / Total Games
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div("Recent Games", className="stat-label"),
                                html.Div(
                                    [
                                        html.Span(f"{wins}W ", className="badge-win"),
                                        html.Span(f"{losses}L", className="badge-loss"),
                                    ]
                                ),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.Div("Total Games", className="stat-label"),
                                html.Div(f"{total_games}", className="stat-value"),
                            ],
                            width=6,
                        ),
                    ],
                    className="mb-3",
                ),
                # Row 4: MVP & Today's Elo
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div("MVP (Last 10)", className="stat-label"),
                                html.Div(
                                    html.Span(
                                        f"{mvp_mon}",
                                        className="format-tag",
                                        style={"fontWeight": "600", "color": "#f1f2f6"},
                                    )
                                ),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.Div("Elo Gain/Loss Today", className="stat-label"),
                                html.Div(
                                    html.Span(
                                        f"{today_diff_str}",
                                        className=(
                                            "badge-win"
                                            if today_diff_str.startswith("+")
                                            else ("badge-loss" if today_diff_str.startswith("-") else "stat-value")
                                        ),
                                    )
                                ),
                            ],
                            width=6,
                        ),
                    ],
                ),
                html.Hr(style={"borderColor": "rgba(255, 255, 255, 0.08)", "margin": "16px 0"}),
                # Row 5: Streaks
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.Div("Longest Win Streak", className="stat-label"),
                                html.Div(
                                    html.Span(f"{longest_streak}W", className="badge-win"),
                                ),
                            ],
                            width=6,
                        ),
                        dbc.Col(
                            [
                                html.Div("Current Streak", className="stat-label"),
                                html.Div(
                                    html.Span(
                                        f"{current_streak}",
                                        className=(
                                            "badge-win"
                                            if "W" in current_streak
                                            else ("badge-loss" if "L" in current_streak else "stat-value")
                                        ),
                                    )
                                ),
                            ],
                            width=6,
                        ),
                    ]
                ),
            ],
            style={"padding": "20px"},
        ),
    ],
    className="card h-100",
)

    card_elo = dbc.Card(
        [
            dbc.CardHeader(f"{current_username} — {selected_format} Performance"),
            dbc.CardBody(
                [
                    dcc.Graph(
                        id="elo-graph",
                        figure=fig,
                        config={"displayModeBar": False},
                    )
                ],
                style={"padding": "10px"},
            ),
        ],
        className="card",
    )

    card_wl = dbc.Card(
        [
            dbc.CardHeader("Win / Loss Ratio"),
            dbc.CardBody(
                [
                    dcc.Graph(
                        id="wl-graph",
                        figure=pie_fig,
                        config={"displayModeBar": False},
                    )
                ],
                style={"padding": "10px"},
            ),
        ],
        className="card h-100",
    )

    return dbc.Container(
        [
            dcc.Store(id="store-username", data=current_username),
            dcc.Store(id="store-format", data=selected_format),
            
            # Top Full-Width Elo Chart
            dbc.Row(
                [
                    dbc.Col(card_elo, width=12),
                ],
                className="mb-4",
            ),
            
            # Bottom 3 Cards Side-by-Side Grid
            dbc.Row(
                [
                    dbc.Col(card_stats, xs=12, md=4, className="mb-3"),
                    dbc.Col(card_wl, xs=12, md=4, className="mb-3"),
                    dbc.Col(teams_stats, xs=12, md=4, className="mb-3"),
                ],
                className="g-3 d-flex flex-wrap",
            ),
        ],
        fluid=True,
        style={"maxWidth": "1280px", "margin": "0 auto", "padding": "20px"},
    )

@dash_app.callback(
    Output("replays-container", "children"),
    [
        Input("store-username", "data"),
        Input("store-format", "data"),
    ],
)
# replay & team caching
def load_replays_async(current_username, selected_format):
    if not current_username or not selected_format:
        return html.Div("No format selected.")

    cached = ReplayCache.query.filter_by(
        userid=current_username, format=selected_format
    ).first()

    user_teams = {}
    if cached and cached.teams_json:
        try:
            user_teams = json.loads(cached.teams_json)
        except Exception:
            user_teams = {}

    if not user_teams:
        try:
            user_teams = replay_search(current_username, selected_format)
            teams_str = json.dumps(user_teams) if user_teams else "{}"

            if not cached:
                cached = ReplayCache(
                    userid=current_username,
                    format=selected_format,
                    teams_json=teams_str,
                )
                db.session.add(cached)
            else:
                cached.teams_json = teams_str

            db.session.commit()
        except Exception as e:
            print(f"[REPLAY ASYNC ERROR]: {e}")
            user_teams = {}

    if user_teams:
        # grab up to 10 replay IDs
        target_replays = list(user_teams.keys())[:10]

        # BATCH FETCH ALL STATS CONCURRENTLY IN THREADS
        stats_map = fetch_stats_concurrently(target_replays, current_username, max_workers=5)

        replay_cards = []
        for replay_id in target_replays:
            team_species = user_teams[replay_id]
            replay_url = f"https://replay.pokemonshowdown.com/{replay_id}"

            sprite_imgs = [
                html.Img(
                    src=get_sprite_url(species),
                    title=species,
                    style={
                        "height": "40px",
                        "width": "40px",
                        "marginRight": "2px",
                        "objectFit": "contain",
                    },
                )
                for species in team_species
            ]

            # pull pre-fetched stats out of the dictionary
            stats = stats_map.get(replay_id)
            
            stats_content = []
            if stats and stats.get("move_usage"):
                for mon, moves in stats["move_usage"].items():
                    top_moves = ", ".join([f"{m} ({c}x)" for m, c in moves.items()])
                    stats_content.append(
                        html.Div(
                            [
                                html.Span(f"{mon}: ", style={"fontWeight": "600", "color": "#f1f2f6"}),
                                html.Span(top_moves, style={"color": "#768396", "fontSize": "0.75rem"}),
                            ],
                            style={"marginTop": "2px"}
                        )
                    )
            else:
                stats_content = [
                    html.Div("No detailed log stats available.", style={"color": "#768396", "fontSize": "0.75rem"})
                ]

            row = html.Div(
                [
                    html.Div(
                        [
                            html.A(
                                f"Replay: {replay_id}",
                                href=replay_url,
                                target="_blank",
                                style={
                                    "color": "#6c5ce7",
                                    "fontWeight": "600",
                                    "textDecoration": "none",
                                    "fontSize": "0.85rem",
                                },
                            ),
                        ],
                        style={"marginBottom": "4px"},
                    ),
                    html.Div(
                        sprite_imgs,
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "flexWrap": "wrap",
                            "marginBottom": "6px",
                        },
                    ),
                    html.Div(
                        stats_content,
                        style={
                            "borderTop": "1px solid rgba(255,255,255,0.05)",
                            "paddingTop": "6px",
                            "fontSize": "0.8rem"
                        }
                    )
                ],
                style={
                    "backgroundColor": "#121621",
                    "padding": "10px 14px",
                    "borderRadius": "8px",
                    "marginBottom": "10px",
                    "border": "1px solid #2b3346",
                },
            )
            replay_cards.append(row)

        return html.Div(
            replay_cards,
            style={
                "overflowY": "auto",
                "maxHeight": "350px",
                "paddingRight": "4px",
            },
        )
    else:
        return html.Div(
            "No public replays found for this format.",
            style={
                "color": "#8c9baf",
                "textAlign": "center",
                "padding": "40px 0",
                "fontSize": "0.9rem",
            },
        )

# Page
@app.route("/", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def index():
    formats = []
    current_username = None
    error_message = None
    selected_format = None
    dash_url = None
    random_pokemon_id = random.randint(1, 1025)

    if request.method == "POST":
        current_username = (
            request.form["username"].strip().lower().replace(" ", "")
        )
        current_username = re.sub(r"[^a-zA-Z0-9]", "", current_username)
        selected_format = request.form.get("format")

        if not current_username:
            return render_template(
                "index.html",
                current_username=current_username,
                formats=formats,
                error_message="",
            )

        user_exists = (
            PlayerRating.query.filter_by(userid=current_username).first()
            is not None
        )

        if not user_exists:
            try:
                rating_df = fetch_current_ratings(current_username)

            except ShowdownUserError:
                error_message = "No user found."
                return render_template(
                    "index.html",
                    current_username=None,
                    formats=formats,
                    error_message=error_message,
                )

            except ShowdownUnavailableError:
                error_message = "Showdown is temporarily unavailable. Please try again later."
                return render_template(
                    "index.html",
                    current_username=None,
                    formats=formats,
                    error_message=error_message,
                )

            for _, row in rating_df.iterrows():
                player = PlayerRating(
                    userid=row["userid"],
                    username=row["username"],
                    format=row["format"],
                    elo=float(row["elo"]),
                    gxe=float(row["gxe"]),
                    wins=int(row["w"]),
                    losses=int(row["l"]),
                    timestamp=row["timestamp"],
                )
                db.session.add(player)
            db.session.commit()

        formats = (
            db.session.query(PlayerRating.format)
            .filter(PlayerRating.userid == current_username)
            .distinct()
            .all()
        )
        formats = [f[0] for f in formats]

        if not selected_format and formats:
            selected_format = formats[0]

        if not selected_format:
            selected_format = "None"

        dash_url = f"/elo/?username={current_username}&format={selected_format}"

        return render_template(
            "index.html",
            current_username=current_username,
            formats=formats,
            error_message=None,
            selected_format=selected_format,
            dash_url=dash_url,
            header_sprite_id=random_pokemon_id,
        )

    else:
        return render_template(
            "index.html",
            current_username=current_username,
            formats=formats,
            error_message=None,
            header_sprite_id=random_pokemon_id,
        )
    
# for export data to csv button
@app.route("/export/<username>", methods=["GET"])
@limiter.limit("10 per minute")
def export_user_csv(username):
    clean_username = re.sub(r"[^a-zA-Z0-9]", "", username.strip().lower())

    stmt = (
        select(
            PlayerRating.format,
            PlayerRating.elo,
            PlayerRating.gxe,
            PlayerRating.wins,
            PlayerRating.losses,
            PlayerRating.timestamp,
        )
        .where(PlayerRating.userid == clean_username)
        .order_by(PlayerRating.timestamp.asc())
    )

    df = pd.read_sql(stmt, db.session.connection())

    if df.empty:
        return "No data found for this user.", 404

    # timestamp formatting spreadsheet readability
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # output directly to memory buffer (no temp file saved on server)
    output = StringIO()
    df.to_csv(output, index=False)

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = (
        f"attachment; filename={clean_username}_showdown_stats.csv"
    )
    response.headers["Content-Type"] = "text/csv"

    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)