"""기획안 품질 검사. 규칙을 글로만 두지 않고, 엔진이 매번 같은 기준으로 검사한다.

validate가 함께 실행한다. 고칠 것(problems)이 남아 있으면 그 단계를 검수 대기로 올리지 않는다(run 스킬).
- 방향 정의: 필요한 장이 모두 있는가 (새 기능, 새 서비스)
- 화면: 참고한 기존 화면이 있는가, 누르는 요소에 동작이, 입력 요소에 규칙이 있는가, 모호한 말이 없는가
- 흐름: 모든 화면이 유저 플로우에 있는가
- 정책: 화면이 가리킨 정책이 모두 정의되어 있는가
"""
from __future__ import annotations

import re
from pathlib import Path

from . import paths
from .screens import Component, Screen

DIRECTION_SECTIONS = {
    "한 문장": r"한 문장",
    "출시 발표문": r"발표문",
    "차별점": r"차별",
    "습관 고리나 핵심 흐름": r"습관 고리|핵심 흐름",
    "주요 상황": r"상황",
    "플랫폼 제약": r"제약",
    "성공 지표": r"지표",
    "위험": r"위험",
}
ACTION_TYPES = {"기본버튼", "보조버튼", "텍스트링크", "플로팅버튼", "토글", "체크박스", "라디오", "선택상자"}
INPUT_TYPES = {"입력창", "검색창"}
VAGUE = re.compile(r"적절히|적당히|빠르게|알아서|기타|(?<![가-힣])등(?![가-힣])")
ACTION_WORDS = re.compile(r"누르면|고르면|켜면|끄면|바꾸면|입력하|열면|간다|연다|이동|돌아간|저장|닫|시작|넘어간|선택")
INPUT_WORDS = re.compile(r"필수|글자|자\b|최대|최소|형식|입력하는 대로|비어|찾는다|선택")


def _norm(t: str) -> str:
    return t.replace(" ", "")


def _stage_names(task_dir: Path) -> list[str]:
    p = paths.summary(task_dir)
    if not p.is_file():
        return []
    m = re.search(r"## 진행 단계\s*\n(.*?)(?=^## |\Z)", p.read_text(encoding="utf-8"), re.M | re.S)
    if not m:
        return []
    out = []
    for line in m[1].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].isdigit():
            out.append(cells[1])
    return out


def _is_skeleton(s: Screen) -> bool:
    return "- 뼈대:" in (s.note or "")


def _marked_parent(screen: Screen) -> dict[str, Component]:
    """요소 ID → 번호가 달린 가장 가까운 조상(자기 포함)."""
    out: dict[str, Component] = {}

    def walk(c: Component, marked: Component | None):
        here = c if c.marker is not None else marked
        if here is not None:
            out[c.id] = here
        for ch in c.children:
            walk(ch, here)

    for top in screen.components:
        walk(top, None)
    return out


def check(task_dir: Path, screens: list[Screen]) -> tuple[list[str], list[str]]:
    problems, notes = [], []
    task_dir = Path(task_dir)
    if paths.is_service(task_dir):
        return problems, notes
    stages = _stage_names(task_dir)
    docs = paths.docs(task_dir)
    in_workspace = paths.is_workspace(paths.workspace_of(task_dir))

    # 방향 정의
    if any("방향 정의" in s for s in stages):
        found = sorted(docs.glob("*방향정의*.md"))
        if not found:
            problems.append("방향 정의 문서가 없어요 (2_기획문서/NN_방향정의.md).")
        else:
            heads = "\n".join(l for l in found[0].read_text(encoding="utf-8").splitlines() if l.startswith("#"))
            for name, pat in DIRECTION_SECTIONS.items():
                if not re.search(pat, heads):
                    problems.append(f"방향 정의에 '{name}' 장이 없어요.")

    inbox = paths.summary(task_dir).parent / paths.INBOX
    inbox_text = inbox.read_text(encoding="utf-8") if inbox.is_file() else ""

    for s in screens:
        if s.status == "참고":
            continue
        # 참고 화면
        if in_workspace and not s.ref and not re.search(rf"기존 화면 확인 필요[^\n]*{re.escape(s.id)}", inbox_text):
            problems.append(f"{s.id}: 따른 기존 화면(- 참고 화면:)이 없어요. 찾지 못했으면 검수함에 '기존 화면 확인 필요: {s.id}'를 남기세요.")
        if _is_skeleton(s):
            continue
        by_no = {str(d.no): d for d in s.descriptions}
        owner = _marked_parent(s)
        for d in s.descriptions:
            if VAGUE.search(d.text):
                problems.append(f"{s.id} 설명 {d.no}: 모호한 말('{VAGUE.search(d.text)[0]}')을 값이나 목록으로 바꾸세요.")
        for top in s.components:
            for c in top.walk():
                t = _norm(c.type)
                if t not in ACTION_TYPES | INPUT_TYPES:
                    continue
                if s.status == "변경" and not (c.changed or (owner.get(c.id) and owner[c.id].changed)):
                    continue  # 변경 화면은 바뀐 요소만 설명한다
                m = owner.get(c.id)
                if m is not None and m.marker is not None and _norm(m.type) in ("팝업", "바텀시트") and m is not c:
                    continue  # 팝업 안의 번호 없는 버튼(취소, 닫기)은 닫는 것이 기본이다
                if m is None:
                    problems.append(f"{s.id}: '{c.label or c.type}'({c.id})에 번호와 설명이 없어요. 누르거나 입력하는 요소예요.")
                    continue
                d = by_no.get(str(m.marker))
                if not d:
                    continue  # 번호-설명 짝은 validate가 따로 잡는다
                if t in INPUT_TYPES and not INPUT_WORDS.search(d.text):
                    problems.append(f"{s.id} 설명 {d.no}: 입력 규칙(필수 여부, 글자 수나 형식)이 없어요.")
                elif t in ACTION_TYPES and not ACTION_WORDS.search(d.text):
                    problems.append(f"{s.id} 설명 {d.no}: 누르거나 고르면 무슨 일이 생기는지가 없어요.")
        bare = [d.no for d in s.descriptions if re.search(r"(?<!\()SCR-\d+", d.text)]
        if bare:
            notes.append(f"{s.id} 설명 {', '.join(bare)}: 다른 화면은 이름과 번호를 함께 쓰면 읽기 쉬워요. 예: 방 상세(SCR-080)")

    # 흐름
    flows = sorted(docs.glob("*유저플로우*.md"))
    if flows and screens:
        text = flows[0].read_text(encoding="utf-8")
        for s in screens:
            if not re.search(r"-P\d+$", s.id) and s.id not in text:
                problems.append(f"{s.id}: 유저 플로우에 없는 화면이에요.")

    # 정책
    pols = sorted(p for p in docs.glob("*.md") if "정책" in p.name)
    if pols:
        defined = set(re.findall(r"^## (POL-\d+)", "\n".join(p.read_text(encoding="utf-8") for p in pols), re.M))
        used = {p for s in screens for d in s.descriptions for p in re.findall(r"POL-\d+", f"{d.policy} {d.text}")}
        for p in sorted(used - defined):
            problems.append(f"{p}: 화면에서 가리키는데 기능 명세 / 정책에 없어요.")
    return problems, notes
