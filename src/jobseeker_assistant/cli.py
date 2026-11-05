"""Ask one question from the command line:  python -m jobseeker_assistant.cli "question"."""

from __future__ import annotations

import sys

from . import snapshots
from .answer import answer_question
from .dotenv import load_dotenv
from .glossary import load_glossary
from .llm import get_llm
from .retrieve import Index
from .source_tags import load_tags


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    argv = sys.argv[1:] if argv is None else argv
    question = " ".join(argv).strip()
    if not question:
        print('usage: python -m jobseeker_assistant.cli "your question"')
        return 2
    snaps = snapshots.load_all()
    if not snaps:
        print("No source snapshots found in sources/. Run `make ingest` first.")
        return 1
    result = answer_question(
        question, Index.from_snapshots(snaps, load_tags()), get_llm(), glossary=load_glossary()
    )
    print(result.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
