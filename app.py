from flask import Flask, render_template, request
from flask_scss import Scss
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select
from showdown_client import fetch_current_ratings, ShowdownUnavailableError, ShowdownUserError
import pandas as pd
import re
import plotly.express as px
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc
from models import db, PlayerRating, MatchHistory
import os

app = Flask(__name__)
Scss(app)

db_url = os.getenv("DATABASE_URL", "sqlite:///elo.db")
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
db.init_app(app)

with app.app_context():
    db.create_all()

# embedded dash app in flask
dash_app = Dash(
    __name__,
    server=app,
    url_base_pathname="/elo/",
    external_stylesheets=[dbc.themes.DARKLY]
    )

dash_app.layout = html.Div([html.H2("Select a valid format")])

# dash helper app for plotly plots
def set_dash_layout(current_username, selected_format):
    stmt = (
        select(
            PlayerRating.userid,
            PlayerRating.format,
            PlayerRating.elo,
            PlayerRating.gxe,
            PlayerRating.timestamp,
            PlayerRating.wins,
            PlayerRating.losses
        )
        .where(
            PlayerRating.userid == current_username,
            PlayerRating.format == selected_format,
        )
        .order_by(PlayerRating.timestamp)
    )
    #query into df for plotly
    plots_df = pd.read_sql(stmt, db.engine)


    #### HANDLE BRAND NEW ACCOUNTS/'NONE' FORMAT ####
    if plots_df.empty or plots_df["format"].empty:
        fig = px.line(title="No data for this user/format",
                      template = "plotly_dark")

        pie_fig = px.pie(title = "No data for this user/format", 
                         template = "plotly_dark",
                         height=200)
        
        pie_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",   
        )

        peak_elo = 1000
        peak_gxe = 0
        current_elo = 1000
        current_gxe = 0
        total_games = 0
        wins = 0
        losses = 0

    elif len(plots_df) == 1:
        plots_df["elo"] = round(plots_df["elo"])
        plots_df["timestamp"] = plots_df["timestamp"].dt.strftime("%B %d %Y %I:%M %p")

        ###### time series elo plot ######
        fig = px.scatter(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"Elo Progression for {selected_format}",
            template = "plotly_dark"
        )
        fig.update_layout(
            title={
                'text': f"Elo Progression for {selected_format}",
                'y': 0.95,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8c9baf", family="Inter, sans-serif"),
            xaxis=dict(showticklabels = False, showgrid=False, zeroline=False),
            yaxis=dict(gridcolor="#2b3346", zeroline=False, dtick=50, tick0=50),
            margin=dict(l=50, r=30, t=60, b=40),
            autosize=True
        )

        fig.update_traces(line_color="#6c5ce7", line_width=3)
        ######## WL pie chart ########
        latest = plots_df.tail(1)
        wins = int(latest["wins"])
        losses = int(latest["losses"])
        pie_df = pd.DataFrame({
        'result': ['Wins', 'Losses'],
        'count': [wins, losses]
        })

        pie_fig = px.pie(
        pie_df,
        values = "count",
        names = "result",
        color = "result",
        color_discrete_map= {"Wins": "#4CAF50", "Losses": "#E84057"},
        hole = 0.7,
        template = "plotly_dark",
        height=200
        )
        pie_fig.update_traces(
        textposition="inside",
        textinfo="label+percent",
        marker=dict(line=dict(color="#111111", width=1)),
        pull=[0, 0],
        hoverinfo="label+value",
        textfont = {"color": "white"}
        )
        pie_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel = dict(font_color = "white")   
        )

        # misc stats display
        peak_elo = int(plots_df["elo"].max())
        peak_gxe = plots_df["gxe"].max()
        current_elo = int(latest["elo"])
        current_gxe = float(latest["gxe"])
        total_games = int(latest['wins'] + latest['losses'])

    

    else:
        plots_df["elo"] = round(plots_df["elo"])
        plots_df["timestamp"] = plots_df["timestamp"].dt.strftime("%B %d %Y %I:%M %p")

        ######## elo time-series ########
        fig = px.line(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"Elo Progression for {selected_format}",
            template = "plotly_dark"
        )

        fig.update_layout(
            title={
                'text': f"Elo Progression for {selected_format}",
                'y': 0.95,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8c9baf", family="Inter, sans-serif"),
            xaxis=dict(showticklabels = False, showgrid=False, zeroline=False),
            yaxis=dict(gridcolor="#2b3346", zeroline=False, dtick=50, tick0=50),
            margin=dict(l=50, r=30, t=60, b=40),
            autosize=True
        )

        fig.update_traces(line_color="#6c5ce7", line_width=3)

        ############ W/L PIE CHART #############
        latest = plots_df.tail(1)
        wins = int(latest["wins"])
        losses = int(latest["losses"])
        pie_df = pd.DataFrame({
        'result': ['Wins', 'Losses'],
        'count': [wins, losses]
        })

        pie_fig = px.pie(
        pie_df,
        values = "count",
        names = "result",
        color = "result",
        color_discrete_map= {"Wins": "#4CAF50", "Losses": "#E84057"},
        hole = 0.7,
        template = "plotly_dark",
        height=200
        )

        pie_fig.update_traces(
        textposition="inside",
        textinfo="percent",
        marker=dict(line=dict(color="#1c212e", width=2)),
        pull=[0, 0],
        hoverinfo="label+value",
        textfont={"color": "white", "size": 13}
        )
        pie_fig.update_layout(
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            hoverlabel=dict(font_color="white"),
            showlegend=True,
            autosize=True
        )

        #### misc stats ####
        peak_elo = int(plots_df["elo"].max())
        peak_gxe = plots_df["gxe"].max()
        current_elo = int(latest["elo"])
        current_gxe = float(latest["gxe"])
        total_games = int(latest['wins'] + latest['losses'])

        ### calculate last 10 games record ###
        recent_matches = (db.session.query(MatchHistory.indicator).filter_by(
            userid=current_username, format = selected_format).order_by(
                MatchHistory.timestamp.desc()).limit(10).all())
        wins = sum(1 for i in recent_matches if i.indicator == "W")
        losses = sum(1 for i in recent_matches if i.indicator == "L")

    card_stats = dbc.Card(
        [
            dbc.CardHeader("Player Statistics"),
            dbc.CardBody(
                [

                    dbc.Row(
                        [
                            dbc.Col([
                                html.Div("Current Elo ", className="stat-label"),
                                html.Div(f"{current_elo}", className="stat-value primary-stat")
                            ], width=6),
                            dbc.Col([
                                html.Div("Peak Elo ", className="stat-label"),
                                html.Div(f"{peak_elo}", className="stat-value")
                            ], width=6),
                        ],
                        className="mb-3"
                    ),

                    dbc.Row(
                        [
                            dbc.Col([
                                html.Div("Current GXE ", className="stat-label"),
                                html.Div(f"{current_gxe}%", className="stat-value primary-stat")
                            ], width=6),
                            dbc.Col([
                                html.Div("Peak GXE ", className="stat-label"),
                                html.Div(f"{peak_gxe}%", className="stat-value")
                            ], width=6),
                        ],
                        className="mb-3"
                    ),
                    html.Hr(className="stat-divider"),

                    dbc.Row(
                        [
                            dbc.Col([
                                html.Div("Recent Games ", className="stat-label"),
                                html.Div([
                                    html.Span(f"{wins}W ", className="badge-win"),
                                    html.Span(f"{losses}L", className="badge-loss"),
                                ])
                            ], width=6),
                            dbc.Col([
                                html.Div("Total Games ", className="stat-label"),
                                html.Div(f"{total_games}", className="stat-value")
                            ], width=6),
                        ]
                    )
                ]
            )
        ],
        className="h-100"
    )

    card_elo = dbc.Card(
        [
            dbc.CardHeader(f"{current_username} — {selected_format} Performance"),
            dbc.CardBody(
                [
                    dcc.Graph(
                        id="elo-graph", 
                        figure=fig,
                        config={'displayModeBar': False}
                    )
                ]
            )
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
                        config={'displayModeBar': False}
                    )
                ]
            )
        ]
    )

    teams_stats = dbc.Card(
        [
            dbc.CardHeader("Match History & Teams"),
            dbc.CardBody(
                [
                    html.Div(
                        "Match history details coming soon...", 
                        style={"color": "#8c9baf", "textAlign": "center", "padding": "40px 0"}
                    )
                ]
            )
        ]
    )

    ##### DISPLAY #####
    dash_app.layout = dbc.Container(
        [
            dbc.Row([dbc.Col(card_elo, width=12, className='mb-3')]), 

            dbc.Row(
                [
                    dbc.Col(card_stats, xs=12, md=4, className='mb-3'),
                    dbc.Col(card_wl, xs=12, md=4, className='mb-3'),
                    dbc.Col(teams_stats, xs=12, md=4, className='mb-3')
                ],
                className="g-3"
            )
        ],
        fluid=True,
        style={"padding": "20px 30px"}
    )

