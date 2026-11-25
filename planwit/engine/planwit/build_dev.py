"""개발 명세(개발명세.md) 생성. 개발자와 AI 코딩 도구가 읽는 한 파일이다.

- 화면마다 구성(요소 트리, YAML)과 요소별 동작, 정책, 이동할 화면을 담는다.
- 기획 문서(영향 분석, 플로우, 정책, 수용 기준, 개발 태스크)를 그대로 이어 붙인다.
- ID(SCR, POL, FR, AC, TASK)로 서로 이어진다. 원본을 고치고 다시 만든다.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import paths
from .screens import Screen, load_screens, task_title

TYPE_MAP = {
    "상단바": "header", "하단탭바": "tabbar", "탭": "tabs", "입력창": "input.text", "검색창": "input.search",
    "선택상자": "input.select", "체크박스": "input.checkbox", "라디오": "input.radio", "토글": "input.toggle",
    "기본버튼": "button.primary", "보조버튼": "button.secondary", "텍스트링크": "link", "플로팅버튼": "button.fab",
    "제목": "text.title", "본문": "text.body", "오류문구": "text.error", "안내문구": "text.helper",
    "목록": "list", "카드": "card", "표": "table", "이미지": "image", "아이콘": "icon", "배지": "badge",
    "팝업": "dialog", "바텀시트": "bottom_sheet", "토스트": "toast", "로딩": "loading", "빈화면": "empty_state",
    "구분선": "divider", "행": "row", "묶음": "group", "아바타": "avatar",
    "설정줄": "list.item.setting", "세그먼트": "segmented", "시간선택": "picker.time", "요일선택": "picker.weekday",
    "소제목": "text.section",
}
STATUS = {"신규": "new", "변경": "changed", "참고": "reference", "기준": "base"}
POLICY_RE = re.compile(r"POL-\d+")


def screen_spec(s: Screen, links: dict[str, str] | None = None) -> dict:
    """화면 하나의 개발 명세. 개발명세.md에 쓴다."""
    links = links or {}
    by_marker = {str(d.no): d for d in s.descriptions}

    def convert(c):
        item = {"id": c.id, "type": TYPE_MAP.get(c.type.replace(" ", ""), "custom")}
        if c.label:
            item["text"] = c.label
        if c.items:
            item["items"] = c.items
        if c.value:
            item["value"] = c.value
        if c.selected is not None:
            item["selected"] = c.selected
        for key in ("left", "right"):
            if getattr(c, key):
                item[f"actions_{key}"] = getattr(c, key)
        if c.changed:
            item["changed"] = True
        d = by_marker.get(str(c.marker)) if c.marker is not None else None
        if d:
            item["no"] = int(d.no) if str(d.no).isdigit() else d.no
            item["behavior"] = d.text
            if d.policy:
                item["policy"] = [p.strip() for p in d.policy.split(",") if p.strip()]
        if c.id in links:
            item["navigate"] = links[c.id]
        if c.children:
            item["children"] = [convert(ch) for ch in c.children]
        return item

    data = {
        "id": s.id,
        "name": s.name,
        "status": STATUS.get(s.status, s.status),
        "platform": s.platform,
        "path": s.path,
        "requirements": s.requirements,
        "policies": sorted({p for d in s.descriptions for p in POLICY_RE.findall(f"{d.policy} {d.text}")}),
        "components": [convert(c) for c in s.components],
    }
    if s.note:
        data["note"] = s.note
    return data


def figma_link(task_dir: Path) -> str:
    """과제요약의 '- 피그마: <주소>' 줄. 없으면 빈 문자열."""
    p = paths.summary(task_dir)
    if not p.is_file():
        return ""
    m = re.search(r"^- 피그마:\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
    return m[1] if m else ""


def _summary_text(task_dir: Path) -> str:
    p = paths.summary(task_dir)
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def handoff_version(task_dir: Path) -> str:
    """과제요약의 '- 전달 버전: v1.0 (YYYY.MM.DD)' 줄."""
    m = re.search(r"^- 전달 버전:\s*(.+)$", _summary_text(task_dir), re.M)
    return m[1].strip() if m else ""


def _history(task_dir: Path) -> list[str]:
    """과제요약의 변경 이력 표."""
    text = _summary_text(task_dir)
    m = re.search(r"^## 변경 이력\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return [l for l in m[1].strip().splitlines() if l.startswith("|")] if m else []


def to_yaml(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)


def _docs(task_dir: Path) -> list[Path]:
    """화면 설계를 뺀 단계 문서. 서비스 기준본은 정책.md."""
    if paths.is_service(task_dir):
        p = Path(task_dir) / "정책.md"
        return [p] if p.is_file() else []
    return sorted(p for p in paths.docs(task_dir).glob("*.md"))


def _demote(text: str) -> str:
    """이어 붙일 문서의 제목을 한 단계씩 낮춘다."""
    out = []
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        if not in_code and re.match(r"^#{1,5} ", line):
            line = "#" + line
        if line.strip() == "> 기본 작성":
            continue
        out.append(line)
    return "\n".join(out).strip()


def build(task_dir: Path) -> list[Path]:
    from .build_proto import _Nav, _links, links_with_nav

    task_dir = Path(task_dir)
    screens = load_screens(task_dir)
    by_id = {s.id: s for s in screens}
    nav = _Nav(screens)
    title = task_title(task_dir)
    figma = figma_link(task_dir)

    lines = [
        f"# {title} · 개발 명세" + (f" · {handoff_version(task_dir)}" if handoff_version(task_dir) else ""),
        "",
        "> 플랜윗이 기획 원본에서 만든 파일이다. 직접 고치지 말고 기획 원본을 고친 뒤 다시 만든다.",
        "> 화면을 눌러 보려면 같은 폴더의 기획안.html을 연다.",
        "",
        "## 읽는 법",
        "",
        "- ID: `SCR` 화면, `POL` 정책, `FR` 기능, `AC` 수용 기준, `TASK` 개발 태스크. 화면과 정책 번호는 서비스 전체에서 하나뿐이다.",
        "- 화면 구성은 위에서 아래 순서의 요소 트리다. `behavior`는 그 요소의 동작과 조건, `policy`는 따를 정책, `navigate`는 누르면 갈 화면이다.",
        "- `changed: true`는 이번 과제에서 바뀌는 요소다.",
        "- **이 명세는 동작 기준이다. 모양(색, 글꼴, 간격, 아이콘)은 피그마 디자인을 따른다.** 기획안의 화면 모양은 초안이다."
        + (f" 피그마: {figma}" if figma else ""),
        "",
        "## 화면 목록",
        "",
        "| 화면 | 이름 | 구분 | 경로 | 기능 |",
        "|---|---|---|---|---|",
    ]
    for s in screens:
        lines.append(f"| {s.id} | {s.name} | {s.status} | {s.path or '-'} | {', '.join(s.requirements) or '-'} |")
    lines += ["", "## 화면별 명세", ""]
    for s in screens:
        spec = screen_spec(s, links_with_nav(s, by_id, nav))
        lines += [f"### {s.id} {s.name}", "", "```yaml", to_yaml(spec).rstrip(), "```", ""]
        if s.descriptions:
            lines += ["| No | 항목 | 설명 | 정책 |", "|---|---|---|---|"]
            lines += [f"| {d.no} | {d.item} | {d.text} | {d.policy} |" for d in s.descriptions]
            lines.append("")
    for doc in _docs(task_dir):
        lines += [_demote(doc.read_text(encoding="utf-8")), ""]
    history = _history(task_dir)
    if history:
        lines += ["## 변경 이력", "", *history, ""]

    out = paths.output_of(task_dir) / paths.DEV_SPEC
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    old = paths.dev(task_dir)  # 예전: 화면마다 yaml
    if old.is_dir():
        import shutil
        shutil.rmtree(old, ignore_errors=True)
    return [out]
