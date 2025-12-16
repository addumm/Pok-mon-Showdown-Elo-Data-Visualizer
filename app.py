from flask import Flask, render_template, redirect, request
from flask_scss import Scss
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from showdown_client import fetch_current_ratings, ShowdownUnavailableError, ShowdownUserError
import pandas as pd
import re

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

    if request.method == "POST":
        # parse usernames to alphanumeric
        current_username = request.form["username"].strip().lower()
        current_username = re.sub(r'[^a-zA-Z0-9]', '', current_username)

        # handle no input
        if current_username == "":
            return render_template("index.html",
                                   current_username = current_username,
                                   formats = formats,
                                   error_message = ""
                                   )

        # CHECK IF USER IS ALREADY IN DB
        elif (PlayerRating.query.filter_by(userid=current_username).first() is not None):
            formats = (
            db.session.query(PlayerRating.format).filter(PlayerRating.userid == 
                                                            current_username).distinct().all()
                                                            )
            formats = [f[0] for f in formats]
            return render_template("index.html", 
                               current_username = current_username, 
                               formats = formats,
                               error_message = None
                               )            

        # else user is not in DB, try to hit showdown api for inputted username
        try:
            rating_df = fetch_current_ratings(current_username)

        except ShowdownUserError:
            error_message = "No user found."
            return render_template("index.html",
                                   current_username = None,
                                   formats = formats,
                                   error_message=error_message)

        except ShowdownUnavailableError:
            error_message = "Showdown is temporarily unavailable. Please try again later."

            return render_template("index.html", 
                                   current_username = None, 
                                   formats = formats,
                                   error_message = error_message)

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

        return render_template(
            "index.html",
            current_username = current_username,
            formats=formats,
            error_message = None
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