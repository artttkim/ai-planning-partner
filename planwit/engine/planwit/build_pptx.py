"""화면 설계서(.pptx) 생성. 장표 구성과 배치는 03_기능명세서.md 2.3을 따른다.

도형 이름에 ID를 넣어(예: SCR-010/c4) 직접 고친 내용을 다시 읽을 수 있게 한다.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from .screens import Component, Screen, load_screens, task_title

FONT = "맑은 고딕"
INK = RGBColor(0x33, 0x33, 0x33)
LINE = RGBColor(0x9A, 0x9A, 0x9A)
FILL = RGBColor(0xED, 0xED, 0xED)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x55, 0x55, 0x55)
SUB = RGBColor(0x77, 0x77, 0x77)
MARK = RGBColor(0xE5, 0x48, 0x4D)

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)

# 기준 화면 크기(px)
FRAMES = {"mobile": (360, 800), "web": (1440, 1024)}

# 구성 요소 종류별 기본 높이(px). 위치가 없는 요소를 위에서 아래로 쌓을 때 쓴다.
DEFAULT_H = {
    "상단바": 56, "하단탭바": 56, "탭": 44, "검색창": 44, "입력창": 48, "선택상자": 48,
    "체크박스": 28, "라디오": 28, "토글": 32, "기본버튼": 48, "보조버튼": 48,
    "텍스트링크": 24, "플로팅버튼": 56, "제목": 36, "본문": 44, "목록": 64, "카드": 120,
    "표": 160, "이미지": 160, "아이콘": 32, "배지": 24, "오류문구": 22, "안내문구": 22,
    "로딩": 48, "빈화면": 200, "토스트": 44, "팝업": 220, "바텀시트": 260, "구분선": 1,
}
PAD, GAP = 16, 12

# 글자가 여러 줄이 될 수 있는 요소의 글자 크기(px). 높이를 글자 수로 계산한다.
TEXT_PX = {"제목": 20, "본문": 14, "오류문구": 12, "안내문구": 12}


def _norm(t: str) -> str:
    return t.replace(" ", "")


def _auto_height(c: Component, width_px: float) -> float:
    t = _norm(c.type)
    base = DEFAULT_H.get(t, 48)
    if t not in TEXT_PX or not c.label:
        return base
    font = TEXT_PX[t]
    per_line = max(1, int((width_px - 8) // font))
    lines = sum(max(1, -(-len(part) // per_line)) for part in c.label.split("\n"))
    return max(base, lines * font * 1.5 + 6)


def _text(shape, text: str, size: float = 10, color=INK, bold=False, align=PP_ALIGN.LEFT,
          anchor=MSO_ANCHOR.MIDDLE):
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right"):
        setattr(tf, m, Inches(0.06))
    for m in ("margin_top", "margin_bottom"):
        setattr(tf, m, Inches(0.03))
    lines = text.split("\n") if text else [""]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color


def _box(slide, x, y, w, h, *, fill=WHITE, line=LINE, line_w=0.75, shape=MSO_SHAPE.RECTANGLE, name=None):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(line_w)
    s.shadow.inherit = False
    if name:
        s.name = name
    return s


def _label(slide, x, y, w, h, text, **kw):
    name = kw.pop("name", None)
    s = _box(slide, x, y, w, h, fill=None, line=None, name=name)
    _text(s, text, **kw)
    return s


def _table(slide, x, y, w, rows, col_w, *, name, size=9, row_h=Inches(0.3)):
    shape = slide.shapes.add_table(len(rows), len(col_w), x, y, w, row_h * len(rows))
    shape.name = name
    tbl = shape.table
    for i, cw in enumerate(col_w):
        tbl.columns[i].width = cw
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = FILL if r == 0 else WHITE
            tf = cell.text_frame
            tf.clear()
            tf.word_wrap = True
            run = tf.paragraphs[0].add_run()
            run.text = str(val)
            run.font.name = FONT
            run.font.size = Pt(size)
            run.font.bold = r == 0
            run.font.color.rgb = INK
            cell.margin_left = cell.margin_right = Inches(0.05)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
    return shape


def _header(slide, cells):
    """장표 위쪽 머리 칸. cells: [(텍스트, 너비 인치, 굵게, 이름)]"""
    x = Inches(0.3)
    for text, width, bold, name in cells:
        s = _box(slide, x, Inches(0.25), Inches(width), Inches(0.42), name=name)
        _text(s, text, size=11, bold=bold)
        x += Inches(width)


# ---------- 구성 요소 그리기 ----------

def _draw_component(slide, screen: Screen, c: Component, x, y, w, h, scale):
    t = _norm(c.type)
    name = f"{screen.id}/{c.id}"
    fs = max(7.0, min(12.0, 14 * scale / 0.0095))  # 화면 축척에 맞춘 글자 크기

    if t == "상단바":
        s = _box(slide, x, y, w, h, fill=WHITE, line=None, name=name)
        _text(s, c.label, size=fs, bold=True, align=PP_ALIGN.CENTER)
        line = slide.shapes.add_connector(1, x, y + h, x + w, y + h)
        line.line.color.rgb = LINE
        line.name = f"{name}/line"
    elif t in ("입력창", "검색창", "선택상자"):
        s = _box(slide, x, y, w, h, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=name)
        s.adjustments[0] = 0.12
        _text(s, c.label, size=fs, color=SUB)
    elif t in ("기본버튼", "플로팅버튼"):
        s = _box(slide, x, y, w, h, fill=DARK, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=name)
        s.adjustments[0] = 0.12
        _text(s, c.label, size=fs, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    elif t == "보조버튼":
        s = _box(slide, x, y, w, h, fill=WHITE, line=DARK, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=name)
        s.adjustments[0] = 0.12
        _text(s, c.label, size=fs, color=DARK, bold=True, align=PP_ALIGN.CENTER)
    elif t == "텍스트링크":
        s = _label(slide, x, y, w, h, c.label, size=fs * 0.9, color=DARK, align=PP_ALIGN.CENTER, name=name)
        for r in s.text_frame.paragraphs[0].runs:
            r.font.underline = True
    elif t in ("오류문구", "안내문구"):
        s = _label(slide, x, y, w, h, c.label, size=fs * 0.85, name=name)
    elif t == "제목":
        s = _label(slide, x, y, w, h, c.label, size=fs * 1.3, bold=True, name=name)
    elif t == "본문":
        s = _label(slide, x, y, w, h, c.label, size=fs, name=name, anchor=MSO_ANCHOR.TOP)
    elif t in ("이미지", "아이콘"):
        s = _box(slide, x, y, w, h, fill=FILL, line=LINE, name=name)
        _text(s, c.label or "이미지", size=fs * 0.85, color=SUB, align=PP_ALIGN.CENTER)
        for a, b in (((x, y), (x + w, y + h)), ((x + w, y), (x, y + h))):
            ln = slide.shapes.add_connector(1, a[0], a[1], b[0], b[1])
            ln.line.color.rgb = LINE
            ln.name = f"{name}/x"
    elif t == "구분선":
        s = slide.shapes.add_connector(1, x, y, x + w, y)
        s.line.color.rgb = LINE
        s.name = name
    elif t in ("체크박스", "라디오", "토글"):
        size = int(h * 0.6)
        shp = MSO_SHAPE.OVAL if t == "라디오" else MSO_SHAPE.ROUNDED_RECTANGLE
        _box(slide, x, y + (h - size) // 2, size if t != "토글" else size * 2, size, fill=WHITE, line=DARK,
             shape=shp, name=f"{name}/mark")
        s = _label(slide, x + size * (2 if t == "토글" else 1) + Inches(0.05), y, w - size * 2, h, c.label,
                   size=fs, name=name)
    elif t in ("팝업", "바텀시트"):
        s = _box(slide, x, y, w, h, fill=WHITE, line=DARK, line_w=1.25,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=name)
        s.adjustments[0] = 0.05
        _text(s, c.label, size=fs, anchor=MSO_ANCHOR.TOP)
    elif t == "토스트":
        s = _box(slide, x, y, w, h, fill=DARK, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=name)
        _text(s, c.label, size=fs * 0.9, color=WHITE, align=PP_ALIGN.CENTER)
    else:  # 목록, 카드, 표, 탭, 배지, 로딩, 빈화면, 기타
        s = _box(slide, x, y, w, h, fill=FILL, line=LINE, name=name)
        _text(s, c.label or c.type, size=fs, anchor=MSO_ANCHOR.MIDDLE)

    if c.changed:
        pad = Inches(0.03)
        o = _box(slide, x - pad, y - pad, w + pad * 2, h + pad * 2, fill=None, line=MARK, line_w=1.5,
                 name=f"{name}/changed")
    if c.marker is not None:
        d = Inches(0.24)
        m = _box(slide, x + w - d // 2, y - d // 2, d, d, fill=MARK, line=None, shape=MSO_SHAPE.OVAL,
                 name=f"{screen.id}/marker/{c.marker}")
        _text(m, str(c.marker), size=8, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
        m.text_frame.margin_left = m.text_frame.margin_right = 0


def _draw_wireframe(slide, screen: Screen, area):
    ax, ay, aw, ah = area
    fw, fh = FRAMES.get(screen.frame, FRAMES["mobile"])
    margin = Inches(0.3)
    scale_emu = min((aw - margin * 2) / fw, (ah - margin * 2) / fh)  # EMU per px
    w, h = int(fw * scale_emu), int(fh * scale_emu)
    fx, fy = ax + (aw - w) // 2, ay + (ah - h) // 2
    frame = _box(slide, fx, fy, w, h, fill=WHITE, line=INK, line_w=1.5,
                 shape=MSO_SHAPE.ROUNDED_RECTANGLE if screen.frame == "mobile" else MSO_SHAPE.RECTANGLE,
                 name=f"{screen.id}/frame")
    if screen.frame == "mobile":
        frame.adjustments[0] = 0.05

    px = lambda v: int(v * scale_emu)  # noqa: E731
    scale_in = scale_emu / 914400  # inch per px
    if any(_norm(c.type) in ("팝업", "바텀시트") for c in screen.components):
        dim = _box(slide, fx, fy, w, h, fill=RGBColor(0xD9, 0xD9, 0xD9), line=INK, line_w=1.5,
                   shape=MSO_SHAPE.ROUNDED_RECTANGLE if screen.frame == "mobile" else MSO_SHAPE.RECTANGLE,
                   name=f"{screen.id}/dim")
        if screen.frame == "mobile":
            dim.adjustments[0] = 0.05
    cursor = PAD
    for c in screen.components:
        cw = c.w if c.w is not None else fw - PAD * 2
        ch = c.h if c.h is not None else _auto_height(c, cw)
        cx = c.x if c.x is not None else PAD
        if _norm(c.type) in ("상단바",) and c.x is None:
            cx, cw = 0, fw
        cy = c.y if c.y is not None else cursor
        if c.y is None and _norm(c.type) == "하단탭바":
            cy = fh - ch
        if c.y is None and _norm(c.type) != "하단탭바":
            cursor = cy + ch + GAP
        _draw_component(slide, screen, c, fx + px(cx), fy + px(cy), px(cw), px(ch), scale_in)


def _screen_slide(prs, screen: Screen, version: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, [
        (screen.id, 1.3, True, f"{screen.id}/header/id"),
        (screen.name, 4.2, True, f"{screen.id}/header/name"),
        (f"경로: {screen.path}" if screen.path else "경로: -", 4.0, False, f"{screen.id}/header/path"),
        (version, 1.0, False, f"{screen.id}/header/version"),
        (screen.status, 1.0, True, f"{screen.id}/header/status"),
        (", ".join(screen.requirements) or "-", 1.233, False, f"{screen.id}/header/req"),
    ])
    top, bottom = Inches(0.8), Inches(6.85)
    area = (Inches(0.3), top, Inches(8.9), bottom - top)
    _box(slide, *area, fill=WHITE, line=LINE, name=f"{screen.id}/area")
    _draw_wireframe(slide, screen, area)

    rows = [["No", "항목", "설명"]]
    for d in screen.descriptions:
        text = d.text + (f"\n정책: {d.policy}" if d.policy else "")
        rows.append([d.no, d.item, text])
    if screen.status == "참고" and len(rows) == 1:
        rows.append(["-", "참고 화면", "흐름 이해를 위한 화면이에요. 변경 없음."])
    _table(slide, Inches(9.35), top, Inches(3.68), rows,
           [Inches(0.42), Inches(1.15), Inches(2.11)], name=f"{screen.id}/desc")

    note = _box(slide, Inches(0.3), bottom + Inches(0.05), Inches(12.73), Inches(0.42),
                name=f"{screen.id}/note")
    _text(note, f"비고: {screen.note}" if screen.note else "비고: -", size=9, color=SUB)


def _cover(prs, title: str, version: str, today: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _label(slide, Inches(0.8), Inches(2.4), Inches(11.7), Inches(0.9), title, size=32, bold=True,
           name="cover/title")
    _label(slide, Inches(0.8), Inches(3.3), Inches(11.7), Inches(0.5), "화면 설계서", size=18, color=SUB,
           name="cover/subtitle")
    _label(slide, Inches(0.8), Inches(5.6), Inches(11.7), Inches(0.4), f"{version}  ·  {today}", size=12,
           color=SUB, name="cover/meta")


def _history(prs, version: str, today: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _label(slide, Inches(0.3), Inches(0.25), Inches(12), Inches(0.5), "변경 이력", size=18, bold=True,
           name="history/title")
    _table(slide, Inches(0.3), Inches(0.9), Inches(12.73),
           [["버전", "날짜", "변경 내용", "변경 화면"], [version, today, "최초 작성", "전체"]],
           [Inches(1.2), Inches(1.6), Inches(7.43), Inches(2.5)], name="history/table", size=10)


def _index(prs, screens: list[Screen]):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _label(slide, Inches(0.3), Inches(0.25), Inches(12), Inches(0.5), "화면 목록", size=18, bold=True,
           name="index/title")
    rows = [["화면 ID", "화면명", "구분", "경로", "관련 기능"]]
    rows += [[s.id, s.name, s.status, s.path or "-", ", ".join(s.requirements) or "-"] for s in screens]
    _table(slide, Inches(0.3), Inches(0.9), Inches(12.73), rows,
           [Inches(1.6), Inches(3.0), Inches(1.0), Inches(4.13), Inches(3.0)], name="index/table", size=10)


def build(task_dir: Path, version: str = "v0.1", today: str | None = None) -> Path:
    task_dir = Path(task_dir)
    screens = load_screens(task_dir)
    if not screens:
        raise ValueError("화면 원본이 없어요.")
    title = task_title(task_dir)
    today = today or dt.date.today().strftime("%Y.%m.%d")

    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    _cover(prs, title, version, today)
    _history(prs, version, today)
    _index(prs, screens)
    for s in screens:
        _screen_slide(prs, s, version)

    out_dir = task_dir / "회사양식"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"화면설계서_{title.replace(' ', '')}_{version}.pptx"
    prs.save(out)
    return out
