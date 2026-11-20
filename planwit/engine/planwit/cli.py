"""엔진 명령 모음. 명령은 04_개발_설계.md 5.1을 따른다."""
import argparse
import importlib
import platform
import sys

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
        problems.append(
            f"Python {platform.python_version()}은 너무 낮아요. 3.11 이상이 필요해요."
        )
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


def main(argv=None) -> int:
    # Windows 콘솔에서도 한글이 깨지지 않게 한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="planwit", description="플랜윗 엔진")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Python과 패키지 점검")
    sub.add_parser("version", help="엔진 버전")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "version":
        print(__version__)
        return 0
    return 2
