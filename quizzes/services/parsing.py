import json
import re
from dataclasses import dataclass

from ..models import Quiz
from .errors import QuizFormatError

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass
class QuestionData:
    text: str
    choices: list
    correct_index: int
    explanation: str
    difficulty: str


def extract_json(raw):
    """Lit le JSON d'une réponse de LLM, même entourée de ``` ou de texte."""
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise QuizFormatError("Réponse du modèle illisible (JSON invalide).")


def _validate_one(item, default_difficulty):
    if not isinstance(item, dict):
        return None
    text = str(item.get("question", "")).strip()
    choices = item.get("choices")
    if not text or not isinstance(choices, list) or len(choices) != 4:
        return None
    choices = [str(choice).strip() for choice in choices]
    if any(not c for c in choices) or len({c.lower() for c in choices}) != 4:
        return None
    index = item.get("correct_index")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 3:
        return None
    explanation = str(item.get("explanation", "")).strip()
    if not explanation:
        return None
    difficulty = item.get("difficulty")
    if difficulty not in Quiz.Difficulty.values:
        difficulty = default_difficulty
    return QuestionData(text, choices, index, explanation, difficulty)


def validate_questions(payload, default_difficulty):
    """Retourne les questions valides ; les autres sont écartées."""
    items = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise QuizFormatError("Le JSON ne contient pas de liste de questions.")
    valid = (_validate_one(item, default_difficulty) for item in items)
    return [question for question in valid if question]