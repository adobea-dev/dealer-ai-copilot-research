"""Patch the evaluator so C6_DEV_01 ranking is treated as a ranking component."""

from pathlib import Path

PATH = Path("src/evaluation/evaluator.py")


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    if '"descending_lead_volume",' not in text:
        text = text.replace(
            '    "descending_ranking",\n    "ascending_ranking",\n',
            '    "descending_ranking",\n'
            '    "ascending_ranking",\n'
            '    "descending_lead_volume",\n',
        )

    old = (
        'elif component in {"descending_ranking", "ascending_ranking"}:'
    )
    new = (
        'elif component in {\n'
        '                "descending_ranking",\n'
        '                "ascending_ranking",\n'
        '                "descending_lead_volume",\n'
        '            }:'
    )

    if old in text:
        text = text.replace(old, new)

    PATH.write_text(text, encoding="utf-8")
    print("[PASS] Evaluator ranking patch applied.")


if __name__ == "__main__":
    main()
