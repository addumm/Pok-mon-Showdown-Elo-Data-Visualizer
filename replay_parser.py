import re
import requests
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

def clean_pokemon_name(raw_slot_string: str) -> str:
    """
    Cleans raw Showdown slot identifiers into readable Pokémon species names.
    Examples:
      'p1a: Dragapult' -> 'Dragapult'
      'p2: Great Tusk'  -> 'Great Tusk'
      'p1a: Kingambit' -> 'Kingambit'
    """
    if ":" in raw_slot_string:
        return raw_slot_string.split(":")[1].strip()
    return raw_slot_string.strip()

def fetch_stats_concurrently(replay_ids: list[str], target_username: str, max_workers: int = 5) -> dict:
    """
    fetches and parses replay stats for multiple replay ids in parallel.
    returns a dictionary mapping replay_id -> parsed_stats.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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

STATUS_MAP = {
    "brn": "Burned",
    "par": "Paralyzed",
    "frz": "Frozen",
    "psn": "Poisoned",
    "tox": "Badly Poisoned",
    "slp": "Asleep"
}

def fetch_and_parse_replay_stats(replay_id: str, target_username: str):
    # Strip any trailing query parameters or p1/p2 flags (e.g. ?p2)
    clean_id = replay_id.split("?")[0].strip()
    
    # All Showdown replays (including Smogtours) serve logs via replay.pokemonshowdown.com
    log_url = f"https://replay.pokemonshowdown.com/{clean_id}.log"

    res = requests.get(log_url, timeout=5)
    if res.status_code != 200:
        return None
    
    lines = res.text.splitlines()
    clean_target = re.sub(r"[^a-z0-9]", "", target_username.lower())
    
    # identify player slot (p1 or p2) and track opponent username
    user_slot = None
    opp_slot = None
    opp_username = "Opponent"

    for line in lines:
        if line.startswith("|player|"):
            parts = line.split("|")
            if len(parts) >= 4:
                slot = parts[2]
                name = parts[3]
                if re.sub(r"[^a-z0-9]", "", name.lower()) == clean_target:
                    user_slot = slot
                else:
                    opp_slot = slot
                    opp_username = name

    if not user_slot:
        return None

    # tracking structures
    team_preview = []
    brought_pokemon = set()
    turns_active = defaultdict(int)
    move_usage = defaultdict(lambda: defaultdict(int))
    fainted_pokemon = set()
    timeline = []  # high-impact turn-by-turn events
    
    current_active_mon = None
    current_turn = 0

    # key setup/utility moves to highlight in the timeline
    IMPACT_MOVES = {
        "stealth rock", "spikes", "toxic spikes", "sticky web", "rapid spin", "mortal spin", "defog",
        "swords dance", "dragon dance", "nasty plot", "calm mind", "quiver dance", "iron defense",
        "reflect", "light screen", "aurora veil", "tail-wind", "trick room", "substitute", "recover", "roost", 
        "slack off", "soft-boiled", "moonlight", "encore", "knock off", "toxic", "thunder wave", "will-o-wisp", 
        "trick", "u-turn", "volt switch", "wish", "ceaseless edge", "chilly reception", "flip turn"
    }

    for line in lines:
        parts = line.split("|")
        if len(parts) < 2:
            continue
            
        cmd = parts[1]

        # track turn numbers
        if cmd == "turn":
            current_turn = int(parts[2])
            if current_active_mon:
                turns_active[current_active_mon] += 1

        # track team preview
        elif cmd == "poke" and parts[2] == user_slot:
            species = parts[3].split(",")[0].strip()
            team_preview.append(species)

        # track switches & timeline
        elif cmd in ["switch", "drag"]:
            slot = parts[2].split(":")[0]
            raw_mon = parts[2].split(":")[1].strip() if ":" in parts[2] else parts[2]
            species = parts[3].split(",")[0].strip()

            if slot.startswith(user_slot):
                current_active_mon = species
                brought_pokemon.add(species)
                timeline.append({
                    "turn": current_turn,
                    "event": f"You switched in {species}"
                })
            elif opp_slot and slot.startswith(opp_slot):
                timeline.append({
                    "turn": current_turn,
                    "event": f"{opp_username} switched in {species}"
                })

        # track moves, move counts, and high-impact setup/hazard events
        elif cmd == "move":
            slot = parts[2].split(":")[0]
            species = parts[2].split(":")[1].strip() if ":" in parts[2] else "Unknown"
            move_name = parts[3]

            if slot.startswith(user_slot):
                move_usage[species][move_name] += 1
                if move_name.lower() in IMPACT_MOVES:
                    timeline.append({
                        "turn": current_turn,
                        "event": f"You used key move: {move_name} ({species})"
                    })
            elif opp_slot and slot.startswith(opp_slot):
                if move_name.lower() in IMPACT_MOVES:
                    timeline.append({
                        "turn": current_turn,
                        "event": f"{opp_username} used key move: {move_name} ({species})"
                    })

        # track faints in timeline
        elif cmd == "faint":
            slot = parts[2].split(":")[0]
            fainted_mon = parts[2].split(":")[1].strip() if ":" in parts[2] else parts[2]

            if slot.startswith(user_slot):
                fainted_pokemon.add(fainted_mon)
                timeline.append({
                    "turn": current_turn,
                    "event": f"Your {fainted_mon} fainted"
                })
            elif opp_slot and slot.startswith(opp_slot):
                timeline.append({
                    "turn": current_turn,
                    "event": f"Opponent's {fainted_mon} fainted"
                })

        # track terastallization in timeline
        elif cmd == "-terastallize":
            slot = parts[2].split(":")[0]
            species = parts[2].split(":")[1].strip() if ":" in parts[2] else parts[2]
            tera_type = parts[3]

            if slot.startswith(user_slot):
                timeline.append({
                    "turn": current_turn,
                    "event": f"You Terastallized {species} into {tera_type}-type"
                })
            elif opp_slot and slot.startswith(opp_slot):
                timeline.append({
                    "turn": current_turn,
                    "event": f"{opp_username} Terastallized {species} into {tera_type}-type"
                })

        elif cmd == "-status":
            if len(parts) >= 4:
                raw_poke = parts[2]
                status_code = parts[3]
                poke_name = clean_pokemon_name(raw_poke)
                status_name = STATUS_MAP.get(status_code, status_code.upper())
                cause = ""
                if len(parts) >= 5 and "[from]" in parts[4]:
                    cause = f" via {parts[4].replace('[from]', '').strip()}"

                timeline.append(
                    f"Turn {current_turn}: {poke_name} was {status_name}{cause}."
                )

        # track status cures
        elif cmd == "-curestatus":
            if len(parts) >= 4:
                raw_poke = parts[2]
                status_code = parts[3]
                poke_name = clean_pokemon_name(raw_poke)
                status_name = STATUS_MAP.get(status_code, status_code.upper())

                timeline.append(
                    f"Turn {current_turn}: {poke_name} cured its {status_name}."
                )

    return {
        "replay_id": clean_id,
        "target_user": target_username,
        "slot": user_slot,
        "total_turns": current_turn,
        "team_preview": team_preview,
        "brought_pokemon": list(brought_pokemon),
        "fainted_pokemon": list(fainted_pokemon),
        "turns_active": dict(turns_active),
        "move_usage": {k: dict(v) for k, v in move_usage.items()},
        "timeline": timeline
    }

def parse_replay_ids(text_input: str, max_replays: int = 3) -> list[str]:
    if not text_input:
        return []
    pattern = r'(?:(?:replay|smogtours)\.pokemonshowdown\.com/)?((?:smogtours-)?[a-zA-Z0-9]+-\d+)'
    matches = re.findall(pattern, text_input)

    seen = set()
    deduped = [m for m in matches if not (m in seen or seen.add(m))]
    
    return deduped[:max_replays]