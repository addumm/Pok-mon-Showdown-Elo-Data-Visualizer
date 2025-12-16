# for each distinct user in databse, check their rankings every X minutes (perhaps X = 3)?
# if rating stays the same in a format, don't add new row to database. if rating does change for specific format, add row
# also need to process new formats user might have started since adding their username to database

import schedule
import time
from showdown_client import fetch_current_ratings, ShowdownUnavailableError, ShowdownUserError
from app import db, PlayerRating, app
from sqlalchemy import select, desc


def grab_new():
    with app.app_context():
        stmt = select(PlayerRating.userid).distinct()
        userids = db.session.execute(stmt).scalars().all()
        for userid in userids:
            try:
                df = fetch_current_ratings(userid)

            except ShowdownUnavailableError:
                continue

            except ShowdownUserError:
                continue

            except Exception as e:
                continue

            for _, row in df.iterrows():
                fmt = row["format"]
                latest_in_db = (
                    db.session.query(PlayerRating).filter_by(userid = userid, format = fmt)
                    .order_by(PlayerRating.timestamp.desc()).first()
                )
                new_elo = float(row["elo"])
                new_wins = int(row["w"])
                new_losses = int(row["l"])
                new_gxe = float(row["gxe"])

                if latest_in_db and ((latest_in_db.wins == new_wins and 
                                     latest_in_db.losses == new_losses) or 
                                     latest_in_db.gxe == new_gxe):
                    continue

                db.session.add(
                    PlayerRating(
                        userid = userid,
                        username = row["username"],
                        format = fmt,
                        elo = new_elo,
                        gxe = new_gxe,
                        wins = new_wins,
                        losses = new_losses,
                        timestamp = row["timestamp"]

                    )
                )
        db.session.commit()


schedule.every(3).minutes.do(grab_new)


while True:
    schedule.run_pending()
    time.sleep(1)