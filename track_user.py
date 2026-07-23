# for each distinct user in databse, check their rankings every X minutes (perhaps 3 min?)
# if rating stays the same in a format, don't add new row to database. if rating does change for specific format, add row
# also need to process new formats user might have started since adding their username to database

import schedule
import time
from showdown_client import fetch_current_ratings, ShowdownUnavailableError, ShowdownUserError
from app import db, PlayerRating, MatchHistory, app
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

            if df.empty:
                continue

            null_placeholder = (
                db.session.query(PlayerRating)
                .filter(
                    PlayerRating.userid == userid,
                    (PlayerRating.format.is_(None)) | (PlayerRating.format == "None")
                )
                .first()
            )

            if null_placeholder:
                first_real_format = df.iloc[0]["format"]

                existing_format_row = (
                    db.session.query(PlayerRating)
                    .filter(
                        PlayerRating.userid == userid,
                        PlayerRating.format == first_real_format
                    )
                    .first()
                )

                if not existing_format_row:
                    null_placeholder.format = first_real_format
                    null_placeholder.username = df.iloc[0]["username"]

                db.session.commit()

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

                prev_wins = latest_in_db.wins if latest_in_db else 0
                prev_losses = latest_in_db.losses if latest_in_db else 0

                raw_prev_wins = prev_wins
                raw_prev_losses = prev_losses

                if latest_in_db and (new_wins < latest_in_db.wins):
                    raw_prev_wins = 0

                if latest_in_db and (new_losses < latest_in_db.losses):
                    raw_prev_losses = 0

                win_diff = new_wins - raw_prev_wins
                loss_diff = new_losses - raw_prev_losses

                if win_diff == 0 and loss_diff == 0:
                    continue

                for _ in range(win_diff):
                    db.session.add(MatchHistory(
                        userid=userid, 
                        format=fmt, 
                        indicator='W', 
                        timestamp=row["timestamp"]
                    ))

                for _ in range(loss_diff):
                    db.session.add(MatchHistory(
                        userid=userid, 
                        format=fmt, 
                        indicator='L', 
                        timestamp=row["timestamp"]
                    ))

                db.session.flush()

                matches = (
                    db.session.query(MatchHistory)
                    .filter_by(userid=userid, format=fmt)
                    .order_by(MatchHistory.timestamp.desc())
                    .all()
                )

                if len(matches) > 10:
                    for old_match in matches[10:]:
                        db.session.delete(old_match)

                accumulated_wins = prev_wins + win_diff
                accumulated_losses = prev_losses + loss_diff

                db.session.add(
                    PlayerRating(
                        userid = userid,
                        username = row["username"],
                        format = fmt,
                        elo = new_elo,
                        gxe = new_gxe,
                        wins = accumulated_wins,
                        losses = accumulated_losses,
                        timestamp = row["timestamp"],
                    )
                )
        db.session.commit()


if __name__ == "__main__":
    grab_new()