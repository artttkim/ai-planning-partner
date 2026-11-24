"""화면 설계 원본(마크다운) 읽기. 형식은 03_기능명세서.md 5.3을 따른다."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import paths

TITLE_RE = re.compile(r"^#\s+(?P<id>\S+)\s+(?P<name>.+?)\s*·\s*(?P<status>신규|변경|참고|기준)\s*$")
META_RE = re.compile(r"^-\s*(?P<key>[^:]+):\s*(?P<value>.*)$")
YAML_RE = re.compile(r"```ya?ml\s*\n(?P<body>.*?)```", re.S)


@dataclass
class Component:
    id: str
    type: str
    label: str = ""
    changed: bool = False
    marker: int | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    children: list["Component"] = field(default_factory=list)
    items: list[str] = field(default_factory=list)   # 탭, 하단탭바, 라디오, 체크박스의 항목
    selected: int | None = None                       # items 중 선택된 항목 순서(0부터)
    left: list[str] = field(default_factory=list)    # 상단바 왼쪽 아이콘 (예: 뒤로)
    right: list[str] = field(default_factory=list)   # 상단바 오른쪽 아이콘 (예: 더보기)
    align: str = ""                                   # 글자 정렬: left, center, right
    size: str = ""                                    # 버튼 크기: small

    def walk(self):
        yield self
        for ch in self.children:
            yield from ch.walk()


@dataclass
class DescRow:
    no: str
    item: str
    text: str
    policy: str = ""


@dataclass
class Screen:
    id: str
    name: str
    status: str
    path: str = ""
    requirements: list[str] = field(default_factory=list)
    platform: str = "앱"
    frame: str = "mobile"
    components: list[Component] = field(default_factory=list)
    descriptions: list[DescRow] = field(default_factory=list)
    note: str = ""
    base: str = ""          # 서비스 기준본에서 가져온 화면이면 그때 기준본의 지문 (합칠 때 충돌 검사)
    source: Path | None = None


def _sections(text: str) -> dict[str, str]:
    """'## 제목' 단위로 본문을 나눈다. 코드 블록 안의 '##'는 무시한다."""
    sections: dict[str, list[str]] = {"": []}
    current = ""
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        if not in_code and line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
            continue
        sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def _table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        rows.append(cells)
    return rows[1:] if rows else []  # 머리글 제외


def parse_screen(path: Path) -> Screen:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = next((l for l in lines if l.startswith("# ")), "")
    m = TITLE_RE.match(title)
    if not m:
        raise ValueError(f"{path.name}: 첫 줄 형식이 '# <화면 ID> <화면명> · <신규|변경|참고>'가 아니에요.")
    screen = Screen(id=m["id"], name=m["name"], status=m["status"], source=path)

    sec = _sections(text)
    for line in sec.get("", "").splitlines():
        mm = META_RE.match(line.strip())
        if not mm:
            continue
        key, value = mm["key"].strip(), mm["value"].strip()
        if key == "경로":
            screen.path = value
        elif key == "관련 기능":
            screen.requirements = [v.strip() for v in value.split(",") if v.strip()]
        elif key == "플랫폼":
            screen.platform = value
        elif key == "기준본":
            screen.base = value

    ym = YAML_RE.search(sec.get("구성", ""))
    if ym:
        data = yaml.safe_load(ym["body"]) or {}
        screen.frame = data.get("frame", "web" if screen.platform == "웹" else "mobile")
        screen.components = [_component(c, f"c{i + 1}") for i, c in enumerate(data.get("components", []) or [])]

    for cells in _table_rows(sec.get("설명", "")):
        cells += [""] * (4 - len(cells))
        screen.descriptions.append(DescRow(no=cells[0], item=cells[1], text=cells[2], policy=cells[3]))

    screen.note = sec.get("비고", "").strip()
    return screen


def _list(v) -> list[str]:
    if v is None:
        return []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def _component(c: dict, default_id: str) -> Component:
    cid = str(c.get("id", default_id))
    return Component(
        id=cid,
        type=str(c.get("type", "기타")),
        label=str(c.get("label", "") or ""),
        changed=bool(c.get("changed", False)),
        marker=c.get("marker"),
        x=c.get("x"), y=c.get("y"), w=c.get("w"), h=c.get("h"),
        children=[_component(ch, f"{cid}-{i + 1}") for i, ch in enumerate(c.get("children", []) or [])],
        items=_list(c.get("items")),
        selected=c.get("selected"),
        left=_list(c.get("left")),
        right=_list(c.get("right")),
        align=str(c.get("align", "") or ""),
        size=str(c.get("size", "") or ""),
    )


def all_components(screen: "Screen") -> list[Component]:
    return [c for top in screen.components for c in top.walk()]


def _id_key(screen_id: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", screen_id)]


def find_screen_dir(task_dir: Path) -> Path:
    if paths.is_service(task_dir):
        return Path(task_dir) / "화면"
    src = paths.docs(task_dir)
    candidates = sorted(p for p in src.glob("*화면설계*") if p.is_dir())
    if not candidates:
        raise FileNotFoundError(f"{src}에 화면설계 폴더가 없어요.")
    return candidates[-1]


def load_screens(task_dir: Path) -> list[Screen]:
    folder = find_screen_dir(task_dir)
    if not folder.is_dir():
        return []
    screens = [parse_screen(p) for p in folder.glob("*.md") if not p.name.startswith("_")]
    return sorted(screens, key=lambda s: _id_key(s.id))


def task_title(task_dir: Path) -> str:
    """00_과제요약.md의 첫 제목, 없으면 폴더 이름에서 날짜를 뺀 것."""
    if paths.is_service(task_dir):
        return f"{paths.service_root_of(task_dir).name} 기준본"
    summary = paths.summary(task_dir)
    if summary.exists():
        for line in summary.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].split("·")[0].strip()
    name = task_dir.name
    return re.sub(r"^\d{4}-\d{2}-\d{2}_", "", name).replace("_", " ")
