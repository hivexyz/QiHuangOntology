from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _bootstrap_path() -> None:
    repo_backend = Path(__file__).resolve().parents[1]
    src_path = repo_backend / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def main() -> int:
    _bootstrap_path()
    from qihuang_shield.services.golden_eval import GoldenEvaluator, load_golden_cases
    from qihuang_shield.services.guideline_import import GuidelineOntologyExtractor
    from qihuang_shield.services.terminology import StoreTerminologyResolver
    from qihuang_shield.store import InMemoryStore

    parser = argparse.ArgumentParser(description="Evaluate QiHuang Shield extraction against a JSONL golden set.")
    parser.add_argument("golden_path", help="Path to JSONL golden cases.")
    parser.add_argument("--output", help="Optional path to write the JSON report.")
    args = parser.parse_args()

    store = InMemoryStore(seed_demo_data=True)
    extractor = GuidelineOntologyExtractor(StoreTerminologyResolver(store))
    report = GoldenEvaluator(extractor).evaluate(load_golden_cases(args.golden_path))
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
