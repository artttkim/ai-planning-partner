"""개발용 화면 명세(.yaml) 생성. 형식은 03_기능명세서.md 5.8을 따른다."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import paths
from .screens import load_screens

TYPE_MAP = {
    "상단바": "header", "하단탭바": "tabbar", "탭": "tabs", "입력창": "input.text", "검색창": "input.search",
    "선택상자": "input.select", "체크박스": "input.checkbox", "라디오": "input.radio", "토글": "input.toggle",
    "기본버튼": "button.primary", "보조버튼": "button.secondary", "텍스트링크": "link", "플로팅버튼": "button.fab",
    "제목": "text.title", "본문": "text.body", "오류문구": "text.error", "안내문구": "text.helper",
    "목록": "list", "카드": "card", "표": "table", "이미지": "image", "아이콘": "icon", "배지": "badge",
    "팝업": "dialog", "바텀시트": "bottom_sheet", "토스트": "toast", "로딩": "loading", "빈화면": "empty_state",
    "구분선": "divider", "행": "row", "묶음": "group", "아바타": "avatar",
}
POLICY_RE = re.compile(r"POL-\d+")


def build(task_dir: Path) -> list[Path]:
    task_dir = Path(task_dir)
    out_dir = paths.dev(task_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for s in load_screens(task_dir):
        policies = sorted({p for d in s.descriptions for p in POLICY_RE.findall(f"{d.policy} {d.text}")})
        by_marker = {str(d.no): d for d in s.descriptions}

        def convert(c):
            item = {"id": c.id, "type": TYPE_MAP.get(c.type.replace(" ", ""), "custom")}
            if c.label:
                item["label"] = c.label
            if c.items:
                item["items"] = c.items
            if c.selected is not None:
                item["selected"] = c.selected
            for key in ("left", "right"):
                if getattr(c, key):
                    item[f"actions_{key}"] = getattr(c, key)
            if c.changed:
                item["changed"] = True
            d = by_marker.get(str(c.marker)) if c.marker is not None else None
            if d:
                item["behavior"] = d.text
                if d.policy:
                    item["policy"] = d.policy
            if c.children:
                item["children"] = [convert(ch) for ch in c.children]
            return item

        components = [convert(c) for c in s.components]
        data = {
            "id": s.id,
            "name": s.name,
            "status": {"신규": "new", "변경": "changed", "참고": "reference"}[s.status],
            "agreement": "초안",
            "platform": s.platform,
            "path": s.path,
            "requirements": s.requirements,
            "policies": policies,
            "components": components,
            "descriptions": [
                {"no": d.no, "item": d.item, "text": d.text, **({"policy": d.policy} if d.policy else {})}
                for d in s.descriptions
            ],
        }
        if s.note:
            data["note"] = s.note
        out = out_dir / f"{s.id}.yaml"
        out.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        written.append(out)
    # 원본에서 지운 화면의 명세는 함께 지운다.
    for old in out_dir.glob("SCR-*.yaml"):
        if old not in written:
            old.unlink()
    return written
