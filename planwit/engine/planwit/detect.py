"""직접 고친 회사 양식 파일 감지 (04 5.3).

생성할 때 남긴 manifest와 지금 파일을 비교해, 바뀐 도형 텍스트를 Claude가 반영할 수 있는 형태로 알려 준다.
바뀐 것이 없으면 아무것도 출력하지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .snapshot import file_hash, manifest_path, pptx_texts, record


def _source_hint(task_dir: Path, key: str) -> str:
    parts = key.split("/")
    screen = parts[0]
    folder = next((p for p in (task_dir / "원본").glob("*화면설계*") if p.is_dir()), None)
    src = f"원본/{folder.name}/{screen}.md" if folder else f"{screen}.md"
    if len(parts) >= 2 and parts[1] == "desc":
        return f"{src} 설명 표 {parts[2]}번 행 (항목 | 설명)"
    if len(parts) >= 2 and parts[1] == "header":
        return f"{src} 머리 정보({parts[2]})"
    if len(parts) == 2:
        return f"{src} 구성의 {parts[1]} label"
    return src


def changes(task_dir: Path) -> list[dict]:
    task_dir = Path(task_dir)
    mp = manifest_path(task_dir)
    if not mp.exists():
        return []
    data = json.loads(mp.read_text(encoding="utf-8"))
    found = []
    for rel, info in data.get("files", {}).items():
        f = task_dir / rel
        if not f.exists() or f.suffix != ".pptx":
            continue
        try:
            if file_hash(f) == info.get("sha256"):
                continue
            now = pptx_texts(f)
        except (PermissionError, OSError):
            continue  # 파워포인트에서 저장 중이면 다음에 다시 본다
        except Exception:
            continue
        before = info.get("texts", {})
        diffs = []
        for key in sorted(set(before) | set(now)):
            a, b = before.get(key), now.get(key)
            if a != b:
                diffs.append({"key": key, "before": a, "after": b, "source": _source_hint(task_dir, key)})
        found.append({"file": rel, "diffs": diffs})
    return found


def scan(workspace: Path) -> str:
    workspace = Path(workspace)
    lines = []
    for task in sorted((workspace / "과제").glob("*/")):
        for item in changes(task):
            if not item["diffs"]:
                # 위치나 모양만 바뀜: 원본에 반영할 글자가 없으니 기록만 새로 한다.
                record(task, task / item["file"])
                continue
            lines.append(f"- 과제 `{task.name}`, 파일 `{item['file']}`")
            for d in item["diffs"]:
                before = "(없음)" if d["before"] is None else repr(d["before"])
                after = "(삭제됨)" if d["after"] is None else repr(d["after"])
                lines.append(f"  - {d['key']} → {d['source']}: {before} → {after}")
    if not lines:
        return ""
    head = (
        "[플랜윗 수정 감지] 기획자가 회사 양식 파일을 직접 고쳤습니다. 기획자의 요청을 처리하기 전에 먼저:\n"
        "1. 아래 변경을 각 원본 파일에 그대로 반영하세요. 같은 항목을 원본에서도 다르게 고친 흔적이 있으면 "
        "어느 쪽을 쓸지 기획자에게 물으세요.\n"
        "2. 영향받는 다른 산출물(설명, 정책, 개발용)을 함께 고치세요.\n"
        "3. engine의 `build pptx`와 `build dev`를 다시 실행해 파일과 manifest를 갱신하세요.\n"
        "4. 기획자에게는 한 줄로만 알리세요. 예: \"화면 설계서 SCR-010에서 고치신 문구를 원본과 개발용에 반영했어요.\"\n"
    )
    return head + "\n".join(lines)
