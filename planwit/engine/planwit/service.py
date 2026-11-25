"""서비스 기준본. 과제를 나눠 작업하고, 끝난 과제를 서비스 전체 화면과 정책에 합친다.

이 모듈의 함수가 받는 workspace는 서비스 폴더(<작업 공간>/<서비스>/)다. 번호와 기준본은 서비스마다 따로다.

- 화면 번호(SCR)와 정책 번호(POL)는 서비스 전체에서 하나뿐이다. 새 번호는 next_id로 받는다.
- 기준본에 있는 화면이나 정책을 고치는 과제는 base로 가져온다. 가져올 때 기준본의 지문을 함께 적는다.
- merge는 과제의 화면과 정책을 기준본에 합친다. 과제를 시작한 뒤 다른 과제가 같은 화면을 먼저 합쳤으면
  지문이 달라 충돌로 알리고, 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import shutil
from pathlib import Path

from . import paths
from .screens import TITLE_RE, find_screen_dir

POL_HEAD_RE = re.compile(r"^## (POL-\d+)\b.*$", re.M)
BASE_LINE_RE = re.compile(r"^- 기준본: .*\n?", re.M)
MERGED_LINE_RE = re.compile(r"^- 반영: .*\n?", re.M)
SCREEN_FILE_RE = re.compile(r"^SCR-\d+(?:-P\d+)?\.md$")


# ---------- 읽기 ----------

def _norm_text(text: str) -> str:
    text = BASE_LINE_RE.sub("", text)
    text = MERGED_LINE_RE.sub("", text)
    text = re.sub(r"·\s*(신규|변경|참고|기준)\s*$", "", text, count=1, flags=re.M)
    text = re.sub(r",?\s*changed: true", "", text)
    return "\n".join(l.rstrip() for l in text.strip().splitlines() if l.strip())


def fingerprint(text: str) -> str:
    return hashlib.sha1(_norm_text(text).encode("utf-8")).hexdigest()[:10]


def _tasks(workspace: Path) -> list[Path]:
    root = Path(workspace) / "과제"
    return sorted(p for p in root.glob("*/") if p.is_dir()) if root.is_dir() else []


def _task_screen_files(task: Path) -> list[Path]:
    try:
        folder = find_screen_dir(task)
    except FileNotFoundError:
        return []
    return sorted(p for p in folder.glob("*.md") if SCREEN_FILE_RE.match(p.name))


def _policy_files(task: Path) -> list[Path]:
    return sorted(p for p in paths.docs(task).glob("*.md") if "정책" in p.name)


def policy_sections(text: str) -> dict[str, str]:
    """'## POL-xxx' 장마다 내용. 다음 '## ' 장 앞까지."""
    out = {}
    heads = list(re.finditer(r"^## .*$", text, re.M))
    for i, h in enumerate(heads):
        m = POL_HEAD_RE.match(h.group(0))
        if not m:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out[m[1]] = text[h.start():end].rstrip() + "\n"
    return out


def _title(path: Path) -> tuple[str, str, str]:
    first = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else ""
    m = TITLE_RE.match(first)
    return (m["id"], m["name"], m["status"]) if m else (path.stem, "", "")


def inventory(workspace: Path) -> dict:
    """서비스와 모든 과제의 화면, 정책 번호. {'SCR': {id: [(어디, 이름, 구분)]}, 'POL': {...}}"""
    workspace = Path(workspace)
    inv = {"SCR": {}, "POL": {}}
    svc = paths.service(workspace)
    for p in sorted((svc / "화면").glob("SCR-*.md")) if (svc / "화면").is_dir() else []:
        sid, name, status = _title(p)
        inv["SCR"].setdefault(sid, []).append((paths.SERVICE, name, "기준"))
    pol = svc / "정책.md"
    if pol.is_file():
        for pid, sec in policy_sections(pol.read_text(encoding="utf-8")).items():
            inv["POL"].setdefault(pid, []).append((paths.SERVICE, sec.splitlines()[0][3:].strip(), "기준"))
    for task in _tasks(workspace):
        for p in _task_screen_files(task):
            sid, name, status = _title(p)
            inv["SCR"].setdefault(sid, []).append((task.name, name, status))
        for f in _policy_files(task):
            for pid, sec in policy_sections(f.read_text(encoding="utf-8")).items():
                kind = "변경" if BASE_LINE_RE.search(sec) else "신규"
                inv["POL"].setdefault(pid, []).append((task.name, sec.splitlines()[0][3:].strip(), kind))
    return inv


def next_id(workspace: Path, kind: str = "SCR") -> str:
    """서비스와 모든 과제에서 아직 쓰지 않은 다음 번호. 화면은 10 단위, 정책은 1 단위."""
    nums = [int(re.match(rf"{kind}-(\d+)", i)[1]) for i in inventory(workspace)[kind]]
    top = max(nums, default=0)
    if kind == "SCR":
        return f"SCR-{(top // 10 + 1) * 10:03d}"
    return f"POL-{top + 1:03d}"


# ---------- 기준본에서 가져오기 ----------

def base(task_dir: Path, item_id: str) -> Path:
    """기준본의 화면이나 정책을 과제로 가져온다. 기준본 지문을 적어 둔다."""
    task_dir = Path(task_dir)
    svc = paths.service(paths.service_root_of(task_dir))
    if item_id.startswith("SCR-"):
        src = svc / "화면" / f"{item_id}.md"
        if not src.is_file():
            raise FileNotFoundError(f"기준본에 {item_id} 화면이 없어요.")
        text = src.read_text(encoding="utf-8")
        dst = find_screen_dir(task_dir) / f"{item_id}.md"
        if dst.exists():
            raise FileExistsError(f"과제에 이미 {item_id} 화면이 있어요.")
        body = MERGED_LINE_RE.sub("", text)
        body = re.sub(r"·\s*기준\s*$", "· 변경", body, count=1, flags=re.M)
        lines = body.splitlines()
        insert_at = next((i + 1 for i, l in enumerate(lines) if l.startswith("- 플랫폼:")), 1)
        lines.insert(insert_at, f"- 기준본: {fingerprint(text)}")
        dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return dst
    if item_id.startswith("POL-"):
        pol = svc / "정책.md"
        sections = policy_sections(pol.read_text(encoding="utf-8")) if pol.is_file() else {}
        if item_id not in sections:
            raise FileNotFoundError(f"기준본에 {item_id} 정책이 없어요.")
        files = _policy_files(task_dir)
        if not files:
            raise FileNotFoundError("과제에 기능 명세 / 정책 문서가 없어요.")
        sec = MERGED_LINE_RE.sub("", sections[item_id])
        head, _, rest = sec.partition("\n")
        sec = f"{head}\n\n- 기준본: {fingerprint(sections[item_id])}{rest if rest.startswith(chr(10)) else chr(10) + rest}"
        f = files[0]
        f.write_text(f.read_text(encoding="utf-8").rstrip() + "\n\n" + sec.rstrip() + "\n", encoding="utf-8")
        return f
    raise ValueError("화면(SCR-)이나 정책(POL-) 번호를 주세요.")


# ---------- 합치기 ----------

def _to_base_screen(text: str, task_name: str) -> str:
    text = BASE_LINE_RE.sub("", MERGED_LINE_RE.sub("", text))
    text = re.sub(r"·\s*(신규|변경|기준)\s*$", "· 기준", text, count=1, flags=re.M)
    text = re.sub(r",\s*changed: true", "", text)
    text = re.sub(r"^\s*changed: true\n", "", text, flags=re.M)
    lines = text.splitlines()
    insert_at = next((i + 1 for i, l in enumerate(lines) if l.startswith("- 플랫폼:")), 1)
    lines.insert(insert_at, f"- 반영: {task_name} ({dt.date.today():%Y.%m.%d})")
    return "\n".join(lines).rstrip() + "\n"


def _to_base_policy(sec: str, task_name: str) -> str:
    sec = BASE_LINE_RE.sub("", MERGED_LINE_RE.sub("", sec))
    head, _, rest = sec.partition("\n")
    return f"{head}\n\n- 반영: {task_name} ({dt.date.today():%Y.%m.%d})\n{rest.lstrip(chr(10))}".rstrip() + "\n"


def _keep_captures(task_dir: Path, service_root: Path):
    """과제 화면이 쓰는 캡처가 서비스 화면지도에 없으면 복사한다. 합친 뒤에도 기준본 화면이 캡처를 찾게 하기 위해서다."""
    from .screens import load_screens, capture_file
    maps = Path(service_root) / paths.DESIGN / "화면지도"
    try:
        screens = load_screens(task_dir)
    except (FileNotFoundError, ValueError):
        return
    for s in screens:
        f = capture_file(s)
        if f is None or s.status == "참고":
            continue
        try:
            f.relative_to(maps)
            continue
        except ValueError:
            pass
        dst = maps / Path(s.capture).name
        if not dst.exists():
            maps.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)


def merge(task_dir: Path, dry_run: bool = False) -> tuple[list[str], list[str]]:
    """과제를 기준본에 합친다. (한 일, 충돌) 목록을 돌려준다. 충돌이 하나라도 있으면 아무것도 쓰지 않는다."""
    task_dir = Path(task_dir)
    workspace = paths.service_root_of(task_dir)  # 이 모듈에서 workspace는 서비스 폴더다
    svc = paths.service(workspace)
    done, conflicts, writes = [], [], []

    for p in _task_screen_files(task_dir):
        text = p.read_text(encoding="utf-8")
        sid, name, status = _title(p)
        if status == "참고":
            continue
        target = svc / "화면" / p.name
        m = re.search(r"^- 기준본: (\S+)", text, re.M)
        if target.is_file():
            current = target.read_text(encoding="utf-8")
            if _norm_text(current) == _norm_text(text):
                continue
            if not m:
                conflicts.append(f"{sid} {name}: 기준본에 이미 있는 화면인데 기준본에서 가져오지 않았어요. "
                                 f"기준본을 가져와(base) 이 과제의 변경을 다시 얹어야 해요.")
            elif m[1] != fingerprint(current):
                conflicts.append(f"{sid} {name}: 이 과제를 시작한 뒤 다른 과제가 기준본을 먼저 바꿨어요. "
                                 f"두 변경을 함께 담아 다시 합쳐야 해요.")
            else:
                writes.append((target, _to_base_screen(text, task_dir.name)))
                done.append(f"{sid} {name}: 기준본 갱신")
        else:
            writes.append((target, _to_base_screen(text, task_dir.name)))
            done.append(f"{sid} {name}: 기준본에 추가")

    pol_file = svc / "정책.md"
    current_pols = policy_sections(pol_file.read_text(encoding="utf-8")) if pol_file.is_file() else {}
    new_pols = dict(current_pols)
    for f in _policy_files(task_dir):
        for pid, sec in policy_sections(f.read_text(encoding="utf-8")).items():
            title = sec.splitlines()[0][3:].strip()
            m = re.search(r"^- 기준본: (\S+)", sec, re.M)
            if pid in current_pols:
                cur = current_pols[pid]
                if _norm_text(cur) == _norm_text(sec):
                    continue
                if not m or m[1] != fingerprint(cur):
                    conflicts.append(f"{title}: 기준본의 같은 정책과 내용이 달라요. 기준본을 가져와(base) 함께 담아야 해요.")
                    continue
                done.append(f"{title}: 기준본 갱신")
            else:
                done.append(f"{title}: 기준본에 추가")
            new_pols[pid] = _to_base_policy(sec, task_dir.name)

    if conflicts or dry_run:
        return done, conflicts

    for target, text in writes:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _keep_captures(task_dir, workspace)
    if new_pols != current_pols:
        def key(pid):
            return int(pid.split("-")[1])
        body = "# 서비스 정책 기준본\n\n> 끝난 과제의 정책을 합친 것이다. 과제에서 고칠 때는 엔진 base로 가져가서 고친다.\n\n"
        body += "\n".join(new_pols[k].rstrip() + "\n" for k in sorted(new_pols, key=key))
        pol_file.write_text(body, encoding="utf-8")
    s = paths.summary(task_dir)
    if s.is_file():
        text = s.read_text(encoding="utf-8").rstrip("\n")
        text += f"\n| {dt.date.today():%Y.%m.%d} | 서비스 기준본에 합침 | 과제 완료 |\n" if "## 변경 이력" in text else ""
        if text:
            s.write_text(text, encoding="utf-8")
    write_registry(workspace)
    return done, conflicts


def write_registry(workspace: Path) -> Path:
    """서비스/화면목록.md: 서비스와 모든 과제의 화면, 정책 번호."""
    inv = inventory(workspace)
    svc = paths.service(workspace)
    svc.mkdir(parents=True, exist_ok=True)

    def key(i):
        return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", i)]

    lines = ["# 화면과 정책 번호", "", "> 엔진이 만든 목록이다. 새 번호는 엔진 next-id로 받는다.", "",
             "## 화면", "", "| 번호 | 이름 | 기준본 | 작업 중인 과제 |", "|---|---|---|---|"]
    for sid in sorted(inv["SCR"], key=key):
        rows = inv["SCR"][sid]
        name = next((n for w, n, _ in rows if w == paths.SERVICE), rows[0][1])
        in_svc = "있음" if any(w == paths.SERVICE for w, _, _ in rows) else "-"
        tasks = ", ".join(f"{w} ({k})" for w, _, k in rows if w != paths.SERVICE) or "-"
        lines.append(f"| {sid} | {name} | {in_svc} | {tasks} |")
    lines += ["", "## 정책", "", "| 번호 | 이름 | 기준본 | 작업 중인 과제 |", "|---|---|---|---|"]
    for pid in sorted(inv["POL"], key=key):
        rows = inv["POL"][pid]
        name = next((n for w, n, _ in rows if w == paths.SERVICE), rows[0][1])
        in_svc = "있음" if any(w == paths.SERVICE for w, _, _ in rows) else "-"
        tasks = ", ".join(f"{w} ({k})" for w, _, k in rows if w != paths.SERVICE) or "-"
        lines.append(f"| {pid} | {name} | {in_svc} | {tasks} |")
    out = svc / "화면목록.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def overlaps(task_dir: Path) -> tuple[list[str], list[str]]:
    """이 과제의 번호가 다른 과제나 기준본과 겹치는지. (고칠 것, 확인할 것)을 돌려준다. validate가 쓴다."""
    task_dir = Path(task_dir)
    inv = inventory(paths.service_root_of(task_dir))
    me = task_dir.name
    out, notes = [], []
    for kind in ("SCR", "POL"):
        for i, rows in inv[kind].items():
            mine = [r for r in rows if r[0] == me]
            others = [r for r in rows if r[0] != me]
            if not mine or not others:
                continue
            if mine[0][2] == "신규":
                dup = [r for r in others if r[0] == paths.SERVICE or r[2] == "신규"]
                if dup:
                    where = ", ".join(sorted({r[0] for r in dup}))
                    out.append(f"{i}: 새로 만든 번호가 {where}에도 있어요. 엔진 next-id로 새 번호를 받으세요.")
                else:  # 다른 과제가 이 과제의 새 화면을 바탕으로 고치고 있다
                    where = ", ".join(sorted({r[0] for r in others}))
                    notes.append(f"{i}: {where}가 이 과제의 새 화면을 바탕으로 고치고 있어요. 이 과제를 먼저 합쳐야 해요.")
            elif mine[0][2] == "변경" and not any(r[0] == paths.SERVICE for r in others):
                others_tasks = ", ".join(sorted({r[0] for r in others}))
                notes.append(f"{i}: {others_tasks}도 같은 화면을 고치고 있어요. 나중에 합칠 때 두 변경을 함께 담아야 해요.")
    return out, notes
