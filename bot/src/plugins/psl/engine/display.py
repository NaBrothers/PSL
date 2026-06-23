import random
from engine.player import Player
from engine.commentary import CommentaryRenderer


renderer = CommentaryRenderer(random)


class Display:
    def print_short_shot(player, distance):
        return renderer.event("short_shot", player=player.coach + " " + player.getName(), distance=distance)

    def print_long_shot(player, distance):
        return renderer.event("long_shot", player=player.coach + " " + player.getName(), distance=distance)

    def print_miss_shot():
        return renderer.event("miss")

    def print_goal(player, gk, assister):
        string = renderer.event("goal", player=player.coach + " " + player.getName(), keeper=gk.coach + " " + gk.getName())
        if assister:
          string = string.rstrip("。，.、")
          string += "，来自 " + assister.getName() + " 的助攻"
        return string

    def print_dribbling(offence, defence):
        return renderer.event("dribble", player=offence.coach + " " + offence.getName(), target=defence.coach + " " + defence.getName())

    def print_controlling(player, direction):
        return renderer.event("carry", player=player.coach + " " + player.getName(), direction=direction)

    def print_tackling(offence, defence):
        return renderer.event("tackle", player=defence.coach + " " + defence.getName(), target=offence.coach + " " + offence.getName())

    def print_saving(gk):
        return renderer.event("save", keeper=gk.coach + " " + gk.getName())

    def print_interception(player):
        return renderer.event("interception", player=player.coach + " " + player.getName())

    def print_high_shot(player):
        return renderer.event("high_shot", player=player.coach + " " + player.getName())

    def print_short_pass(player1, player2, distance):
        return renderer.event("short_pass", player=player1.coach + " " + player1.getName(), target=player2.getName(), distance=distance)

    def print_long_pass(player1, player2, distance):
        return renderer.event("long_pass", player=player1.coach + " " + player1.getName(), target=player2.getName(), distance=distance)
