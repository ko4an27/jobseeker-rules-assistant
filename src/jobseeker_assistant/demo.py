"""Offline demo: 5 sample questions through the graph with the fake LLM.

    make demo

The fake LLM repeats the first sentence of its top source, so answers are short and
literal; the point is to show the flow: which questions are answered, which are refused,
why, and which path each one took.
"""

from __future__ import annotations

import sys

from . import snapshots
from .glossary import load_glossary
from .graph import run_graph
from .llm import FakeLLM
from .retrieve import Index
from .source_tags import load_tags

QUESTIONS = [
    "How long can a work try-out last?",
    "i got a small side gig, do i lose all my kela money??",
    "Can I still apply for labour market subsidy?",
    "What is the best pizza in Helsinki?",  # off-topic
    "Kela rejected my application. Will I win if I appeal?",  # personal legal advice
]


def main() -> int:
    snaps = snapshots.load_all()
    if not snaps:
        print("No source snapshots found in sources/. Run `make ingest` first.")
        return 1
    index = Index.from_snapshots(snaps, load_tags())
    glossary = load_glossary()
    for i, question in enumerate(QUESTIONS, 1):
        answer, path = run_graph(question, index, FakeLLM(), glossary)
        print(f"\n=== {i}. {question}")
        print("path:   " + " → ".join(path))
        if answer.refused:
            print(f"result: REFUSED ({answer.refusal_reason})")
        if answer.glossary_used:
            print("glossary: " + ", ".join(answer.glossary_used))
        print(answer.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
