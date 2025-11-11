from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple


def run(cmd: list[str], *, env: Optional[dict[str, str]] = None) -> tuple[int, str, str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=run_env,
    )
    out, err = proc.communicate()
    return proc.returncode, out, err


def cleanup_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


ScenarioResult = Tuple[str, str]


@dataclass
class SmokeScenario:
    name: str
    command_factory: Callable[[], list[str]]
    validator: Callable[[int, str, str], ScenarioResult]
    env: Optional[dict[str, str]] = None
    setup: Optional[Callable[[], None]] = None
    cleanup: Optional[Callable[[], None]] = None


def run_scenario(scenario: SmokeScenario) -> ScenarioResult:
    try:
        if scenario.setup:
            scenario.setup()
        rc, out, err = run(scenario.command_factory(), env=scenario.env)
        return scenario.validator(rc, out, err)
    finally:
        if scenario.cleanup:
            scenario.cleanup()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    compat = [sys.executable, str(repo_root / "split_markdown.py")]
    fcfs_path = repo_root / "test" / "FCFS.md"
    fcfs = str(fcfs_path)
    fcfs_markers = ["Oliver Hart", "Library of Congress"]
    fake_translate_env = {"MD_TOOL_FAKE_TRANSLATE": "stub"}

    failures: list[str] = []
    reports: list[tuple[str, str, str]] = []

    def add_report(name: str, status: str, detail: str = "") -> None:
        label = status.upper()
        reports.append((label, name, detail))
        if label == "FAIL":
            failures.append(f"{name} failed{': ' + detail if detail else ''}")

    def marker_failures(path: Path) -> list[str]:
        if not path.is_file():
            return fcfs_markers[:]
        text = path.read_text(encoding="utf-8")
        return [marker for marker in fcfs_markers if marker not in text]

    def scenario_result(condition: bool, fail_detail: str) -> ScenarioResult:
        return ("PASS", "") if condition else ("FAIL", fail_detail)

    def cleanup_factory(paths: Iterable[Path]) -> Callable[[], None]:
        return lambda: cleanup_paths(paths)

    scenarios: list[SmokeScenario] = []

    scenarios.append(
        SmokeScenario(
            name="Legacy grammar rejection",
            command_factory=lambda: compat
            + [
                "pipeline",
                "translate-md",
                fcfs,
                "-t",
                "zh",
                "=",
                "format-newlines",
                "=",
                "split",
                "2",
                "-o",
                str(repo_root / "test" / "out_invalid_should_not_write.md"),
            ],
            validator=lambda rc, _out, err: (
                ("PASS", "")
                if rc != 0 and ("-i/--input" in err or "Stage 'translate-md'" in err)
                else ("FAIL", f"rc={rc}, stderr={err.strip()}")
            ),
        )
    )

    scenarios.append(
        SmokeScenario(
            name="Pipeline: format-newlines",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "--no-output",
                "=",
                "format-newlines",
            ],
            validator=lambda rc, _out, err: scenario_result(rc == 0, f"rc={rc}, stderr={err.strip()}"),
        )
    )

    scenarios.append(
        SmokeScenario(
            name="Pipeline: split requires -o",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "--no-output",
                "=",
                "format-newlines",
                "=",
                "split",
                "2",
            ],
            validator=lambda rc, _out, _err: ("PASS", "") if rc != 0 else ("FAIL", "split accepted missing -o"),
        )
    )

    split_parts_base = repo_root / "test" / "smoke_parts.md"
    split_parts_outputs = [
        split_parts_base.with_name(f"{split_parts_base.stem}_part_{index}{split_parts_base.suffix}")
        for index in range(1, 3)
    ]
    scenarios.append(
        SmokeScenario(
            name="Pipeline: split with -o",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "--no-output",
                "=",
                "format-newlines",
                "=",
                "split",
                "2",
                "-o",
                str(split_parts_base),
            ],
            setup=cleanup_factory([split_parts_base, *split_parts_outputs]),
            cleanup=cleanup_factory(split_parts_outputs),
            validator=lambda rc, _out, err: (
                ("FAIL", f"rc={rc}, stderr={err.strip()}")
                if rc != 0
                else (
                    ("PASS", "")
                    if not [str(path) for path in split_parts_outputs if not path.is_file()]
                    else (
                        "FAIL",
                        "missing parts: "
                        + ", ".join(str(path) for path in split_parts_outputs if not path.is_file()),
                    )
                )
            ),
        )
    )

    format_cli_out = repo_root / "test" / "smoke_format_cli.md"
    scenarios.append(
        SmokeScenario(
            name="CLI: format-newlines",
            command_factory=lambda: compat + ["format-newlines", fcfs, "-o", str(format_cli_out)],
            setup=cleanup_factory([format_cli_out]),
            cleanup=cleanup_factory([format_cli_out]),
            validator=lambda rc, _out, err: scenario_result(
                rc == 0 and format_cli_out.is_file(), f"rc={rc}, stderr={err.strip()}"
            ),
        )
    )

    split_cli_base = repo_root / "test" / "smoke_cli_split.md"
    split_cli_parts = [
        split_cli_base.with_name(f"{split_cli_base.stem}_part_{index}{split_cli_base.suffix}") for index in range(1, 3)
    ]
    scenarios.append(
        SmokeScenario(
            name="CLI: split",
            command_factory=lambda: compat + ["split", fcfs, "2", "-o", str(split_cli_base)],
            setup=cleanup_factory(split_cli_parts),
            cleanup=cleanup_factory(split_cli_parts),
            validator=lambda rc, _out, err: scenario_result(
                rc == 0 and all(path.is_file() for path in split_cli_parts),
                f"rc={rc}, stderr={err.strip()}",
            ),
        )
    )

    combine_cli_out = repo_root / "test" / "smoke_cli_combined.md"

    def combine_setup() -> None:
        cleanup_paths([combine_cli_out, *split_cli_parts])
        rc, _out, err = run(
            compat + ["split", fcfs, "2", "-o", str(split_cli_base)],
        )
        if rc != 0 or not all(path.is_file() for path in split_cli_parts):
            raise RuntimeError(f"split prep failed: {err.strip()}")

    scenarios.append(
        SmokeScenario(
            name="CLI: combine",
            command_factory=lambda: compat
            + [
                "combine",
                *(str(path) for path in split_cli_parts),
                "-o",
                str(combine_cli_out),
            ],
            setup=combine_setup,
            cleanup=cleanup_factory([combine_cli_out, *split_cli_parts]),
            validator=lambda rc, _out, err: (
                ("FAIL", f"rc={rc}, stderr={err.strip()}")
                if rc != 0 or not combine_cli_out.is_file()
                else (
                    ("PASS", "")
                    if not marker_failures(combine_cli_out)
                    else (
                        "FAIL",
                        "missing markers: " + ", ".join(marker_failures(combine_cli_out)),
                    )
                )
            ),
        )
    )

    def pipeline_stage_validator(path: Path) -> Callable[[int, str, str], ScenarioResult]:
        def _validator(rc: int, _out: str, err: str) -> ScenarioResult:
            if rc != 0 or not path.is_file():
                return ("FAIL", f"rc={rc}, stderr={err.strip()}")
            missing = marker_failures(path)
            if missing:
                return ("FAIL", "missing markers: " + ", ".join(missing))
            return ("PASS", "")

        return _validator

    recombined_out = repo_root / "test" / "smoke_pipeline_recombined.md"
    scenarios.append(
        SmokeScenario(
            name="Pipeline: format->split->combine (stage output)",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "--no-output",
                "=",
                "format-newlines",
                "=",
                "split",
                "2",
                "=",
                "combine",
                "--output",
                str(recombined_out),
            ],
            setup=cleanup_factory([recombined_out]),
            cleanup=cleanup_factory([recombined_out]),
            validator=pipeline_stage_validator(recombined_out),
        )
    )

    global_out = repo_root / "test" / "smoke_pipeline_global.md"
    scenarios.append(
        SmokeScenario(
            name="Pipeline: format->split->combine (global -o)",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "-o",
                str(global_out),
                "=",
                "format-newlines",
                "=",
                "split",
                "2",
                "=",
                "combine",
            ],
            setup=cleanup_factory([global_out]),
            cleanup=cleanup_factory([global_out]),
            validator=pipeline_stage_validator(global_out),
        )
    )

    translate_pipeline_out = repo_root / "test" / "smoke_translate_pipeline.md"
    scenarios.append(
        SmokeScenario(
            name="Pipeline: translate-md",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "-o",
                str(translate_pipeline_out),
                "=",
                "translate-md",
                "-t",
                "zz",
                "--workers",
                "1",
                "--delay-min",
                "0",
                "--delay-max",
                "0",
                "--bulk-delay-every",
                "0",
                "--retry-count",
                "0",
            ],
            env=fake_translate_env,
            setup=cleanup_factory([translate_pipeline_out]),
            cleanup=cleanup_factory([translate_pipeline_out]),
            validator=lambda rc, _out, err: (
                ("FAIL", f"rc={rc}, stderr={err.strip()}")
                if rc != 0 or not translate_pipeline_out.is_file()
                else (
                    ("PASS", "")
                    if "[auto->zz|stub]" in translate_pipeline_out.read_text(encoding="utf-8")
                    else ("FAIL", "missing fake translation marker")
                )
            ),
        )
    )

    scenarios.append(
        SmokeScenario(
            name="CLI: translate text",
            command_factory=lambda: compat + ["translate", "-t", "zz", "Hello", "world"],
            env=fake_translate_env,
            validator=lambda rc, out, err: (
                ("PASS", "")
                if rc == 0 and "[auto->zz|stub] HELLO WORLD" in out.strip()
                else ("FAIL", f"rc={rc}, stderr={err.strip()}")
            ),
        )
    )

    translate_cli_out = repo_root / "test" / "smoke_translate_cli.md"
    translate_cli_debug = repo_root / "test" / "smoke_translate_cli.json"
    scenarios.append(
        SmokeScenario(
            name="CLI: translate-md",
            command_factory=lambda: compat
            + [
                "translate-md",
                fcfs,
                "-t",
                "zz",
                "--output",
                str(translate_cli_out),
                "--debug-output",
                str(translate_cli_debug),
                "--workers",
                "1",
                "--delay-min",
                "0",
                "--delay-max",
                "0",
                "--bulk-delay-every",
                "0",
                "--retry-count",
                "0",
            ],
            env=fake_translate_env,
            setup=cleanup_factory([translate_cli_out, translate_cli_debug]),
            cleanup=cleanup_factory([translate_cli_out, translate_cli_debug]),
            validator=lambda rc, _out, err: (
                ("FAIL", f"rc={rc}, stderr={err.strip()}")
                if rc != 0 or not translate_cli_out.is_file() or not translate_cli_debug.is_file()
                else (
                    ("PASS", "")
                    if "[auto->zz|stub]" in translate_cli_out.read_text(encoding="utf-8")
                    and '"paragraphs":' in translate_cli_debug.read_text(encoding="utf-8")
                    else ("FAIL", "output or debug data missing expected markers")
                )
            ),
        )
    )

    format_stage_path = repo_root / "test" / "smoke_pipeline_format_stage.md"
    format_stage_final = repo_root / "test" / "smoke_pipeline_format_stage_final.md"
    scenarios.append(
        SmokeScenario(
            name="Pipeline: format stage output",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "-o",
                str(format_stage_final),
                "=",
                "format-newlines",
                "--output",
                str(format_stage_path),
                "=",
                "split",
                "2",
                "=",
                "combine",
            ],
            setup=cleanup_factory([format_stage_path, format_stage_final]),
            cleanup=cleanup_factory([format_stage_path, format_stage_final]),
            validator=lambda rc, _out, err: (
                ("FAIL", f"rc={rc}, stderr={err.strip()}")
                if rc != 0 or not format_stage_final.is_file() or not format_stage_path.is_file()
                else (
                    ("PASS", "")
                    if not marker_failures(format_stage_final)
                    else ("FAIL", "missing markers: " + ", ".join(marker_failures(format_stage_final)))
                )
            ),
        )
    )

    split_stage_base = repo_root / "test" / "smoke_pipeline_split_stage.md"
    split_stage_outputs = [
        split_stage_base.with_name(f"{split_stage_base.stem}_part_{index}{split_stage_base.suffix}")
        for index in range(1, 3)
    ]
    split_stage_final = repo_root / "test" / "smoke_pipeline_split_stage_final.md"
    scenarios.append(
        SmokeScenario(
            name="Pipeline: split stage output",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "-o",
                str(split_stage_final),
                "=",
                "format-newlines",
                "=",
                "split",
                "2",
                "-o",
                str(split_stage_base),
                "=",
                "combine",
            ],
            setup=cleanup_factory([split_stage_final, *split_stage_outputs]),
            cleanup=cleanup_factory([split_stage_final, *split_stage_outputs]),
            validator=lambda rc, _out, err: (
                ("FAIL", f"rc={rc}, stderr={err.strip()}")
                if rc != 0 or not split_stage_final.is_file()
                else (
                    ("PASS", "")
                    if not marker_failures(split_stage_final)
                    else ("FAIL", "missing markers: " + ", ".join(marker_failures(split_stage_final)))
                )
            ),
        )
    )

    translate_stage_final = repo_root / "test" / "smoke_pipeline_translate_stage_final.md"
    translate_stage_debug = repo_root / "test" / "smoke_pipeline_translate_stage.json"
    scenarios.append(
        SmokeScenario(
            name="Pipeline: translate debug output",
            command_factory=lambda: compat
            + [
                "pipeline",
                "-i",
                fcfs,
                "-o",
                str(translate_stage_final),
                "=",
                "format-newlines",
                "=",
                "translate-md",
                "-t",
                "zz",
                "--workers",
                "1",
                "--delay-min",
                "0",
                "--delay-max",
                "0",
                "--bulk-delay-every",
                "0",
                "--retry-count",
                "0",
                "--debug-output",
                str(translate_stage_debug),
                "=",
                "split",
                "2",
                "=",
                "combine",
            ],
            env=fake_translate_env,
            setup=cleanup_factory([translate_stage_final, translate_stage_debug]),
            cleanup=cleanup_factory([translate_stage_final, translate_stage_debug]),
            validator=lambda rc, _out, err: (
                ("FAIL", f"rc={rc}, stderr={err.strip()}")
                if rc != 0 or not translate_stage_final.is_file() or not translate_stage_debug.is_file()
                else (
                    ("PASS", "")
                    if "[auto->zz|stub]" in translate_stage_final.read_text(encoding="utf-8")
                    and '"paragraphs":' in translate_stage_debug.read_text(encoding="utf-8")
                    else ("FAIL", "missing fake translation marker or debug payload")
                )
            ),
        )
    )

    for scenario in scenarios:
        try:
            status, detail = run_scenario(scenario)
        except Exception as exc:  # pragma: no cover - defensive
            add_report(scenario.name, "FAIL", f"{exc}")
        else:
            add_report(scenario.name, status, detail)

    print("---- Smoke Test Report ----")
    for status, name, detail in reports:
        message = f"[{status}] {name}"
        if detail:
            message += f" - {detail}"
        print(" ", message)

    if failures:
        print("SMOKE FAILURES:")
        for f in failures:
            print(" -", f)
        return 1

    print("Smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
