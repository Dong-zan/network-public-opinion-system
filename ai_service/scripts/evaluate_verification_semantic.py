import argparse
import json
import sys
from pathlib import Path


AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.services.semantic_calibration import (  # noqa: E402
    evaluate_calibration,
    evaluate_repeated_calibration,
    load_calibration_fixture,
    load_repeated_outputs,
    load_saved_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="离线评测/ai/verify语义候选准入，不调用任何模型或网络。")
    parser.add_argument(
        "--mode",
        choices=("fixture-validator", "saved-output", "repeated-saved-output"),
        default="fixture-validator",
    )
    parser.add_argument(
        "--fixture",
        default=str(AI_SERVICE_ROOT / "tests" / "fixtures" / "verification_semantic_calibration.json"),
    )
    parser.add_argument("--saved-output", help="saved-output模式下人工保存的模型JSON文件")
    parser.add_argument("--repeated-output", help="repeated-saved-output模式下的JSON文件或目录")
    parser.add_argument("--report", help="可选：写入机器可读JSON报告")
    args = parser.parse_args()

    fixture = load_calibration_fixture(args.fixture)
    saved_outputs = None
    if args.mode == "saved-output":
        if not args.saved_output:
            parser.error("saved-output模式必须提供--saved-output")
        saved_outputs = load_saved_outputs(args.saved_output)
        report = evaluate_calibration(fixture, saved_outputs=saved_outputs)
    elif args.mode == "repeated-saved-output":
        repeated_path = args.repeated_output or args.saved_output
        if not repeated_path:
            parser.error("repeated-saved-output模式必须提供--repeated-output")
        report = evaluate_repeated_calibration(fixture, load_repeated_outputs(repeated_path))
    else:
        report = evaluate_calibration(fixture)
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        Path(args.report).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
