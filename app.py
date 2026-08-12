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

from showdown_client import (
    ShowdownUnavailableError,
    ShowdownUserError,
    fetch_current_ratings,
    get_sprite_url,
    replay_search,
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
    external_stylesheets=[dbc.themes.DARKLY],
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

    # if no data in plots_df
    if plots_df.empty or plots_df["format"].empty:
        fig = px.line(title="No data for this user/format", template="plotly_dark")
        pie_fig = px.pie(
            title="No data for this user/format",
            template="plotly_dark",
            height=200,
        )
        pie_fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")

        peak_elo = 1000
        peak_gxe = 0
        current_elo = 1000
        current_gxe = 0
        total_games = 0
        wins = 0
        losses = 0

    # if 1 data point
    elif len(plots_df) == 1:
        plots_df["elo"] = round(plots_df["elo"])
        plots_df["timestamp"] = plots_df["timestamp"].dt.strftime("%B %d %Y %I:%M %p")

        fig = px.scatter(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"Elo Progression for {selected_format}",
            template="plotly_dark",
        )
        fig.update_layout(
            title={
                "text": f"Elo Progression for {selected_format}",
                "y": 0.95,
                "x": 0.5,
                "xanchor": "center",
                "yanchor": "top",
            },
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8c9baf", family="Inter, sans-serif"),
            xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
            yaxis=dict(gridcolor="#2b3346", zeroline=False, dtick=50, tick0=50),
            margin=dict(l=50, r=30, t=60, b=40),
            autosize=True,
        )
        fig.update_traces(line_color="#6c5ce7", line_width=3)

        latest = plots_df.tail(1)
        wins = int(latest["wins"].iloc[0])
        losses = int(latest["losses"].iloc[0])
        pie_df = pd.DataFrame({"result": ["Wins", "Losses"], "count": [wins, losses]})

        pie_fig = px.pie(
            pie_df,
            values="count",
            names="result",
            color="result",
            color_discrete_map={"Wins": "#4CAF50", "Losses": "#E84057"},
            hole=0.7,
            template="plotly_dark",
            height=200,
        )
        pie_fig.update_traces(
            textposition="inside",
            textinfo="percent",
            marker=dict(line=dict(color="#1c212e", width=2)),
            pull=[0, 0],
            hoverinfo="label+value",
            textfont={"color": "white", "size": 13},
        )
        pie_fig.update_layout(
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hoverlabel=dict(font_color="white"),
            showlegend=True,
            autosize=True,
            legend_itemclick=False,
            legend_itemdoubleclick=False,
        )

        peak_elo = int(plots_df["elo"].max())
        peak_gxe = plots_df["gxe"].max()
        current_elo = int(latest["elo"].iloc[0])
        current_gxe = float(latest["gxe"].iloc[0])
        total_games = int(latest["wins"] + latest["losses"].iloc[0])

    # constructing plots for existing users w/ >1 data point 
    else:
        plots_df["elo"] = round(plots_df["elo"])
        plots_df["timestamp"] = plots_df["timestamp"].dt.strftime("%B %d %Y %I:%M %p")

        fig = px.line(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"Elo Progression for {selected_format}",
            template="plotly_dark",
        )
        fig.update_traces(
            line_color="#6c5ce7",
            line_width=3,
            fill="tozeroy",
            fillcolor="rgba(108, 92, 231, 0.18)",
        )

        min_elo = max(plots_df["elo"].min() - 50, 900)

        fig.update_layout(
            title={
                "text": f"Elo Progression for {selected_format}",
                "y": 0.95,
                "x": 0.5,
                "xanchor": "center",
                "yanchor": "top",
            },
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8c9baf", family="Inter, sans-serif"),
            yaxis=dict(
                gridcolor="#2b3346",
                zeroline=False,
                range=[min_elo, plots_df["elo"].max() + 50],
            ),
            margin=dict(l=50, r=30, t=60, b=40),
            autosize=True,
        )
        fig.update_xaxes(
            type="category",
            showgrid=False,
            zeroline=False,
            showticklabels=False,
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
            color_discrete_map={"Wins": "#4CAF50", "Losses": "#E84057"},
            hole=0.7,
            template="plotly_dark",
            height=200,
        )

        pie_fig.update_traces(
            textposition="inside",
            textinfo="percent",
            marker=dict(line=dict(color="#1c212e", width=2)),
            pull=[0, 0],
            hoverinfo="label+value",
            textfont={"color": "white", "size": 13},
        )
        pie_fig.update_layout(
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hoverlabel=dict(font_color="white"),
            showlegend=True,
            autosize=True,
            legend_itemclick=False,
            legend_itemdoubleclick=False,
        )

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

    ### teams/match history card ###
    teams_stats = dbc.Card(
        [
            dbc.CardHeader("Match History & Teams", style={"fontWeight": "600"}),
            dbc.CardBody(
                [
                    dbc.Spinner(
                        html.Div(id="replays-container"),
                        color="primary",
                        type="border",
                        size="md",
                    )
                ],
                style={"padding": "12px"},
            ),
        ],
        className="h-100",
    )

    # cards for player stats
    card_stats = dbc.Card(
        [
            dbc.CardHeader("Player Statistics"),
            dbc.CardBody(
                [
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Div("Current Elo ", className="stat-label"),
                                    html.Div(f"{current_elo}", className="stat-value primary-stat"),
                                ],
                                width=6,
                            ),
                            dbc.Col(
                                [
                                    html.Div("Peak Elo ", className="stat-label"),
                                    html.Div(f"{peak_elo}", className="stat-value"),
                                ],
                                width=6,
                            ),
                        ],
                        className="mb-3",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Div("Current GXE ", className="stat-label"),
                                    html.Div(f"{current_gxe}%", className="stat-value primary-stat"),
                                ],
                                width=6,
                            ),
                            dbc.Col(
                                [
                                    html.Div("Peak GXE ", className="stat-label"),
                                    html.Div(f"{peak_gxe}%", className="stat-value"),
                                ],
                                width=6,
                            ),
                        ],
                        className="mb-3",
                    ),
                    html.Hr(className="stat-divider"),
                    dbc.Row(
                        [
                            dbc.Col(
                                [
                                    html.Div("Recent Games ", className="stat-label"),
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
                                    html.Div("Total Games ", className="stat-label"),
                                    html.Div(f"{total_games}", className="stat-value"),
                                ],
                                width=6,
                            ),
                        ]
                    ),
                ]
            ),
        ],
        className="h-100",
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
                ]
            ),
        ]
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
                ]
            ),
        ]
    )

    return dbc.Container(
        [
            dcc.Store(id="store-username", data=current_username),
            dcc.Store(id="store-format", data=selected_format),
            dbc.Row([dbc.Col(card_elo, width=12, className="mb-3")]),
            dbc.Row(
                [
                    dbc.Col(card_stats, xs=12, md=4, className="mb-3"),
                    dbc.Col(card_wl, xs=12, md=4, className="mb-3"),
                    dbc.Col(teams_stats, xs=12, md=4, className="mb-3"),
                ],
                className="g-3",
            ),
        ],
        fluid=True,
        style={"padding": "20px 30px"},
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
        replay_cards = []
        for replay_id, team_species in list(user_teams.items())[:10]: ## can adjust to desired number of teams/replays shown
            replay_url = f"https://replay.pokemonshowdown.com/{replay_id}"

            sprite_imgs = [
                html.Img(
                    src=get_sprite_url(species),
                    title=species,
                    style={
                        "height": "48px",
                        "width": "48px",
                        "marginRight": "6px",
                        "objectFit": "contain",
                    },
                )
                for species in team_species
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
                        },
                    ),
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
                "maxHeight": "210px",
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