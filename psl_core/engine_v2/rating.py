"""Player match ratings calculation (Phase 2)."""

from __future__ import annotations

from typing import Dict, List

from .player import Player


def compute_player_rating(player: Player, team_goals: int, team_conceded: int) -> float:
    """Compute a match rating for a player (1.0 - 10.0 scale).

    Based on contributions during the match.
    Phase 2 additions: carries, crosses, headers.
    """
    base = 6.0

    # Goals contribution
    base += player.goals * 1.0

    # Assists contribution
    base += player.assists * 0.5

    # Shots on target bonus
    if player.shots > 0:
        base += min(0.5, player.shots_on_target * 0.15)

    # Pass completion
    if player.passes_attempted > 5:
        pass_rate = player.passes_completed / player.passes_attempted
        base += (pass_rate - 0.7) * 1.5  # bonus/penalty around 70% benchmark

    # Tackles
    if player.tackles_attempted > 0:
        tackle_rate = player.tackles_won / player.tackles_attempted
        base += tackle_rate * 0.3

    # Interceptions
    base += player.interceptions * 0.1

    # Goalkeeper saves
    if player.is_goalkeeper:
        base += player.saves * 0.3
        base -= team_conceded * 0.2

    # Dribbles
    if player.dribbles_attempted > 0:
        dribble_rate = player.dribbles_completed / player.dribbles_attempted
        base += dribble_rate * 0.2

    # Phase 2: Carries
    if player.carries_attempted > 0:
        carry_rate = player.carries_completed / player.carries_attempted
        base += carry_rate * 0.15

    # Phase 2: Crosses
    if player.crosses_attempted > 0:
        cross_rate = player.crosses_completed / player.crosses_attempted
        base += cross_rate * 0.2

    # Phase 2: Headers
    if player.headers_won > 0:
        base += min(0.3, player.headers_won * 0.1)

    # Clamp between 1.0 and 10.0
    return max(1.0, min(10.0, round(base, 1)))


def compute_team_ratings(
    players: List[Player], team_goals: int, team_conceded: int
) -> List[Dict]:
    """Compute ratings for all players in a team."""
    ratings = []
    for p in players:
        rating = compute_player_rating(p, team_goals, team_conceded)
        ratings.append({
            "name": p.name,
            "position": p.position,
            "rating": rating,
        })
    return ratings
