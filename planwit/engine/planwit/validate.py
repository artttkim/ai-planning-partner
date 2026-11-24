"""ID 연결 검사. 고칠 것이 있으면 목록을 돌려준다."""
from __future__ import annotations

import re
from pathlib import Path

from . import paths
from .screens import all_components, load_screens

FR_RE = re.compile(r"^\|\s*(FR-\d+(?:-\d+)?)\s*\|")


def task_requirements(task_dir: Path) -> list[str]:
    summary = paths.summary(task_dir)
    if not summary.exists():
        return []
    return [m[1] for line in summary.read_text(encoding="utf-8").splitlines() if (m := FR_RE.match(line.strip()))]


def check(task_dir: Path) -> list[str]:
    return check_all(task_dir)[0]


def check_all(task_dir: Path) -> tuple[list[str], list[str]]:
    """(고칠 것, 확인할 것)."""
    from . import service

    problems, notes = [], []
    screens = load_screens(task_dir)
    ids = [s.id for s in screens]
    for dup in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"화면 ID {dup}가 두 번 이상 쓰였어요.")
    covered = {r for s in screens for r in s.requirements}
    for fr in task_requirements(task_dir):
        if fr not in covered:
            problems.append(f"{fr}가 어떤 화면에도 연결되지 않았어요.")
    known = set(ids)
    workspace = paths.workspace_of(task_dir)
    if paths.is_workspace(workspace) and not paths.is_service(task_dir):
        known |= set(service.inventory(workspace)["SCR"])  # 기준본이나 다른 과제의 화면을 가리킬 수 있다
        p2, n2 = service.overlaps(task_dir)
        problems += p2
        notes += n2
    for s in screens:
        comps = all_components(s)
        cids = [c.id for c in comps]
        for dup in sorted({i for i in cids if cids.count(i) > 1}):
            problems.append(f"{s.id}: 구성 요소 ID {dup}가 두 번 이상 쓰였어요.")
        markers = {str(c.marker) for c in comps if c.marker is not None}
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
    return problems, notes
