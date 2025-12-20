import requests
from requests.exceptions import HTTPError
import json
import pandas as pd
from io import StringIO

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
