import json
import os
import random
from string import Formatter


TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "commentary.json")


class SafeDict(dict):
  def __missing__(self, key):
    return "{" + key + "}"


class CommentaryRenderer:
  def __init__(self, rng=None, template_path=TEMPLATE_PATH):
    self.rng = rng or random
    with open(template_path, "r", encoding="utf-8") as f:
      self.templates = json.load(f)

  def render(self, section, key, **context):
    templates = self.templates.get(section, {}).get(key)
    if not templates:
      templates = self.templates.get(section, {}).get("default")
    if not templates:
      return ""
    template = self.rng.choice(templates)
    return template.format_map(SafeDict(context))

  def route(self, key, **context):
    return self.render("routes", key, **context)

  def possession(self, key, **context):
    return self.render("possession", key, **context)

  def report(self, key, **context):
    return self.render("report", key, **context)

  def event(self, key, **context):
    return self.render("events", key, **context)


def event_player_name(event, fallback="进攻球员"):
  if event.player is None:
    return fallback
  return event.player.getName(False)


def event_target_name(event, fallback="门将"):
  if event.target is None:
    return fallback
  return event.target.getName(False)


def xg_text(value):
  if not value:
    return ""
  return "，xG " + format(value, ".2f")
