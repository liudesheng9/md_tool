from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, err = proc.communicate()
    return proc.returncode, out, err


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    compat = [sys.executable, str(repo_root / "split_markdown.py")]
    fcfs = str(repo_root / "test" / "FCFS.md")

    failures: list[str] = []

    # 1) Invalid old grammar should be refused before running translate-md
    cmd1 = compat + [
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
    ]
    rc1, out1, err1 = run(cmd1)
    # Accept either argparse failure (missing -i) or stage-level refusal
    if not (rc1 != 0 and ("-i/--input" in err1 or "Stage 'translate-md'" in err1)):
        failures.append(
            "Old grammar did not fail early as expected\n"
            f" rc={rc1}\nSTDOUT:\n{out1}\nSTDERR:\n{err1}"
        )

    # 2) Minimal valid pipeline: format-newlines only
    cmd2 = compat + [
        "pipeline",
        "-i",
        fcfs,
        "--no-output",
        "=",
        "format-newlines",
    ]
    rc2, out2, err2 = run(cmd2)
    if rc2 != 0:
        failures.append(
            "Valid pipeline (format-newlines) failed\n"
            f" rc={rc2}\nSTDOUT:\n{out2}\nSTDERR:\n{err2}"
        )

    # 3) Final split without -o should fail
    cmd3 = compat + [
        "pipeline",
        "-i",
        fcfs,
        "--no-output",
        "=",
        "format-newlines",
        "=",
        "split",
        "2",
    ]
    rc3, out3, err3 = run(cmd3)
    if rc3 == 0:
        failures.append(
            "Final split without -o should have failed\n"
            f" rc={rc3}\nSTDOUT:\n{out3}\nSTDERR:\n{err3}"
        )

    # 4) Final split with -o should pass
    out_base = repo_root / "test" / "smoke_parts.md"
    try:
        out_base.unlink(missing_ok=True)  # ensure clean
    except Exception:
        pass
    cmd4 = compat + [
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
        str(out_base),
    ]
    rc4, out4, err4 = run(cmd4)
    if rc4 != 0:
        failures.append(
            "Final split with -o failed\n"
            f" rc={rc4}\nSTDOUT:\n{out4}\nSTDERR:\n{err4}"
        )

    if failures:
        print("SMOKE FAILURES:")
        for f in failures:
            print(" -", f)
        return 1

    print("Smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
