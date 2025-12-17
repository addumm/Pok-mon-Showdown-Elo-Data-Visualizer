from flask import Flask, render_template, redirect, request
from flask_scss import Scss
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select
from datetime import datetime
from showdown_client import fetch_current_ratings, ShowdownUnavailableError, ShowdownUserError
import pandas as pd
import re
import json
from elo_visualization import df_for_plots
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder

app = Flask(__name__)
Scss(app)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///elo.db"
db = SQLAlchemy(app)

# Data Class
class PlayerRating(db.Model):
    id = db.Column(db.Integer, primary_key = True, autoincrement = True)
    userid = db.Column(db.String(18), nullable = False)
    username = db.Column(db.String(18), nullable = False)
    format = db.Column(db.String)
    elo = db.Column(db.Float, nullable = False)
    gxe = db.Column(db.Float)
    wins = db.Column(db.Integer)
    losses = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default = datetime.now)

    def __repr__(self) -> str:
        return f"player {self.id}"

# Page
@app.route("/", methods = ["GET", "POST"])
def index():
    formats = []
    current_username = None
    error_message = None
    graph_JSON = None

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
                                   error_message = "",
                                   graph_JSON = None
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
                                    error_message=error_message,
                                    graph_JSON = None)

            except ShowdownUnavailableError:
                error_message = "Showdown is temporarily unavailable. Please try again later."

                return render_template("index.html", 
                                    current_username = None, 
                                    formats = formats,
                                    error_message = error_message,
                                    graph_JSON = None)

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
            stmt = select(
                PlayerRating.userid,
                PlayerRating.format,
                PlayerRating.elo,
                PlayerRating.timestamp,).where(
                PlayerRating.userid == current_username,
                PlayerRating.format == selected_format).order_by(
                    PlayerRating.timestamp)
            
            plots_df = pd.read_sql(stmt, db.engine)
            plots_df["elo"] = pd.to_numeric(plots_df["elo"], errors="coerce")
            min_elo = plots_df["elo"].min()
            max_elo = plots_df["elo"].max()

            #TODO fix y axis/figure out why plotly is plotting elo as the row indices 0 to 11, not the elo values
            if not plots_df.empty:
                fig = px.line(plots_df, x = "timestamp", y = "elo", 
                              title = f"Elo Over Time for {selected_format}")
                fig.update_yaxes(
                    title_text="Elo",
                    range=[min_elo - 10, max_elo + 10],
                    type="linear",
                    tick0=round(min_elo / 50) * 50,
                    dtick=50,
    )
                
                graph_JSON = json.dumps(fig, cls=PlotlyJSONEncoder)

        return render_template(
            "index.html",
            current_username = current_username,
            formats=formats,
            error_message = None,
            graph_JSON = graph_JSON
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