# Page
@app.route("/", methods = ["GET", "POST"])
def index():
    formats = []
    current_username = None
    error_message = None

    if request.method == "POST":
        # parse usernames to alphanumeric
        current_username = request.form["username"].strip().lower().replace(" ", "")
        current_username = re.sub(r'[^a-zA-Z0-9]', '', current_username)
        selected_format = request.form.get("format")

        # handle no input
        if not current_username:
            return render_template("index.html",
                                   current_username = current_username,
                                   formats = formats,
                                   error_message = ""
                                   )

        user_exists = (PlayerRating.query.filter_by(userid=current_username).first() is not None)

        if not user_exists:
            try:
                rating_df = fetch_current_ratings(current_username)

            except ShowdownUserError:
                error_message = "No user found."
                return render_template("index.html",
                                    current_username = None,
                                    formats = formats,
                                    error_message=error_message
                                    )

            except ShowdownUnavailableError:
                error_message = "Showdown is temporarily unavailable. Please try again later."

                return render_template("index.html", 
                                    current_username = None, 
                                    formats = formats,
                                    error_message = error_message
                                    )

        # add player & stats to db
            for _, row in rating_df.iterrows():
                player = PlayerRating(
                userid = row["userid"],
                username = row["username"],
                format = row["format"],
                elo = float(row["elo"]),
                gxe = float(row["gxe"]),
                wins = int(row["w"]),
                losses = int(row["l"]),
                timestamp = row["timestamp"],
                )
                db.session.add(player)
            db.session.commit()

        #querying all formats from user
        formats = (
            db.session.query(PlayerRating.format).filter(PlayerRating.userid == 
                                                            current_username).distinct().all()
                                                            )
        formats = [f[0] for f in formats]

        # pick first format if nothing is selected
        if not selected_format and formats:
            selected_format = formats[0]

        #### CALL DASH-PLOTLY VISUALIZATIONS ####
        if selected_format:
            set_dash_layout(current_username, selected_format)

        return render_template(
            "index.html",
            current_username = current_username,
            formats=formats,
            error_message = None,
            selected_format=selected_format
        )

    else:
        return render_template("index.html", 
                               current_username = current_username, 
                               formats = formats,
                               error_message = None
                               )


if __name__ == "__main__":
    app.run(host = '0.0.0.0', port = 8000, debug = True)