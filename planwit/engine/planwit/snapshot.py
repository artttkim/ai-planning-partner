"""생성한 회사 양식 파일의 지문과 도형별 텍스트를 기록한다. 수정 감지(04 5.3)의 기준이 된다."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from pptx import Presentation


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pptx_texts(path: Path) -> dict[str, str]:
    """ID가 붙은 도형(이름에 '/'가 있는 것)의 텍스트를 읽는다. 표는 행마다 따로 읽는다."""
    texts: dict[str, str] = {}
    prs = Presentation(str(path))
    for slide in prs.slides:
        for shape in slide.shapes:
            if "/" not in shape.name:
                continue
            if shape.has_table:
                rows = shape.table.rows
                for r_idx in range(1, len(rows)):
                    cells = [c.text_frame.text for c in rows[r_idx].cells]
                    key = cells[0] or str(r_idx)
                    texts[f"{shape.name}/{key}"] = " | ".join(cells[1:])
            elif shape.has_text_frame and shape.text_frame.text:
                texts[shape.name] = shape.text_frame.text
    return texts


def manifest_path(task_dir: Path) -> Path:
    return Path(task_dir) / ".planwit" / "manifest.json"


def record(task_dir: Path, generated: Path) -> Path:
    task_dir, generated = Path(task_dir), Path(generated)
    mp = manifest_path(task_dir)
    mp.parent.mkdir(exist_ok=True)
    data = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {"files": {}}
    rel = generated.relative_to(task_dir).as_posix()
    data["files"][rel] = {
        "sha256": file_hash(generated),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "texts": pptx_texts(generated) if generated.suffix == ".pptx" else {},
    }
    mp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return mp
