"""Decide from a match's own first page whether scrolling through it is worth the time.

A page that has no tracking, timestamps, win probability or events, and whose commentary text
never names a line, length, shot or direction, has nothing the dataset can use. Such a match
stays in the dataset with empty Cricinfo columns, and is not scrolled. The call is made from that
match's own page, never from a guess about its competition or year.
"""
import re

# Words a commentator uses to name where the ball pitched, how it was played or where it went
_LINE = r"off stump|middle stump|leg stump|outside off|outside the off|down the leg|down leg|wide of off|on the stumps|off and middle|leg and middle"
_LENGTH = r"fullish|fuller|pitched up|yorker|full toss|full length|good length|short of a length|back of a length|short ball|short delivery|bouncer|half volley|half-volley|full ball|full delivery|length ball"
# Verbs found by comparing words in balls Cricinfo tracked against those it did not (drives, punches, taps, jabs and so on)
_SHOT = (r"drive|drives|driven|cut|cuts|pull|pulls|pulled|hook|hooks|hooked|sweep|sweeps|swept|glance|glances|glanced|flick|flicks|flicked|slog|slogs|slogged|"
         r"scoop|scoops|ramp|steer|steers|steered|punch|punches|punched|paddle|paddles|nudge|nudges|nudged|defend|defends|defended|block|blocks|blocked|"
         r"edge|edges|edged|lofted|lofts|clip|clips|clipped|dab|dabs|dabbed|smash|smashes|smashed|swat|swats|swatted|tap|taps|tapped|jab|jabs|jabbed|"
         r"drill|drills|drilled|slap|slaps|slapped|eases|eased|pushed|pushes|chips|chipped|front foot|back foot")
_DIRECTION = (r"cover|point|third man|fine leg|square leg|mid.?wicket|mid.?on|mid.?off|long.?on|long.?off|long leg|deep|slip|gully|"
              r"straight|down the ground|over the top|backward|short leg|silly|sweeper|fine|behind square")
NAMES_A_DELIVERY = re.compile(rf"\b({_LINE}|{_LENGTH}|{_SHOT}|{_DIRECTION})\b", re.IGNORECASE)


def text_names_a_delivery(text: str | None) -> bool:
    """True when commentary text names a line, length, shot or direction. 'Good ball, no run' does not."""
    return bool(text and NAMES_A_DELIVERY.search(text))


def is_useful(comments: list[dict]) -> bool:
    """comments: one dict per ball with 'structured' (any tracking, timestamp, win probability or event) and 'text'."""
    return any(c.get("structured") or text_names_a_delivery(c.get("text")) for c in comments)


def from_ball(ball: dict) -> dict:
    """A captured ball record in the form is_useful reads."""
    structured = bool(ball.get("line") or ball.get("length") or ball.get("shot") or ball.get("control") or ball.get("wz")
                      or ball.get("timestamp") or ball.get("win_probability") is not None or ball.get("events"))
    return {"structured": structured, "text": " ".join(filter(None, [ball.get("text"), ball.get("pre_text")]))}
