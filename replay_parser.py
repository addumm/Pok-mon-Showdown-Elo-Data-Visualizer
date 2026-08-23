import re
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_stats_concurrently(replay_ids: list[str], target_username: str, max_workers: int = 5) -> dict:
    """
    fetches and parses replay stats for multiple replay ids in parallel.
    returns a dictionary mapping replay_id -> parsed_stats.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # submit a task for each replay id
        future_to_id = {
            executor.submit(fetch_and_parse_replay_stats, rid, target_username): rid
            for rid in replay_ids
        }
        
        for future in as_completed(future_to_id):
            rid = future_to_id[future]
            try:
                stats = future.result()
                if stats:
                    results[rid] = stats
            except Exception as e:
                print(f"[STATS FETCH ERROR] Replay {rid}: {e}")
                results[rid] = None

    return results

def fetch_and_parse_replay_stats(replay_id: str, target_username: str):
    log_url = f"https://replay.pokemonshowdown.com/{replay_id}.log"
    res = requests.get(log_url, timeout=5)
    if res.status_code != 200:
        return None
    
    lines = res.text.splitlines()
    clean_target = re.sub(r"[^a-z0-9]", "", target_username.lower())
    
    # identify player slot (p1 or p2)
    user_slot = None
    for line in lines:
        if line.startswith("|player|"):
            parts = line.split("|")
            if len(parts) >= 4 and re.sub(r"[^a-z0-9]", "", parts[3].lower()) == clean_target:
                user_slot = parts[2]  # 'p1' or 'p2'
                break
                
    if not user_slot:
        return None  # user wasn't in this battle

    # initialize stats tracking structures
    team_preview = []
    brought_pokemon = set()
    turns_active = defaultdict(int)
    move_usage = defaultdict(lambda: defaultdict(int))
    fainted_pokemon = set()
    
    current_active_mon = None
    current_turn = 0

    for line in lines:
        parts = line.split("|")
        if len(parts) < 2:
            continue
            
        cmd = parts[1]

        # find turn count
        if cmd == "turn":
            current_turn = int(parts[2])
            if current_active_mon:
                turns_active[current_active_mon] += 1

        # find team preview (all 6 mons registered)
        elif cmd == "poke" and parts[2] == user_slot:
            species = parts[3].split(",")[0].strip()
            team_preview.append(species)

        # find switches (who actually entered the battle)
        elif cmd in ["switch", "drag"] and parts[2].startswith(user_slot):
            raw_mon = parts[2].split(":")[1].strip() if ":" in parts[2] else parts[2]
            species = parts[3].split(",")[0].strip()
            
            current_active_mon = species
            brought_pokemon.add(species)

        # find move usage
        elif cmd == "move" and parts[2].startswith(user_slot):
            species = parts[2].split(":")[1].strip() if ":" in parts[2] else "Unknown"
            move_name = parts[3]
            move_usage[species][move_name] += 1

        # find faints
        elif cmd == "faint" and parts[2].startswith(user_slot):
            fainted_mon = parts[2].split(":")[1].strip() if ":" in parts[2] else parts[2]
            fainted_pokemon.add(fainted_mon)

    return {
        "replay_id": replay_id,
        "target_user": target_username,
        "slot": user_slot,
        "total_turns": current_turn,
        "team_preview": team_preview,
        "brought_pokemon": list(brought_pokemon),
        "fainted_pokemon": list(fainted_pokemon),
        "turns_active": dict(turns_active),
        "move_usage": {k: dict(v) for k, v in move_usage.items()}
    }

def build_llm_game_summary_payload(replay_id: str, target_username: str) -> dict:
    stats = fetch_and_parse_replay_stats(replay_id, target_username)
    if not stats:
        return None
    
    return {
        "replay_id": stats["replay_id"],
        "user": target_username,
        "turns": stats["total_turns"],
        "team_brought": stats["brought_pokemon"],
        "faints": stats["fainted_pokemon"],
        "move_usage": stats["move_usage"],
        "timeline": stats.get("key_events", [])
    }