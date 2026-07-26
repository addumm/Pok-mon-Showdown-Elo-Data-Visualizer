import requests
from requests.exceptions import HTTPError
import json
import pandas as pd
from io import StringIO
import re

class ShowdownUserError(Exception):
    pass

class ShowdownUnavailableError(Exception):
    pass

### string handled and formatted in app.py ###
def fetch_current_ratings(username: str) -> pd.DataFrame:
    user_link = "https://pokemonshowdown.com/users/" + username + ".json"

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

    #### HANDLE USERS WITH NO GAMES / RATINGS / NEW ACCOUNTS ####
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
                "timestamp": [pd.Timestamp.now()]
            }
        )
        return df

    #### HANDLE ALL OTHER USERS ####
    df_ratings = pd.DataFrame(user_dict["ratings"]).T
    df_ratings = df_ratings.reset_index().rename(columns = {"index": "format"})

    df = pd.read_json(StringIO(r.text))
    df = df.reset_index().rename(columns = {"index": "format"})

    df = pd.merge(df, df_ratings, how = "inner", on = "format")
    df.drop(["ratings", "registertime", "group", "rpr", "rprd", "coil"], axis = 1, inplace = True)
    df = df[["userid", "username", "format", "elo", "gxe", "w", "l"]]
    df["timestamp"] = pd.Timestamp.now()

    return df

def replay_search(user:str, format: str):
    user_replays = "https://replay.pokemonshowdown.com/search.json?user=" + user
    try:
        r = requests.get(user_replays)
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

    ### unravel the json ###
    replay_dict = json.loads(r.text)
    target_format = normalize_format(format)

    extracted_teams = {}

    for item in replay_dict:
        if normalize_format(item.get("format", "")) != target_format:
            continue

        replay_id = item["id"]

        exact_username = None
        for player_name in item.get("players", []):
            if player_name.lower() == user.lower():
                exact_username = player_name
                break

        if not exact_username:
            continue

        log_url = "https://replay.pokemonshowdown.com/" + replay_id + ".log"
        try:
            res = requests.get(log_url)
            res.raise_for_status()
            log_text = res.text
        except requests.exceptions.RequestException:
            continue

        player_slot = None
        team = []

        for line in log_text.splitlines():
            if line.startswith("|player|"):
                parts = line.split("|")
                if len(parts) >= 4 and parts[3] == exact_username:
                    player_slot = parts[2]
                    break

        if player_slot:
            for line in log_text.splitlines():
                if line.startswith("|poke|"):
                    parts = line.split("|")
                    if len(parts) >= 4 and parts[2] == player_slot:
                        species = parts[3].split(",")[0]
                        team.append(species)
        if team:
            extracted_teams[replay_id] = team

    return extracted_teams

def get_sprite_url(species: str) -> str:
    pokemon_id = re.sub(r"[^a-z0-9]", "", species.lower())
    return f"https://play.pokemonshowdown.com/sprites/gen5/{pokemon_id}.png"

def normalize_format(format_str: str) -> str:
    return re.sub(r"[^a-z0-9]", "", format_str.lower())