#!/usr/bin/env python3
"""Run @lam/vulture/ws-plugin tests in an isolated consumer-style tree."""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = pathlib.Path(__file__).resolve().parent
CORE_ROOT = ROOT.parent / "lam-vulture"
PLUGIN_PACKAGE = pathlib.Path("@lam") / "vulture" / "ws-plugin"
CORE_PACKAGE = pathlib.Path("@lam") / "vulture"
VERSION_RE = re.compile(r"^(?:lamc\s+)?v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
EXPECT_RE = re.compile(r"^\s*#\s*expect:\s*(.*)$")


def require_lamc() -> str:
    lamc = shutil.which("lamc")
    if lamc is None:
        raise SystemExit("error: lamc is required but was not found on PATH")

    try:
        completed = subprocess.run(
            [lamc, "version"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"error: could not execute 'lamc version': {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SystemExit(f"error: 'lamc version' failed: {detail}")

    version_text = completed.stdout.strip()
    match = VERSION_RE.fullmatch(version_text)
    if match is None:
        raise SystemExit(f"error: unrecognized lamc version output: {version_text!r}")
    version = tuple(int(match.group(index)) for index in range(1, 4))
    if version < (1, 18, 0) or version >= (3, 0, 0):
        raise SystemExit(
            "error: @lam/vulture/ws-plugin tests require lamc >=1.18, <3; "
            f"found {version_text}"
        )
    return lamc


def expected_output(case: pathlib.Path) -> str:
    lines = []
    for line in case.read_text(encoding="utf-8").splitlines():
        match = EXPECT_RE.match(line)
        if match is not None:
            lines.append(match.group(1))
    if not lines:
        raise ValueError("no '# expect:' output directives")
    return "\n".join(lines)


def copy_package(source: pathlib.Path, destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            "*.pyc",
            "build",
            "dist",
            "extlibs",
            "*.lamc-cache",
        ),
    )


def stage_packages(extlibs: pathlib.Path) -> None:
    missing = [
        path
        for path in (CORE_ROOT / "__init__.lam",)
        if not path.is_file()
    ]
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(
            "the sibling @lam/vulture checkout is incomplete; missing " + formatted
        )
    copy_package(CORE_ROOT, extlibs / CORE_PACKAGE)
    copy_package(ROOT, extlibs / PLUGIN_PACKAGE)


def process_details(completed: subprocess.CompletedProcess[str]) -> str:
    details = [f"exit status {completed.returncode}"]
    if completed.stdout:
        details.append("stdout:\n" + completed.stdout.rstrip())
    if completed.stderr:
        details.append("stderr:\n" + completed.stderr.rstrip())
    return "\n".join(details)


def run_case(
    lamc: str,
    case: pathlib.Path,
    temp_root: pathlib.Path,
    extlibs: pathlib.Path,
) -> tuple[bool, str]:
    try:
        expected = expected_output(case)
    except (OSError, ValueError) as exc:
        return False, f"invalid test case: {exc}"

    binary = temp_root / case.stem
    command = [
        lamc,
        "build",
        str(case),
        "--no-cache",
        "--extlibs",
        str(extlibs),
        "-o",
        str(binary),
    ]
    try:
        compiled = subprocess.run(
            command,
            cwd=temp_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired:
        return False, "compile timed out after 240 seconds"
    except OSError as exc:
        return False, f"could not run compiler: {exc}"
    if compiled.returncode != 0:
        return False, "compile failed: " + process_details(compiled)

    try:
        executed = subprocess.run(
            [str(binary)],
            cwd=temp_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "execution timed out after 60 seconds"
    except OSError as exc:
        return False, f"could not execute test binary: {exc}"
    if executed.returncode != 0:
        return False, "execution failed: " + process_details(executed)

    actual = executed.stdout.rstrip("\n")
    if actual != expected:
        detail = f"output mismatch\nexpected: {expected!r}\nactual:   {actual!r}"
        if executed.stderr:
            detail += f"\nstderr:   {executed.stderr.rstrip()!r}"
        return False, detail
    return True, "ok"


def main() -> int:
    lamc = require_lamc()
    cases = sorted(TESTS.glob("test_*.lam"))
    if not cases:
        print("error: no Lam test cases found", file=sys.stderr)
        return 2

    failures: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="lam-vulture-ws-plugin-tests-") as temporary:
        temp_root = pathlib.Path(temporary)
        extlibs = temp_root / "extlibs"
        try:
            stage_packages(extlibs)
        except (OSError, shutil.Error) as exc:
            print(f"error: could not stage test packages: {exc}", file=sys.stderr)
            return 2

        for case in cases:
            print(f"==> {case.name}", flush=True)
            passed, detail = run_case(lamc, case, temp_root, extlibs)
            if passed:
                print(f"PASS {case.name}")
            else:
                print(f"FAIL {case.name}: {detail}", file=sys.stderr)
                failures.append((case.name, detail))

    if failures:
        names = ", ".join(name for name, _ in failures)
        print(f"\n{len(failures)} test file(s) failed: {names}", file=sys.stderr)
        return 1
    print(f"\n{len(cases)} test file(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
