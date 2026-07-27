from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from io import StringIO
import json
import re
import pandas as pd
import requests
from requests.exceptions import HTTPError


class ShowdownUserError(Exception):
    pass

class ShowdownUnavailableError(Exception):
    pass

def normalize_format(format_str: str) -> str:
    """Converts format strings like '[Gen 9] OU' or 'gen9ou' into 'gen9ou'."""
    return re.sub(r"[^a-z0-9]", "", str(format_str).lower())

def fetch_current_ratings(username: str) -> pd.DataFrame:
    user_link = f"https://pokemonshowdown.com/users/{username}.json"

    try:
        r = requests.get(user_link)
        r.raise_for_status()
    except HTTPError as e:
        status = e.response.status_code
        if status == 403:
            raise ShowdownUserError("invalid username")
        elif status == 404:
            raise ShowdownUserError("user not found")
        elif status == 503:
            raise ShowdownUnavailableError("server unavailable")
        else:
            raise
    except requests.exceptions.RequestException:
        raise ShowdownUnavailableError("network error")

    user_dict = json.loads(r.text)

    if not user_dict["ratings"]:
        df = pd.DataFrame(
            {
                "userid": [user_dict["userid"]],
                "username": [user_dict["username"]],
                "format": [None],
                "elo": [1000],
                "gxe": [0],
                "w": [0],
                "l": [0],
                "timestamp": [pd.Timestamp.now()],
            }
        )
        return df

    df_ratings = pd.DataFrame(user_dict["ratings"]).T
    df_ratings = df_ratings.reset_index().rename(columns={"index": "format"})

    df = pd.read_json(StringIO(r.text))
    df = df.reset_index().rename(columns={"index": "format"})

    df = pd.merge(df, df_ratings, how="inner", on="format")
    df.drop(
        ["ratings", "registertime", "group", "rpr", "rprd", "coil"],
        axis=1,
        inplace=True,
    )
    df = df[["userid", "username", "format", "elo", "gxe", "w", "l"]]
    df["timestamp"] = pd.Timestamp.now()

    return df

def _fetch_single_replay_team(item: dict, target_user_id: str):
    """Helper function to fetch and extract a team from a single replay log."""
    replay_id = item["id"]
    log_url = f"https://replay.pokemonshowdown.com/{replay_id}.log"

    try:
        res = requests.get(log_url, timeout=4)
        res.raise_for_status()
        log_text = res.text
    except requests.exceptions.RequestException:
        return replay_id, None

    player_slot = None
    team = []

    # map username to p1/p2
    for line in log_text.splitlines():
        if line.startswith("|player|"):
            parts = line.split("|")
            if (
                len(parts) >= 4
                and normalize_format(parts[3]) == target_user_id
            ):
                player_slot = parts[2]
                break

    # extract pokemon species registered under player_slot
    if player_slot:
        for line in log_text.splitlines():
            if line.startswith("|poke|"):
                parts = line.split("|")
                if len(parts) >= 4 and parts[2] == player_slot:
                    species = parts[3].split(",")[0]
                    team.append(species)

    return replay_id, team if team else None


# cache <= 128 recent search results in memory
@lru_cache(maxsize=128)
def replay_search(user: str, format_name: str, limit: int = 10):
    user_replays = f"https://replay.pokemonshowdown.com/search.json?user={user}"
    try:
        r = requests.get(user_replays, timeout=5)
        r.raise_for_status()
    except HTTPError as e:
        status = e.response.status_code
        if status == 403:
            raise ShowdownUserError("invalid username")
        elif status == 404:
            raise ShowdownUserError("user not found")
        elif status == 503:
            raise ShowdownUnavailableError("server unavailable")
        else:
            raise
    except requests.exceptions.RequestException:
        raise ShowdownUnavailableError("network error")

    replay_dict = json.loads(r.text)

    target_format = normalize_format(format_name)
    target_user_id = normalize_format(user)

    # filter matching formats & slice first to fetch the top n replays
    filtered_data = [
        item
        for item in replay_dict
        if normalize_format(item.get("format", "")) == target_format
    ][:limit]

    extracted_teams = {}

    # fetch log files concurrently using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(_fetch_single_replay_team, item, target_user_id)
            for item in filtered_data
        ]

        for future in as_completed(futures):
            replay_id, team = future.result()
            if team:
                extracted_teams[replay_id] = team

    return extracted_teams


def get_sprite_url(species: str) -> str:
    BASE_HYPHEN_SPECIES = {
    "tinglu",
    "chiyu",
    "chienpao",
    "wochien",
    "hooh",
    "porygonz",
    "jangmoo",
    "hakamoo",
    "kommoo",
}
    raw_clean = re.sub(r"[^a-z0-9]", "", species.lower())

    if raw_clean in BASE_HYPHEN_SPECIES:
        pokemon_id = raw_clean

    elif "-" in species:
        parts = species.split("-", 1)
        clean_base = re.sub(r"[^a-z0-9]", "", parts[0].lower())
        clean_form = re.sub(r"[^a-z0-9]", "", parts[1].lower())

        if clean_form:
            pokemon_id = f"{clean_base}-{clean_form}"
        else:
            pokemon_id = clean_base

    else:
        pokemon_id = raw_clean

    return f"https://play.pokemonshowdown.com/sprites/gen5/{pokemon_id}.png"