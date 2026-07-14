import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
LOCAL_OUTPUT_ROOT = (AI_SERVICE_ROOT / "local_calibration_outputs").resolve()
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.services.semantic_calibration import load_calibration_fixture  # noqa: E402
from app.services.semantic_output_collection import collect_semantic_outputs  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="显式授权后采集脱敏语义校准输出；默认不联网。")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--env-file")
    parser.add_argument(
        "--fixture",
        default=str(AI_SERVICE_ROOT / "tests" / "fixtures" / "verification_semantic_calibration.json"),
    )
    parser.add_argument("--output-dir", default=str(LOCAL_OUTPUT_ROOT / "semantic-runs"))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--model-label")
    parser.add_argument("--delay-seconds", type=float, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-cases", type=int)
    args = parser.parse_args(argv)

    if not args.allow_network:
        print("网络访问未授权：必须显式提供--allow-network；未创建Provider，也未读取模型密钥。", file=sys.stderr)
        return 2
    if args.repeat < 1:
        parser.error("--repeat必须至少为1")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds不能为负数")

    if args.env_file:
        try:
            _load_environment_file(args.env_file)
        except FileNotFoundError:
            print("指定的环境文件不存在，未创建Provider。", file=sys.stderr)
            return 2
        except (OSError, RuntimeError, ValueError):
            print("指定的环境文件无法安全加载，未创建Provider。", file=sys.stderr)
            return 2

    output_dir = _safe_output_directory(args.output_dir)
    fixture_path = Path(args.fixture)
    fixture_sha256 = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    fixture = load_calibration_fixture(fixture_path)
    case_ids = set(args.case_id) if args.case_id else None
    unknown_case_ids = sorted((case_ids or set()) - {case.case_id for case in fixture.cases})
    if unknown_case_ids:
        print(
            "fixture中不存在case_id: " + ", ".join(unknown_case_ids) + "；未调用Provider。",
            file=sys.stderr,
        )
        return 2
    (
        provider,
        provider_name,
        configured_model,
        article_max_chars,
        max_tokens,
        temperature,
        thinking_enabled,
    ) = _create_authorized_provider()
    collect_semantic_outputs(
        provider=provider,
        provider_name=provider_name,
        model_name=configured_model,
        fixture=fixture,
        output_path=output_dir / "semantic-runs.json",
        repeat=args.repeat,
        case_ids=case_ids,
        max_cases=args.max_cases,
        delay_seconds=args.delay_seconds,
        resume=args.resume,
        article_max_chars=article_max_chars,
        fixture_sha256=fixture_sha256,
        run_label=args.model_label,
        max_tokens=max_tokens,
        temperature=temperature,
        thinking_enabled=thinking_enabled,
        code_commit=_safe_git_commit(),
    )
    return 0


def _create_authorized_provider():
    from app.core.config import Settings
    from app.llm.factory import create_llm_provider

    config = Settings()
    provider = create_llm_provider(config.llm_provider, config=config)
    is_deepseek = config.llm_provider.strip().lower() == "deepseek"
    model_name = config.deepseek_model if is_deepseek else "fake"
    max_tokens = config.deepseek_max_tokens if is_deepseek else None
    thinking_enabled = config.deepseek_thinking_enabled if is_deepseek else None
    temperature = (
        config.deepseek_temperature
        if is_deepseek and not config.deepseek_thinking_enabled
        else None
    )
    return (
        provider,
        provider.name,
        model_name,
        config.verify_semantic_article_max_chars,
        max_tokens,
        temperature,
        thinking_enabled,
    )


def _load_environment_file(value: str) -> None:
    path = Path(value)
    if not path.is_file():
        raise FileNotFoundError("environment file does not exist")
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError("python-dotenv is unavailable") from exc
    load_dotenv(dotenv_path=path, override=True, verbose=False)


def _safe_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=AI_SERVICE_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip().lower()
    if len(commit) == 40 and all(character in "0123456789abcdef" for character in commit):
        return commit
    return None


def _safe_output_directory(value: str) -> Path:
    output_dir = Path(value).resolve()
    try:
        output_dir.relative_to(LOCAL_OUTPUT_ROOT)
    except ValueError as exc:
        raise ValueError("采集输出目录必须位于ai_service/local_calibration_outputs/内") from exc
    return output_dir


if __name__ == "__main__":
    raise SystemExit(main())
