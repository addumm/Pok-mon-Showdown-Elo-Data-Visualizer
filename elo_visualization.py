from app import db, PlayerRating, app
from sqlalchemy import select
import plotly.express as px
import pandas as pd


# for users with no games
def generate_placeholder_plot(userid: str):
    pass



# make dataframe to plot from via plotly
def df_for_plots(userid: str):
    query = select(
        PlayerRating.userid, PlayerRating.format, PlayerRating.elo, PlayerRating.timestamp).where(
            PlayerRating.userid == userid).order_by(PlayerRating.format, PlayerRating.timestamp)
    df = pd.read_sql_query(query, db.engine)
    return df