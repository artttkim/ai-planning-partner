"""과제 폴더 구조. 폴더와 파일 이름은 여기에서만 정한다.

과제/<YYYY-MM-DD>_<과제명>/
├─ 00_과제요약.md
├─ 01_검수함.md
├─ 02_결정기록.md
├─ 1_입력자료/        기획자가 준 자료
├─ 2_기획문서/        단계별 원본 (NN_<단계>.md, NN_화면설계/)
├─ 3_결과물/          원본에서 생성한 파일 (화면 설계서 .pptx)
│  └─ 개발용/         개발용 화면 명세 (SCR-*.yaml)
└─ .planwit/          생성 기록, 뽑은 텍스트
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

SUMMARY = "00_과제요약.md"
INBOX = "01_검수함.md"
DECISIONS = "02_결정기록.md"
INPUT = "1_입력자료"
DOCS = "2_기획문서"
OUTPUT = "3_결과물"
DEV = f"{OUTPUT}/개발용"

# 예전 구조 → 지금 구조
_OLD = [
    ("과제요약.md", SUMMARY),
    ("검수함.md", INBOX),
    ("결정기록.md", DECISIONS),
    ("입력", INPUT),
    ("원본", DOCS),
    ("회사양식", OUTPUT),
]
# 문서 안의 예전 경로 표기. 앞에 글자가 붙은 것(예: 00_과제요약.md)은 이미 새 이름이라 건드리지 않는다.
_TEXT_RENAMES = [
    (r"(?<![\w/])개발용/화면/", f"{DEV}/"),
    (r"(?<![\w/])과제요약\.md", SUMMARY),
    (r"(?<![\w/])검수함\.md", INBOX),
    (r"(?<![\w/])결정기록\.md", DECISIONS),
    (r"(?<![\w/])입력/", f"{INPUT}/"),
    (r"(?<![\w/])원본/", f"{DOCS}/"),
    (r"(?<![\w/])회사양식/", f"{OUTPUT}/"),
]


def summary(task_dir: Path) -> Path:
    return Path(task_dir) / SUMMARY


def docs(task_dir: Path) -> Path:
    return Path(task_dir) / DOCS


def output(task_dir: Path) -> Path:
    return Path(task_dir) / OUTPUT


def dev(task_dir: Path) -> Path:
    return Path(task_dir) / DEV


def _rewrite_refs(task_dir: Path):
    """문서 안의 예전 경로 표기를 새 경로로 바꾼다."""
    files = list(task_dir.glob("*.md")) + list(docs(task_dir).rglob("*.md"))
    for f in files:
        text = f.read_text(encoding="utf-8")
        new = text
        for pattern, repl in _TEXT_RENAMES:
            new = re.sub(pattern, repl, new)
        if new != text:
            f.write_text(new, encoding="utf-8")


def migrate(task_dir: Path) -> list[str]:
    """예전 구조의 과제 폴더를 지금 구조로 옮긴다. 옮긴 항목을 돌려준다. 이미 새 구조면 아무것도 하지 않는다."""
    task_dir = Path(task_dir)
    moved = []
    for old, new in _OLD:
        src, dst = task_dir / old, task_dir / new
        if not src.exists():
            continue
        try:
            if not dst.exists():
                src.rename(dst)
            elif src.is_dir():  # 앞서 일부만 옮겨진 경우: 안의 것을 합친다
                for f in list(src.iterdir()):
                    if f.name.startswith("~$"):
                        continue  # 오피스가 파일을 열 때 만드는 잠금 파일
                    shutil.move(str(f), dst / f.name)
                shutil.rmtree(src)
            else:
                continue
            moved.append(f"{old} → {new}")
        except OSError:
            moved.append(f"{old}: 열려 있는 파일이 있어 옮기지 못함. 파일을 닫고 다시 실행")
    old_dev = task_dir / "개발용"
    if old_dev.exists():
        target = dev(task_dir)
        try:
            target.mkdir(parents=True, exist_ok=True)
            for f in old_dev.rglob("*"):
                if f.is_file():
                    shutil.move(str(f), target / f.name)
            shutil.rmtree(old_dev)
            moved.append(f"개발용 → {DEV}")
        except OSError:
            moved.append("개발용: 열려 있는 파일이 있어 옮기지 못함. 파일을 닫고 다시 실행")
    if moved:
        mp = task_dir / ".planwit" / "manifest.json"
        if mp.exists():
            data = json.loads(mp.read_text(encoding="utf-8"))
            data["files"] = {k.replace("회사양식/", f"{OUTPUT}/"): v for k, v in data.get("files", {}).items()}
            mp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _rewrite_refs(task_dir)
    return moved
