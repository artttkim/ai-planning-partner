"""작업 공간과 과제 폴더 구조. 폴더와 파일 이름은 여기에서만 정한다.

<작업 공간>/
├─ 회사/                  모든 서비스 공통 규칙 (규칙.md)
└─ <서비스>/              서비스마다 하나 (예: 타이미C)
   ├─ 기준본/             끝난 과제를 합친 전체 화면과 정책
   │  ├─ 화면/            SCR-*.md (서비스 안에서 하나뿐인 화면 번호)
   │  ├─ 정책.md
   │  ├─ 화면목록.md      기준본과 모든 과제의 화면 번호 (엔진이 만든다)
   │  └─ 기획안.html      서비스 전체 기획안 (엔진이 만든다)
   ├─ 디자인/             디자인.css, 화면지도/(기존 화면 캡처)
   ├─ 서비스지식/         서비스지식.md(서비스 맥락), 자료색인.md(회사 자료 폴더 색인)
   └─ 과제/<YYYY-MM-DD>_<과제명>/
   ├─ 00_과제요약.md  요약, 진행 단계, 결정 기록
   ├─ 01_검수함.md
   ├─ 1_입력자료/     기획자가 준 자료
   ├─ 2_기획문서/     단계별 원본 (NN_<단계>.md, NN_화면설계/)
   ├─ 3_결과물/       기획안.html(프로토타입 + 설명 + 의견), 개발명세.md(요청하거나 개발 전달 때). 화면 설계서 .pptx는 요청할 때만
   └─ .planwit/       생성 기록, 캡처, 뽑은 텍스트
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

SUMMARY = "00_과제요약.md"
INBOX = "01_검수함.md"
DECISIONS = "02_결정기록.md"  # 예전 구조. 지금은 과제요약의 "결정 기록" 장
INPUT = "1_입력자료"
DOCS = "2_기획문서"
OUTPUT = "3_결과물"
DEV = f"{OUTPUT}/개발용"  # 예전 구조. 지금은 개발명세.md 한 파일
PLAN = "기획안.html"
DEV_SPEC = "개발명세.md"
SERVICE = "기준본"  # 서비스 폴더 안의 기준본 폴더
OLD_SERVICE = "서비스"  # 예전: 작업 공간 맨 위의 기준본
TASKS = "과제"
DESIGN = "디자인"
KNOWLEDGE = "서비스지식"  # 서비스 맥락(서비스지식.md)과 자료 색인
COMPANY = "회사"

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
    (r"(?<![\w/])02_결정기록\.md", f"{SUMMARY}의 결정 기록"),
    (r"`?3_결과물/개발용/\*?\.?y?a?m?l?`?", f"`{OUTPUT}/{DEV_SPEC}`"),
    (r"(?<![\w/])입력/", f"{INPUT}/"),
    (r"(?<![\w/])원본/", f"{DOCS}/"),
    (r"(?<![\w/])회사양식/", f"{OUTPUT}/"),
]


WORKSPACE_MARK = ".planwit-workspace"


def is_workspace(root: Path) -> bool:
    """플랜윗 작업 공간인지. 아니면 엔진은 그 폴더에서 아무것도 읽거나 쓰지 않는다.

    표시 파일이 있거나, 예전 설정으로 만든 작업 공간(과제/, 회사/ 폴더와 플랜윗 CLAUDE.md)이면 작업 공간이다.
    """
    root = Path(root)
    if (root / WORKSPACE_MARK).is_file():
        return True
    claude = root / "CLAUDE.md"
    if not ((root / "회사").is_dir() and claude.is_file()):
        return False
    try:
        text = claude.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return text.startswith("# 플랜윗 작업 공간") or "\n## 플랜윗" in text


def summary(task_dir: Path) -> Path:
    return Path(task_dir) / SUMMARY


def docs(task_dir: Path) -> Path:
    return Path(task_dir) / DOCS


def output(task_dir: Path) -> Path:
    return Path(task_dir) / OUTPUT


def dev(task_dir: Path) -> Path:
    return Path(task_dir) / DEV


def plan(task_dir: Path) -> Path:
    return output(task_dir) / PLAN


def dev_spec(task_dir: Path) -> Path:
    return output(task_dir) / DEV_SPEC


def service_root_of(path: Path) -> Path:
    """과제 폴더나 기준본 폴더가 속한 서비스 폴더. 예전 구조(작업 공간/과제/...)면 작업 공간."""
    p = Path(path)
    if p.name in (SERVICE, OLD_SERVICE) and not (p / TASKS).is_dir():
        return p.parent
    if p.parent.name == TASKS:
        return p.parent.parent
    return p


def workspace_of(path: Path) -> Path:
    """위로 올라가며 찾은 플랜윗 작업 공간."""
    p = Path(path).resolve()
    for d in (p, *p.parents):
        if is_workspace(d):
            return d
    return service_root_of(p).parent


def service(service_root: Path) -> Path:
    """서비스의 기준본 폴더."""
    return Path(service_root) / SERVICE


def services(workspace: Path) -> list[Path]:
    ws = Path(workspace)
    if not ws.is_dir():
        return []
    return sorted(d for d in ws.iterdir() if d.is_dir() and not d.name.startswith(".") and d.name != COMPANY
                  and any((d / x).is_dir() for x in (TASKS, SERVICE, DESIGN)))


def all_tasks(workspace: Path) -> list[Path]:
    """작업 공간의 모든 과제. 서비스 폴더 아래 과제와 예전 구조(작업 공간/과제/)의 과제."""
    ws = Path(workspace)
    out = []
    for root in [*services(ws), ws]:
        t = root / TASKS
        if t.is_dir():
            out += sorted(p for p in t.glob("*/") if p.is_dir())
    return out


def design_css(path: Path) -> Path | None:
    """서비스 디자인 값. 서비스의 디자인/디자인.css, 없으면 회사/디자인.css."""
    for c in (service_root_of(path) / DESIGN / "디자인.css", workspace_of(path) / COMPANY / "디자인.css"):
        if c.is_file():
            return c
    return None


def migrate_workspace(workspace: Path, service_name: str) -> list[str]:
    """예전 구조(작업 공간/과제/, 작업 공간/서비스/)를 서비스 폴더 아래로 옮긴다."""
    ws = Path(workspace)
    svc = ws / service_name
    moved = []
    for src, dst in ((ws / TASKS, svc / TASKS), (ws / OLD_SERVICE, svc / SERVICE),
                     (ws / COMPANY / "디자인.css", svc / DESIGN / "디자인.css"),
                     (ws / COMPANY / "화면지도", svc / DESIGN / "화면지도")):
        if not src.exists() or src == dst:
            continue
        if src.is_dir() and not any(src.iterdir()):
            src.rmdir()
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and src.is_dir():
            for f in list(src.iterdir()):
                shutil.move(str(f), dst / f.name)
            src.rmdir()
        else:
            shutil.move(str(src), dst)
        moved.append(f"{src.relative_to(ws).as_posix()} → {dst.relative_to(ws).as_posix()}")
    return moved


def is_service(folder: Path) -> bool:
    return Path(folder).name == SERVICE


def output_of(folder: Path) -> Path:
    """결과물을 둘 곳. 서비스 기준본은 서비스 폴더 바로 아래."""
    return Path(folder) if is_service(folder) else output(folder)


def _fold_decisions(task_dir: Path) -> bool:
    """예전 02_결정기록.md의 표를 과제요약의 "결정 기록" 장으로 옮긴다."""
    old = task_dir / DECISIONS
    if not old.is_file():
        return False
    rows = [l for l in old.read_text(encoding="utf-8").splitlines() if l.startswith("| ") and not l.startswith("| 날짜")]
    s = summary(task_dir)
    text = s.read_text(encoding="utf-8") if s.is_file() else ""
    if "## 결정 기록" not in text:
        block = "\n## 결정 기록\n\n| 날짜 | 결정 | 이유 | 출처 |\n|---|---|---|---|\n"
        block += "".join(r + "\n" for r in rows if not r.startswith("|---"))
        if "## 변경 이력" in text:
            text = text.replace("## 변경 이력", block.lstrip("\n") + "\n## 변경 이력", 1)
        else:
            text = text.rstrip("\n") + "\n" + block
        s.write_text(text, encoding="utf-8")
    old.unlink()
    return True


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
    # 지금 구조로 줄이기: 결정 기록은 과제요약 안으로, 화면별 개발용 명세와 예전 프로토타입은 지운다(다시 만든다)
    if _fold_decisions(task_dir):
        moved.append(f"{DECISIONS} → {SUMMARY}의 결정 기록")
    for old, label in ((task_dir / DEV, "개발용/"), (output(task_dir) / "프로토타입.html", "프로토타입.html")):
        if old.exists():
            try:
                shutil.rmtree(old) if old.is_dir() else old.unlink()
                moved.append(f"{OUTPUT}/{label} 지움 ({PLAN}, {DEV_SPEC}로 바뀜)")
            except OSError:
                moved.append(f"{OUTPUT}/{label}: 열려 있는 파일이 있어 지우지 못함")
    if moved:
        mp = task_dir / ".planwit" / "manifest.json"
        if mp.exists():
            data = json.loads(mp.read_text(encoding="utf-8"))
            data["files"] = {k.replace("회사양식/", f"{OUTPUT}/"): v for k, v in data.get("files", {}).items()}
            mp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _rewrite_refs(task_dir)
    return moved
