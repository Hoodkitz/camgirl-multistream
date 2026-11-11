"""Auto-Begruessung und Spendenziele (reine Logik, ohne I/O)."""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_PLACEHOLDER = re.compile(r"\{(username|platform|amount)\}")
MAX_TEMPLATE_LEN = 500


def render_template(template: str, **values: str) -> str:
    """Nur erlaubte Platzhalter; alles andere bleibt woertlich (kein str.format -> keine Injection)."""
    return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), "")), template)[:MAX_TEMPLATE_LEN]


def should_greet(last_greeted: datetime | None, now: datetime, cooldown_hours: int) -> bool:
    return last_greeted is None or now - last_greeted >= timedelta(hours=cooldown_hours)


@dataclass
class GoalProgress:
    reached: bool
    total: int
    newly_reached: bool


def goal_progress(previous_total: int, added: int, target: int) -> GoalProgress:
    total = previous_total + added
    return GoalProgress(total >= target, total, previous_total < target <= total)
