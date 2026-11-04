"""Explicit refusal rule for personal legal advice (CLAUDE.md rule 4).

The assistant can explain what the official pages say, including how a process works
("How do I appeal a Kela decision?"). It must not judge a person's own case: predict an
outcome, say whether to sue, or decide whether something done to them was legal. These
questions are refused before retrieval, whatever the sources contain.
"""

from __future__ import annotations

import re

LEGAL_ADVICE_REFUSAL = (
    "I can't give personal legal advice or judge how your case will turn out. "
    "For your own situation, ask Kela or your employment services, or get advice from a "
    "lawyer or a public legal aid office."
)

# (rule name, pattern). Patterns describe the KIND of question, not specific test sentences.
RULES: list[tuple[str, re.Pattern]] = [
    # "Should I sue / appeal / go to court / hire a lawyer?"
    (
        "should_i_take_legal_action",
        re.compile(
            r"\bshould (?:i|we) (?:sue|appeal|complain|go to court|take \w+(?: \w+){0,3}"
            r" to court|hire a lawyer|get a lawyer)\b"
        ),
    ),
    # Suing / taking someone to court, in any form.
    (
        "lawsuit",
        re.compile(r"\b(?:sue|suing|lawsuit|take \w+(?: \w+){0,3} to court|court case)\b"),
    ),
    # Predicting the outcome: "will I win", "my chances", "will my appeal succeed".
    (
        "predict_outcome",
        re.compile(
            r"\bwill (?:i|we) win\b"
            r"|\b(?:my|our) chances?\b"
            r"|\bchances? (?:of|if|that)\b.*\b(?:appeal|court|case|win|succeed)"
            r"|\bwill (?:my|the|our) (?:appeal|case|complaint) (?:succeed|work|win)\b"
        ),
    ),
    # Asking us to rule on something in their own situation: "is my eviction notice legal?"
    (
        "is_my_situation_legal",
        re.compile(
            r"\b(?:is|was|are|were) (?:my|our|this|their|his|her)\b[\w’' -]{0,60}?"
            r"\b(?:legal|illegal|lawful|unlawful|valid)\b"
        ),
    ),
    (
        "asks_for_legal_advice",
        re.compile(r"\blegal advice\b|\bdo i need a lawyer\b"),
    ),
]


def detect(question: str) -> str | None:
    """Name of the first rule that matches, or None."""
    q = " ".join(question.lower().split())
    for name, pattern in RULES:
        if pattern.search(q):
            return name
    return None
