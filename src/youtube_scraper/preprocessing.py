from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from difflib import SequenceMatcher

from .spam_rules import evaluate_spam_rules, normalize_text


@dataclass
class ProcessedComment:
    commenter_hash_id: str
    raw_text: str
    cleaned_text: str
    is_spam: bool
    is_template: bool
    is_duplicate: bool
    spam_rule_hits: list[str]


def pseudonymize_commenter_id(raw_commenter_id: str, secret_salt: str) -> str:
    digest = hmac.new(
        secret_salt.encode("utf-8"), raw_commenter_id.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return digest


def clean_text(raw_text: str) -> str:
    text = raw_text.replace("\n", " ").replace("\r", " ")
    return " ".join(text.split())


def is_template_text(text_a: str, text_b: str, threshold: float) -> bool:
    score = SequenceMatcher(a=text_a, b=text_b).ratio()
    return score >= threshold


def process_comment(
    *,
    raw_commenter_id: str,
    raw_text: str,
    secret_salt: str,
    previous_video_normalized: set[str],
    global_normalized_counts: dict[str, int],
    global_normalized_samples: list[str],
    template_threshold: float,
    spam_blacklist: set[str],
) -> ProcessedComment:
    cleaned = clean_text(raw_text)
    normalized = normalize_text(cleaned)

    duplicate = normalized in previous_video_normalized
    cross_count = global_normalized_counts.get(normalized, 0)

    template = False
    for sample in global_normalized_samples[-250:]:
        if is_template_text(normalized, sample, template_threshold):
            template = True
            break

    spam = evaluate_spam_rules(normalized, cross_count, spam_blacklist)

    return ProcessedComment(
        commenter_hash_id=pseudonymize_commenter_id(raw_commenter_id, secret_salt),
        raw_text=raw_text,
        cleaned_text=cleaned,
        is_spam=spam.is_spam,
        is_template=template,
        is_duplicate=duplicate,
        spam_rule_hits=spam.hits,
    )
