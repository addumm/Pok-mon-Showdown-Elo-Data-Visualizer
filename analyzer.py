import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_ID = "gemini-3.5-flash"

def get_genai_client():
  api_key = os.getenv("GEMINI_API_KEY")
  if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is missing.")
  return genai.Client(api_key=api_key)

class SingleGameAnalysis(BaseModel):
    matchup: str = Field(
        description = "What are the team archetypes? Which of the users pokemon appear to be good in the matchup? what are the opponents threats to the user's team?"
    )
    win_condition: str = Field(
        description="What are the core win-conditions or core strategies available to the player? How did the user do executing these?"
    )
    luck: str = Field(
        description="How was the user's luck in the game?"
    )
    turning_point_turn: int = Field(
        description="The exact turn number where game momentum decisively shifted."
    )
    turning_point_reason: str = Field(
        description="Detailed explanation of why this turn was the pivotal moment."
    )
    critical_mistakes: list[str] = Field(
        description="Note any blunders/suboptimal plays/mispredictions made by the user. Ensure to weigh risk vs reward, consider sacrifices to get in another pokemon vs blindly losing a pokemon, etc."
    )
    mvp_pokemon: str = Field(
        description="The Pokémon on the user's team that contributed most to the match outcome."
    )

class MultiGameAnalysis(BaseModel):
    summary_overview: str = Field(
        description="How did the player perform across the analyzed matches?"
    )
    overperforming_pokemon: list[str] = Field(
        description="Which pokémon consistently generated high value, sweeps, wallbreaking power, or defensive utility?"
    )
    underperforming_pokemon: list[str] = Field(
        description="What pokémon consistently fainted early, exerted zero pressure, or were seemingly dead weight."
    )
    playstyle_habits: list[str] = Field(
        description="What are the user's behavioral trends across games (e.g., switching under specific scenarios, Tera usage, setup blunders, etc.)."
    )
    luck: list[str] = Field(
        description="How was the user's luck across these games?"
    )
    strategic_adjustments: list[str] = Field(
        description="What are 2-3 actionable adjustments to raise overall win rate."
    )

def analyze_single_game(game_payload: dict) -> SingleGameAnalysis:
    """
    Analyzes a single parsed Showdown match JSON payload using Gemini 3.6 Flash.
    Returns a validated SingleGameAnalysis object.
    """
    prompt = f"""
    You are an elite competitive Pokémon Showdown analyst evaluating a match for player '{game_payload.get('user')}'.
    Analyze the parsed log state and return insights strictly based on the provided data. 
    If any blunders were made, explain why and suggest alternative move suggestions as well.
    
    Match Data:
    {json.dumps(game_payload, indent=2)}
    """

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=SingleGameAnalysis,
            system_instruction=(
                "You are a strict data-driven Pokémon competitive analyst. "
                "Base your evaluation strictly on the JSON payload. Do not invent turns or mechanics."
            )
        ),
    )
    
    # parse the validated json string directly into pydantic model
    return SingleGameAnalysis.model_validate_json(response.text)

def analyze_multi_games(username: str, game_payloads: list[dict]) -> MultiGameAnalysis:
    prompt = f"""
    You are a high-level Pokémon Showdown head coach evaluating {len(game_payloads)} recent matches for '{username}'.
    Review the team usage, move distribution, and faints across games to identify {username}'s habits and team flaws.

    Aggregated Game Data:
    {json.dumps(game_payloads, indent=2)}
    """

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            response_mime_type="application/json",
            response_schema=MultiGameAnalysis,
            system_instruction=(
                "You are an analytical Pokémon coach focusing on win-rate trends, risk management, "
                "and team building optimizations across multiple games."
            )
        ),
    )

    return MultiGameAnalysis.model_validate_json(response.text)