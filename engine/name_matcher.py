import re
import unicodedata
from difflib import SequenceMatcher

NAME_MATCH_THRESHOLD = 0.88


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize('NFKD', name)
    normalized = normalized.encode('ascii', 'ignore').decode('ascii')
    normalized = normalized.lower()
    normalized = normalized.replace('.', ' ')
    normalized = normalized.replace('-', ' ')
    normalized = re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', normalized)
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def name_similarity(left: str, right: str) -> float:
    left_key = normalize_name(left)
    right_key = normalize_name(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def build_name_lookup(names: list[str]) -> dict[str, str]:
    lookup = {}
    for name in names:
        lookup[normalize_name(name)] = name
    return lookup


def match_player_name(
    pp_name: str,
    dk_names: list[str],
    threshold: float = NAME_MATCH_THRESHOLD,
) -> tuple[str | None, float]:
    if not dk_names:
        return None, 0.0

    if pp_name in dk_names:
        return pp_name, 1.0

    best_name = None
    best_score = 0.0

    for dk_name in dk_names:
        score = name_similarity(pp_name, dk_name)
        if score > best_score:
            best_score = score
            best_name = dk_name

    if best_name and best_score >= threshold:
        return best_name, best_score

    return None, best_score
