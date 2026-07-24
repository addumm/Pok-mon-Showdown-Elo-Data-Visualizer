from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class PlayerRating(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    userid = db.Column(db.String(18), nullable=False, index = True)
    username = db.Column(db.String(18), nullable=False)
    format = db.Column(db.String)
    elo = db.Column(db.Float, nullable=False)
    gxe = db.Column(db.Float)
    wins = db.Column(db.Integer)
    losses = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"player {self.id}"

class MatchHistory(db.Model):
    __tablename__ = "match_history"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    userid = db.Column(db.String(18), nullable=False, index = True)
    format = db.Column(db.String, nullable = False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    indicator = db.Column(db.String(1), nullable = False)