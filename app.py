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
from models import db, PlayerRating

app = Flask(__name__)
Scss(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///elo.db"
db.init_app(app)

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
        recent = "Record: 0W 0L"
        total_games = f"Total Games: 0"

    elif len(plots_df) == 1:
        plots_df["elo"] = round(plots_df["elo"])
        plots_df["timestamp"] = plots_df["timestamp"].dt.strftime("%B %d %Y %I:%M %p")

        ###### time series elo plot ######
        fig = px.scatter(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"Elo Over Time for {selected_format}",
            template = "plotly_dark"
            )
        fig.update_xaxes(showticklabels = False)

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
        recent = f"Current Record: {wins} - {losses}"
        total_games = f"Total Games: {int(latest['wins'] + latest['losses'])}"

    else:
        plots_df["elo"] = round(plots_df["elo"])
        plots_df["timestamp"] = plots_df["timestamp"].dt.strftime("%B %d %Y %I:%M %p")

        ######## elo time-series ########
        fig = px.line(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"Elo Over Time for {selected_format}",
            template = "plotly_dark"
        )
        fig.update_layout(
            yaxis=dict(
            dtick=100,
            tick0= 1000),
            xaxis_title="Timestamp",
            yaxis_title = "Elo"
        )
        fig.update_xaxes(showticklabels = False)

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

        #### misc stats ####
        peak_elo = int(plots_df["elo"].max())
        peak_gxe = plots_df["gxe"].max()
        current_elo = int(latest["elo"])
        current_gxe = float(latest["gxe"])
        total_games = f"Total Games: {int(latest['wins'] + latest['losses'])}"

        ### calculate last 10 games record ###
        last_10_df = plots_df.tail(10)
        recent = f"Recent Games: {int(last_10_df['wins'].iloc[-1] - last_10_df['wins'].iloc[0])}W {int(last_10_df['losses'].iloc[-1] - last_10_df['losses'].iloc[0])}L"

    #### Cards for layout ####
    card_elo = dbc.Card(
        [
            dbc.CardHeader(f"{current_username} {selected_format} Profile"),
            dbc.CardBody(
                [
                    dcc.Graph(id = "elo-graph", figure = fig)
                ]
            )
        ]
    )

    card_wl = dbc.Card(
        [
            dbc.CardHeader("Win-Loss", style={'textAlign': 'center'}),
            dbc.CardBody(
                [
                    dcc.Graph(id = "wl-graph", figure = pie_fig)
                ]

            )
        ]
    )

    card_stats = dbc.Card(
        [
            dbc.ListGroup(
                [
                    dbc.ListGroupItem(f"{recent}", style={'textAlign': 'center'}),
                    dbc.ListGroupItem(total_games, style={'textAlign': 'center'}),
                    dbc.ListGroupItem(f"Highest ELO: {peak_elo}", style={'textAlign': 'center'}),
                    dbc.ListGroupItem(f"Highest GXE: {peak_gxe}", style={'textAlign': 'center'}),
                    dbc.ListGroupItem(f"Current ELO: {current_elo}", style={'textAlign': 'center'}),
                    dbc.ListGroupItem(f"Current GXE: {current_gxe}", style = {'textAlign': 'center'})
                ]
            )
        ]
    )

    teams_stats = dbc.Card(
        [
            dbc.CardHeader("Recent Teams", style={'textAlign': 'center'}),
            dbc.CardBody(
                [
                    html.P("Coming soon!")
                ]
            )
        ]
    )

    ##### DISPLAY #####
    dash_app.layout = dbc.Container(
        [
            dbc.Row([dbc.Col(card_elo, width = 12, className='mb-2')]), 

            dbc.Row(
                [
                dbc.Col(card_wl, width = {'size': 4}, className='mb-2'),
                dbc.Col(card_stats, width = {'size': 4}, className='mb-2'),
                dbc.Col(teams_stats, width = {'size': 4}, className = 'mb-2')
                ]
                )
        ]
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

        # choose first format if nothing is selected
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


if __name__ in "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug = True)