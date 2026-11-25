"""회사·서비스 자료 폴더 색인. 내용은 읽지 않고 파일 이름, 경로, 날짜, 크기만 모은다.

토큰을 아끼기 위해서다. 플랜윗은 이 색인을 보고 읽을 파일만 골라 읽는다.
- 분류: 경로와 파일 이름의 낱말로 정한다 (기획서, 정책, 지표, 사용자 등)
- 판 묶기: "v2", "최종", "수정", 날짜처럼 판만 다른 파일은 하나로 묶고 가장 최근 것을 대표로 둔다
- 바뀐 것: 지난 색인과 비교해 새로 생기거나 바뀐 파일을 따로 보여 준다
폴더는 읽기만 한다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

from . import paths

INDEX_JSON = "자료색인.json"
INDEX_MD = "자료색인.md"
MAX_FILES = 30000
TOP_PER_CATEGORY = 12

DOC_EXT = {".md", ".txt", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv", ".pdf", ".hwp", ".hwpx",
           ".key", ".pages", ".numbers"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".svn", "$RECYCLE.BIN", "System Volume Information"}
SKIP_FILES = re.compile(r"^(~\$|\.~|desktop\.ini$|thumbs\.db$|\.ds_store$)", re.I)

# (분류, 낱말). 위에 있을수록 먼저 맞춘다. 낱말은 경로 전체(폴더 이름 포함)에서 찾는다.
CATEGORIES = [
    ("서비스 소개", r"서비스\s*소개|회사\s*소개|서비스\s*정의|서비스\s*개요|\bIR\b|비전|전략|사업\s*계획|overview|about|브랜드\s*스토리"),
    ("기능 지도", r"\bIA\b|정보\s*구조|메뉴\s*구조|사이트\s*맵|sitemap|기능\s*(목록|정의|리스트)|화면\s*(목록|리스트)|feature\s*list"),
    ("기획서", r"PRD|기획서|기획안|요구\s*사항|스토리\s*보드|화면\s*설계|\bSB\b|spec|명세|상세\s*기획"),
    ("정책", r"정책|약관|운영\s*기준|policy|terms|가이드라인"),
    ("지표", r"지표|KPI|대시보드|dashboard|리포트|report|분석|통계|리텐션|retention|매출|데이터|metric|OKR"),
    ("사용자", r"사용자|페르소나|persona|인터뷰|interview|설문|survey|리서치|research|VOC|리뷰|review|CS|문의|고객"),
    ("디자인", r"디자인|design|UI|UX|컴포넌트|component|스타일\s*가이드|브랜드\s*가이드|figma|피그마|와이어"),
    ("회의록", r"회의|미팅|meeting|회고|retro|킥오프|kickoff"),
    ("출시", r"릴리[즈스]|release|출시|배포|업데이트|패치\s*노트|changelog|버전\s*기록"),
    ("QA", r"\bQA\b|\bTC\b|테스트|test\s*case|결함|버그"),
]
_CAT_RE = [(name, re.compile(pat, re.I)) for name, pat in CATEGORIES]
_VERSION_RE = re.compile(
    r"([_\-\s\(\[]*(v|ver|rev)\.?\s*\d+([._]\d+)*[\)\]]?)|([_\-\s]*(최종|최종본|최최종|수정본?|final|draft|초안|사본|copy|복사본))"
    r"|([_\s]*\(\d{1,2}\)$)|(-\d{1,2}$)|([_\-\s]*(19|20)?\d{2}[.\-_]?\d{2}[.\-_]?\d{2})", re.I)


def _base(stem: str) -> str:
    """판 표시를 뺀 이름. 같은 문서의 여러 판을 묶는 열쇠다."""
    s = stem
    for _ in range(4):
        new = _VERSION_RE.sub("", s).strip(" _-.")
        if new == s:
            break
        s = new
    return re.sub(r"\s+", " ", s).lower() or stem.lower()


def _category(rel: str, ext: str) -> str:
    for name, rx in _CAT_RE:
        if rx.search(rel):
            return name
    if ext in IMAGE_EXT:
        return "화면 캡처"
    return "기타"


def scan(root: Path) -> list[dict]:
    """폴더를 돌며 문서와 그림 파일의 정보를 모은다. 내용은 읽지 않는다."""
    root = Path(root)
    out: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if SKIP_FILES.search(name):
                continue
            ext = Path(name).suffix.lower()
            if ext not in DOC_EXT and ext not in IMAGE_EXT:
                continue
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except OSError:
                continue
            rel = p.relative_to(root).as_posix()
            out.append({
                "path": rel,
                "ext": ext,
                "size": st.st_size,
                "mtime": int(st.st_mtime),
                "category": _category(rel, ext),
                "group": f"{Path(rel).parent.as_posix()}/{_base(Path(name).stem)}{ext}",
            })
            if len(out) >= MAX_FILES:
                return out
    return out


def _groups(files: list[dict]) -> list[dict]:
    """판이 여럿인 파일은 가장 최근 것을 대표로 묶는다."""
    by: dict[str, list[dict]] = {}
    for f in files:
        by.setdefault(f["group"], []).append(f)
    reps = []
    for items in by.values():
        items.sort(key=lambda f: f["mtime"], reverse=True)
        rep = dict(items[0])
        rep["versions"] = len(items)
        rep["older"] = [f["path"] for f in items[1:]]
        reps.append(rep)
    return reps


def _score(f: dict) -> float:
    """읽을 가치 점수. 문서가 그림보다, 최근 것이, 판이 많은(자주 고친) 것이, 얕은 위치가 높다."""
    age_days = max(0.0, (dt.datetime.now().timestamp() - f["mtime"]) / 86400)
    s = 3.0 if f["ext"] in DOC_EXT else 0.5
    s += max(0.0, 2.0 - age_days / 180)          # 1년 안쪽일수록 높게
    s += min(f.get("versions", 1) - 1, 4) * 0.4    # 여러 번 고친 문서
    s -= f["path"].count("/") * 0.15               # 깊이 묻힌 파일은 조금 낮게
    return round(s, 2)


def knowledge_dir(service_root: Path) -> Path:
    return Path(service_root) / paths.KNOWLEDGE


def build(source: Path, service_root: Path) -> tuple[Path, dict]:
    """색인을 만들어 <서비스>/서비스지식/자료색인.md 와 .planwit/자료색인.json 에 쓴다. (md 경로, 요약)을 돌려준다."""
    source = Path(source).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"폴더가 없어요: {source}")
    service_root = Path(service_root)
    kdir = knowledge_dir(service_root)
    kdir.mkdir(parents=True, exist_ok=True)
    jpath = service_root / ".planwit" / INDEX_JSON
    old = {}
    if jpath.is_file():
        try:
            prev = json.loads(jpath.read_text(encoding="utf-8"))
            for src in prev.get("sources", []):
                if src.get("root") == str(source):
                    old = {f["path"]: f["mtime"] for f in src.get("files", [])}
        except (ValueError, OSError):
            old = {}

    files = scan(source)
    reps = _groups(files)
    for r in reps:
        r["score"] = _score(r)
    changed = [r for r in reps if r["path"] not in old or old[r["path"]] != r["mtime"]] if old else []

    data = {"sources": []}
    if jpath.is_file():
        try:
            data = json.loads(jpath.read_text(encoding="utf-8"))
        except ValueError:
            data = {"sources": []}
    data["sources"] = [s for s in data.get("sources", []) if s.get("root") != str(source)]
    data["sources"].append({"root": str(source), "indexed": dt.datetime.now().isoformat(timespec="minutes"),
                            "files": reps})
    jpath.parent.mkdir(parents=True, exist_ok=True)
    jpath.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    md = kdir / INDEX_MD
    md.write_text(_markdown(data, changed if old else None), encoding="utf-8")
    cats: dict[str, int] = {}
    for r in reps:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    return md, {"files": len(files), "documents": len(reps), "changed": len(changed), "categories": cats}


def _day(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y.%m.%d")


def _size(n: int) -> str:
    return f"{n / 1048576:.1f}MB" if n >= 1048576 else f"{max(1, n // 1024)}KB"


def _markdown(data: dict, changed: list[dict] | None) -> str:
    order = [c for c, _ in CATEGORIES] + ["화면 캡처", "기타"]
    lines = ["# 자료 색인", "",
             "> 엔진이 파일 이름만 보고 만든 목록이다. 내용은 읽지 않았다. 플랜윗은 여기서 읽을 파일을 골라 읽고, "
             "읽은 파일은 서비스지식.md의 출처에 적는다. 폴더는 읽기만 한다.", ""]
    for src in data["sources"]:
        reps = src["files"]
        lines += [f"## {src['root']}", "", f"- 색인한 때: {src['indexed']}", ""]
        for cat in order:
            items = sorted((r for r in reps if r["category"] == cat), key=lambda r: -r["score"])
            if not items:
                continue
            lines += [f"### {cat} ({len(items)})", "", "| 파일 | 고친 날 | 크기 | 판 |", "|---|---|---|---|"]
            for r in items[:TOP_PER_CATEGORY]:
                lines.append(f"| {r['path']} | {_day(r['mtime'])} | {_size(r['size'])} | {r.get('versions', 1)} |")
            if len(items) > TOP_PER_CATEGORY:
                lines.append(f"| 외 {len(items) - TOP_PER_CATEGORY}개 (엔진 find-docs로 찾기) | | | |")
            lines.append("")
    if changed is not None:
        lines += ["## 지난 색인 뒤 새로 생기거나 바뀐 파일", ""]
        if changed:
            lines += [f"- {r['path']} ({_day(r['mtime'])}, {r['category']})" for r in
                      sorted(changed, key=lambda r: -r["mtime"])[:50]]
        else:
            lines.append("- 없음")
        lines.append("")
    return "\n".join(lines)


def find(service_root: Path, words: list[str], limit: int = 30) -> list[dict]:
    """색인에서 낱말이 경로에 들어간 파일을 찾는다 (낱말이 많이 맞을수록, 점수가 높을수록 앞)."""
    jpath = Path(service_root) / ".planwit" / INDEX_JSON
    if not jpath.is_file():
        raise FileNotFoundError("자료 색인이 없어요. 먼저 엔진 index로 색인을 만드세요.")
    data = json.loads(jpath.read_text(encoding="utf-8"))
    rx = [re.compile(re.escape(w), re.I) for w in words if w.strip()]
    hits = []
    for src in data.get("sources", []):
        for r in src.get("files", []):
            n = sum(1 for x in rx if x.search(r["path"]))
            if n:
                hits.append((n, r["score"], src["root"], r))
    hits.sort(key=lambda h: (-h[0], -h[1]))
    return [dict(r, root=root, full=str(Path(root) / r["path"])) for _, _, root, r in hits[:limit]]
