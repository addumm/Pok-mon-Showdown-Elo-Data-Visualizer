import requests
from requests.exceptions import HTTPError
import json
import pandas as pd
from io import StringIO

class ShowdownUserError(Exception):
    pass

class ShowdownUnavailableError(Exception):
    pass


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

    if not user_dict["ratings"]:
        df = pd.read_json(StringIO(r.text))
        df["format"] = pd.NA
        df["elo"] = 1000
        df["gxe"] = 0
        df["w"] = 0
        df["l"] = 0
        df.drop(["ratings", "registertime", "group"], axis = 1, inplace = True)
        df = df[["userid", "username", "format", "elo", "gxe", "w", "l"]]
        df["timestamp"] = pd.Timestamp.now()
        return df


    df_ratings = pd.DataFrame(user_dict["ratings"]).T
    df_ratings = df_ratings.reset_index().rename(columns = {"index": "format"})

    df = pd.read_json(StringIO(r.text))
    df = df.reset_index().rename(columns = {"index": "format"})

    df = pd.merge(df, df_ratings, how = "inner", on = "format")
    df.drop(["ratings", "registertime", "group", "rpr", "rprd", "coil"], axis = 1, inplace = True)
    df = df[["userid", "username", "format", "elo", "gxe", "w", "l"]]
    df["timestamp"] = pd.Timestamp.now()

    return df
