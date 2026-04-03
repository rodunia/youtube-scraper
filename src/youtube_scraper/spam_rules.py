from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PROMO_RE = re.compile(r"(?i)(dm\s+me|check\s+my\s+channel|subscribe\s+back|promo\s+code)")
CONTACT_RE = re.compile(r"(?i)(whatsapp|telegram|kik|snapchat)\b")
SOLICIT_RE = re.compile(r"(?i)(contact\s+me|message\s+me|join\s+now|earn\s+money)")
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
CHAR_FLOOD_RE = re.compile(r"(.)\1{11,}")


@dataclass
class SpamRuleResult:
    is_spam: bool
    hits: list[str]


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def evaluate_spam_rules(normalized_text: str, cross_video_occurrences: int, blacklist: set[str]) -> SpamRuleResult:
    hits: list[str] = []

    if len(URL_RE.findall(normalized_text)) >= 2:
        hits.append("S1")
    if PROMO_RE.search(normalized_text):
        hits.append("S2")
    if CONTACT_RE.search(normalized_text) and SOLICIT_RE.search(normalized_text):
        hits.append("S3")

    tokens = TOKEN_RE.findall(normalized_text)
    if tokens:
        token_counts = Counter(tokens)
        if token_counts and token_counts.most_common(1)[0][1] >= 8:
            hits.append("S4")

    if CHAR_FLOOD_RE.search(normalized_text):
        hits.append("S5")

    if cross_video_occurrences >= 5:
        hits.append("S6")

    if normalized_text in blacklist:
        hits.append("S7")

    if len(normalized_text) > 15:
        non_alnum = sum(1 for ch in normalized_text if not ch.isalnum() and not ch.isspace())
        if (non_alnum / len(normalized_text)) > 0.60:
            hits.append("S8")

    return SpamRuleResult(is_spam=bool(hits), hits=hits)
