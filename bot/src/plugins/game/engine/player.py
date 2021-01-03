from game.model.card import Card

class Player:
  def __init__(self, card):
    self.name = card.player.name
    self.position = card.player.Position
    # 格式 ability["Short_Passing"] 具体请看Card
    self.ability = card.ability
