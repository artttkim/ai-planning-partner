"""ID 연결 검사. 고칠 것이 있으면 목록을 돌려준다."""
from __future__ import annotations

import re
from pathlib import Path

from .screens import load_screens

FR_RE = re.compile(r"^\|\s*(FR-\d+(?:-\d+)?)\s*\|")


def task_requirements(task_dir: Path) -> list[str]:
    summary = Path(task_dir) / "과제요약.md"
    if not summary.exists():
        return []
    return [m[1] for line in summary.read_text(encoding="utf-8").splitlines() if (m := FR_RE.match(line.strip()))]


def check(task_dir: Path) -> list[str]:
    problems = []
    screens = load_screens(task_dir)
    ids = [s.id for s in screens]
    for dup in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"화면 ID {dup}가 두 번 이상 쓰였어요.")
    covered = {r for s in screens for r in s.requirements}
    for fr in task_requirements(task_dir):
        if fr not in covered:
            problems.append(f"{fr}가 어떤 화면에도 연결되지 않았어요.")
    known = set(ids)
    for s in screens:
        markers = {str(c.marker) for c in s.components if c.marker is not None}
        descs = {str(d.no) for d in s.descriptions}
        for m in sorted(markers - descs):
            problems.append(f"{s.id}: 번호 {m}에 설명이 없어요.")
        for d in sorted(descs - markers):
            if s.status != "참고":
                problems.append(f"{s.id}: 설명 {d}에 해당하는 번호 표시가 없어요.")
        for d in s.descriptions:
            for ref in re.findall(r"SCR-\d+(?:-P\d+)?", d.text):
                if ref not in known:
                    problems.append(f"{s.id}: 설명 {d.no}이 가리키는 {ref} 화면이 없어요.")
    return problems
