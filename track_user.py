from concurrent.futures import ThreadPoolExecutor, as_completed
from app import app
from models import MatchHistory, PlayerRating, db
from showdown_client import (
    fetch_current_ratings,
    ShowdownUnavailableError,
    ShowdownUserError,
)
from sqlalchemy import select

MAX_WORKERS = 6

def process_single_user(userid: str):
    """
    worker function executed in parallel
    processes a single user within an isolated application context thread
    """
    with app.app_context():
        try:
            df = fetch_current_ratings(userid)
        except (ShowdownUnavailableError, ShowdownUserError):
            return userid, False
        except Exception as e:
            print(f"[{userid}] Unexpected error during fetch: {e}")
            return userid, False

        if df.empty:
            return userid, False

        has_updates = False

        null_placeholder = (
            db.session.query(PlayerRating)
            .filter(
                PlayerRating.userid == userid,
                (PlayerRating.format.is_(None)) | (PlayerRating.format == "None"),
            )
            .first()
        )

        if null_placeholder:
            first_real_format = df.iloc[0]
            null_placeholder.username = first_real_format["username"]
            null_placeholder.format = first_real_format["format"]
            null_placeholder.elo = float(first_real_format["elo"])
            null_placeholder.gxe = float(first_real_format["gxe"])
            null_placeholder.wins = int(first_real_format["w"])
            null_placeholder.losses = int(first_real_format["l"])
            null_placeholder.timestamp = first_real_format["timestamp"]
            has_updates = True

        for _, row in df.iterrows():
            fmt = row["format"]
            new_elo = float(row["elo"])
            new_gxe = float(row["gxe"])
            new_wins = int(row["w"])
            new_losses = int(row["l"])

            latest_row = (
                db.session.query(PlayerRating)
                .filter_by(userid=userid, format=fmt)
                .order_by(PlayerRating.timestamp.desc())
                .first()
            )

            if not latest_row:
                db.session.add(
                    PlayerRating(
                        userid=userid,
                        username=row["username"],
                        format=fmt,
                        elo=new_elo,
                        gxe=new_gxe,
                        wins=new_wins,
                        losses=new_losses,
                        timestamp=row["timestamp"],
                    )
                )
                has_updates = True
                continue

            prev_wins = latest_row.wins or 0
            prev_losses = latest_row.losses or 0

            win_diff = max(0, new_wins - prev_wins)
            loss_diff = max(0, new_losses - prev_losses)

            if win_diff > 0 or loss_diff > 0:
                has_updates = True

                for _ in range(win_diff):
                    db.session.add(
                        MatchHistory(
                            userid=userid,
                            format=fmt,
                            indicator="W",
                            timestamp=row["timestamp"],
                        )
                    )

                for _ in range(loss_diff):
                    db.session.add(
                        MatchHistory(
                            userid=userid,
                            format=fmt,
                            indicator="L",
                            timestamp=row["timestamp"],
                        )
                    )

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
                        userid=userid,
                        username=row["username"],
                        format=fmt,
                        elo=new_elo,
                        gxe=new_gxe,
                        wins=accumulated_wins,
                        losses=accumulated_losses,
                        timestamp=row["timestamp"],
                    )
                )

        db.session.commit()
        return userid, has_updates

def grab_new():
    # fetches all distinct users and processes them concurrently
    with app.app_context():
        stmt = select(PlayerRating.userid).distinct()
        userids = db.session.execute(stmt).scalars().all()

    updated_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_single_user, userid): userid for userid in userids
        }

        for future in as_completed(futures):
            uid = futures[future]
            try:
                userid, updated = future.result()
                if updated:
                    updated_count += 1
            except Exception as e:
                print(f"thread failure for user [{uid}]: {e}")

    print(f"Finished checking users. Updated {updated_count}/{len(userids)} users.")


if __name__ == "__main__":
    grab_new()