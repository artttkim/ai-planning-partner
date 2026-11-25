"""문서 파일을 텍스트로 바꾼다. PRD와 회사 문서를 읽을 때 쓴다."""
from __future__ import annotations

from pathlib import Path


def skim(text: str, limit: int) -> str:
    """훑어 읽기용 요약: 제목처럼 보이는 줄을 먼저 모으고, 남는 만큼 앞부분을 붙인다. 토큰을 아끼기 위해서다."""
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    heads = [l for l in lines if l.lstrip().startswith(("#", "---")) or (len(l) <= 40 and not l.endswith(("다.", "요.", ".")))]
    out = "[제목처럼 보이는 줄]\n" + "\n".join(heads)[: limit // 2]
    out += "\n\n[앞부분]\n" + "\n".join(lines)[: max(0, limit - len(out))]
    return out + "\n\n[훑어 읽기: 뒷부분 생략]"


def to_text(path: Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".md", ".txt", ".csv"):
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".docx":
        from docx import Document

        doc = Document(str(path))
        parts = [p.text for p in doc.paragraphs]
        for t in doc.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return "\n".join(parts)
    if ext == ".pptx":
        from pptx import Presentation

        out = []
        for i, slide in enumerate(Presentation(str(path)).slides, 1):
            out.append(f"--- {i}쪽 ---")
            for sh in slide.shapes:
                if sh.has_text_frame and sh.text_frame.text.strip():
                    out.append(sh.text_frame.text)
                elif getattr(sh, "has_table", False) and sh.has_table:
                    for row in sh.table.rows:
                        out.append(" | ".join(c.text_frame.text for c in row.cells))
        return "\n".join(out)
    if ext == ".xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(str(path), read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            out.append(f"--- 시트: {ws.title} ---")
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    out.append(" | ".join("" if v is None else str(v) for v in row))
        return "\n".join(out)
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(f"--- {i}쪽 ---\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages, 1))
    raise ValueError(f"읽을 수 없는 형식이에요: {ext}")
