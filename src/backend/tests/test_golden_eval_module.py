from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from qihuang_shield.dependencies import store
from qihuang_shield.services.golden_eval import GoldenEvaluator, load_golden_cases
from qihuang_shield.services.guideline_import import GuidelineOntologyExtractor
from qihuang_shield.services.terminology import StoreTerminologyResolver


def test_golden_evaluator_reports_metrics_for_smoke_fixture(client) -> None:
    cases = load_golden_cases("eval/golden_smoke.jsonl")
    extractor = GuidelineOntologyExtractor(StoreTerminologyResolver(store))

    report = GoldenEvaluator(extractor).evaluate(cases)

    assert report["case_count"] == 1
    assert report["overall"]["concepts"]["recall"] > 0
    assert report["overall"]["assertions"]["recall"] > 0
    assert "rule" in report["by_extractor_engine"]
    assert report["cases"][0]["case_id"] == "tcm-core-smoke"


def test_golden_eval_cli_writes_json_report(tmp_path) -> None:
    output_path = tmp_path / "golden-report.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_golden.py",
            "eval/golden_smoke.jsonl",
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    report = json.loads(Path(output_path).read_text(encoding="utf-8"))
    assert report["case_count"] == 1
    assert "overall" in report
