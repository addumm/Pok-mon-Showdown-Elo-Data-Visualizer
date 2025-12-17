from flask import Flask, render_template, request
from flask_scss import Scss
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select
from showdown_client import fetch_current_ratings, ShowdownUnavailableError, ShowdownUserError
import pandas as pd
import re
import plotly.express as px
from dash import Dash, html, dcc
from models import db, PlayerRating

app = Flask(__name__)
Scss(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///elo.db"
db.init_app(app)

# embedded dash app in flask
dash_app = Dash(
    __name__,
    server=app,
    url_base_pathname="/elo/"
    )

# dash helper for plotly plots
def set_dash_layout(current_username, selected_format):
    stmt = (
        select(
            PlayerRating.userid,
            PlayerRating.format,
            PlayerRating.elo,
            PlayerRating.timestamp,
        )
        .where(
            PlayerRating.userid == current_username,
            PlayerRating.format == selected_format,
        )
        .order_by(PlayerRating.timestamp)
    )

    plots_df = pd.read_sql(stmt, db.engine)

    if plots_df.empty:
        fig = px.line(title="No data for this user/format")
    else:
        fig = px.line(
            plots_df,
            x="timestamp",
            y="elo",
            title=f"{current_username} Elo Over Time for {selected_format}",
        )

    dash_app.layout = html.Div(
        [
            html.H2("Elo chart"),
            dcc.Graph(id="elo-graph", figure=fig),
        ]
    )
dash_app.layout = html.Div([html.H2("No chart yet. Go to / and submit a user.")])

# Page
@app.route("/", methods = ["GET", "POST"])
def index():
    formats = []
    current_username = None
    error_message = None

    if request.method == "POST":
        # parse usernames to alphanumeric
        raw_username = request.form["username"]
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
                               error_message = None,
                               graph_JSON = None
                               )


if __name__ in "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug = True)