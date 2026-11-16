"""Validate a PageSnapshot JSON file (e.g. downloaded with the extension's "Debug: snapshot" button)
against shared/page_snapshot.schema.json AND the Pydantic model, and check the privacy rules.

    python -m scripts.validate_snapshot darklens-snapshot.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

from backend.models import PageSnapshot

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "shared" / "page_snapshot.schema.json").read_text(encoding="utf-8"))


def validate(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = [f"schema: {e.message} at {list(e.path)}" for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(data)]
    try:
        PageSnapshot.model_validate(data)
    except Exception as exc:
        problems.append(f"pydantic: {exc}")
    for s in data.get("segments", []):
        if len(s.get("text", "")) > 300:
            problems.append(f"segment {s['id']} longer than 300 chars")
    return problems


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    problems = validate(path)
    if problems:
        print(f"INVALID ({len(problems)} problem(s)):")
        for p in problems[:30]:
            print("  -", p)
        raise SystemExit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"VALID PageSnapshot from the {data['collector']} collector: {len(data['segments'])} segments, "
          f"{len(data['buttons'])} buttons, {len(data['prices'])} prices, {len(data['popups'])} popups.")


if __name__ == "__main__":
    main()
