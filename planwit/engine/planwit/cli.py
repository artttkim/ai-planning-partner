"""엔진 명령 모음. 명령은 04_개발_설계.md 5.1을 따른다."""
import argparse
import importlib
import json
import platform
import sys
from pathlib import Path

from . import __version__

MIN_PYTHON = (3, 11)
REQUIRED = {
    "pptx": "python-pptx",
    "docx": "python-docx",
    "openpyxl": "openpyxl",
    "yaml": "PyYAML",
    "pypdf": "pypdf",
}


def doctor() -> int:
    """Python 버전과 필요한 패키지를 점검한다. 문제가 없으면 0을 돌려준다."""
    problems = []
    if sys.version_info < MIN_PYTHON:
        problems.append(f"Python {platform.python_version()}은 너무 낮아요. 3.11 이상이 필요해요.")
    for module, package in REQUIRED.items():
        try:
            importlib.import_module(module)
        except ImportError:
            problems.append(f"{package} 패키지가 없어요.")
    if problems:
        print("플랜윗 엔진 점검: 문제 있음")
        for p in problems:
            print(f"- {p}")
        return 1
    print(f"플랜윗 엔진 점검: 정상 (엔진 {__version__}, Python {platform.python_version()})")
    return 0


def build(kind: str, task: str, version: str) -> int:
    from . import build_dev, build_pptx, snapshot

    task_dir = Path(task).resolve()
    try:
        if kind in ("pptx", "all"):
            out = build_pptx.build(task_dir, version=version)
            snapshot.record(task_dir, out)
            print(f"생성: {out.relative_to(task_dir).as_posix()}")
        if kind in ("dev", "all"):
            for out in build_dev.build(task_dir):
                print(f"생성: {out.relative_to(task_dir).as_posix()}")
    except PermissionError as e:
        print(f"생성 실패: 파일이 다른 프로그램에서 열려 있어요. 파워포인트를 닫고 다시 시도해 주세요. ({e.filename})")
        return 1
    except (ValueError, FileNotFoundError) as e:
        print(f"생성 실패: {e}")
        return 1
    return 0


def validate(task: str) -> int:
    from . import validate as v

    problems = v.check(Path(task).resolve())
    if not problems:
        print("ID 검사: 문제 없음")
        return 0
    print("ID 검사: 고칠 것")
    for p in problems:
        print(f"- {p}")
    return 1


def extract(path: str, out: str | None) -> int:
    from . import extract as ex

    try:
        text = ex.to_text(Path(path))
    except Exception as e:  # 읽지 못한 이유를 그대로 보여 준다
        print(f"읽기 실패: {Path(path).name}: {e}")
        return 1
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"저장: {out}")
    else:
        print(text)
    return 0


def detect(workspace: str | None, hook: bool) -> int:
    from . import detect as d

    if hook:
        # 훅에서는 표준 입력으로 세션 정보(JSON)가 들어온다. 어떤 오류도 기획자의 요청을 막지 않게 한다.
        try:
            raw = sys.stdin.read()
            workspace = json.loads(raw).get("cwd") if raw.strip() else None
        except Exception:
            workspace = None
        try:
            msg = d.scan(Path(workspace or Path.cwd()))
        except Exception:
            return 0
    else:
        msg = d.scan(Path(workspace or Path.cwd()))
    if msg:
        print(msg)
    elif not hook:
        print("직접 고친 파일 없음")
    return 0


def migrate(workspace) -> int:
    from . import paths
    root = Path(workspace or Path.cwd())
    tasks = [p for p in sorted((root / "과제").glob("*/")) if p.is_dir()] if (root / "과제").exists() else [root]
    for task in tasks:
        moved = paths.migrate(task)
        if moved:
            print(f"{task.name}: " + ", ".join(moved))
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="planwit", description="플랜윗 엔진")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Python과 패키지 점검")
    sub.add_parser("version", help="엔진 버전")
    b = sub.add_parser("build", help="원본에서 파일 생성")
    b.add_argument("kind", choices=["pptx", "dev", "all"])
    b.add_argument("task", help="과제 폴더 경로")
    b.add_argument("--version", dest="doc_version", default="v0.1", help="문서 버전 (기본 v0.1)")
    v = sub.add_parser("validate", help="ID 연결 검사")
    v.add_argument("task")
    e = sub.add_parser("extract", help="문서를 텍스트로 변환")
    e.add_argument("path")
    e.add_argument("--out")
    mg = sub.add_parser("migrate", help="예전 구조의 과제 폴더를 지금 구조로 옮기기")
    mg.add_argument("workspace", nargs="?")
    dt = sub.add_parser("detect", help="직접 고친 회사 양식 파일 감지")
    dt.add_argument("workspace", nargs="?")
    dt.add_argument("--hook", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "build":
        return build(args.kind, args.task, args.doc_version)
    if args.command == "validate":
        return validate(args.task)
    if args.command == "extract":
        return extract(args.path, args.out)
    if args.command == "detect":
        return detect(args.workspace, args.hook)
    if args.command == "migrate":
        return migrate(args.workspace)
    return 2
