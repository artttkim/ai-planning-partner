"""화면 설계서(.pptx) 생성. 장표 구성과 배치는 03_기능명세서.md 2.3, 와이어프레임 규칙은 5.3을 따른다.

도형 이름에 ID를 넣어(예: SCR-010/c4) 직접 고친 내용을 다시 읽을 수 있게 한다.
와이어프레임은 실제 화면 축척(px)으로 배치하고, 글자도 같은 축척으로 그린다.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from . import paths
from .screens import Component, Screen, load_screens, task_title

FONT = "맑은 고딕"
INK = RGBColor(0x33, 0x33, 0x33)
LINE = RGBColor(0x9A, 0x9A, 0x9A)
FILL = RGBColor(0xED, 0xED, 0xED)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x55, 0x55, 0x55)
SUB = RGBColor(0x77, 0x77, 0x77)
BLACK = RGBColor(0x00, 0x00, 0x00)
MARK = RGBColor(0xE5, 0x48, 0x4D)

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)
EMU_PER_PT = 12700

# 기준 화면 크기(px)
FRAMES = {"mobile": (360, 800), "web": (1440, 1024)}
PAD, GAP = 16, 12  # 화면 좌우 여백, 요소 사이 간격(px)

# 글자 크기(px). 화면 축척대로 줄여 그리고, 같은 값으로 줄 수와 높이를 계산한다.
FONT_PX = {
    "제목": 20, "본문": 14, "안내문구": 12, "오류문구": 12, "텍스트링크": 13, "배지": 11,
    "상단바": 17, "탭": 14, "하단탭바": 11, "기본버튼": 15, "보조버튼": 15, "토스트": 13,
}
BASE_FONT = 14

# 크기가 정해진 요소의 높이(px)
FIXED_H = {
    "상단바": 56, "하단탭바": 56, "탭": 44, "검색창": 44, "입력창": 48, "선택상자": 48,
    "체크박스": 32, "라디오": 32, "토글": 40, "기본버튼": 48, "보조버튼": 48, "플로팅버튼": 56,
    "아이콘": 24, "아바타": 40, "배지": 22, "구분선": 1, "로딩": 48, "이미지": 160, "표": 160,
}
TEXTS = ("제목", "본문", "안내문구", "오류문구")
OVERLAYS = ("팝업", "바텀시트", "토스트", "플로팅버튼")
FULL_WIDTH = ("상단바", "하단탭바", "탭")
ICON_GLYPH = {"뒤로": "<", "닫기": "X", "더보기": "⋮", "검색": "Q", "추가": "+", "메뉴": "≡"}


def _norm(t: str) -> str:
    return t.replace(" ", "")


# ---------- 글자 크기 계산 ----------

def _char_w(ch: str) -> float:
    if ch == " ":
        return 0.3
    return 1.0 if ord(ch) > 0x2E80 else 0.58


def _text_w(text: str, font: float) -> float:
    return max((sum(_char_w(ch) for ch in line) for line in text.split("\n")), default=0) * font


def _lines(text: str, width: float, font: float) -> int:
    total = 0
    for line in (text or "").split("\n"):
        w = sum(_char_w(ch) for ch in line) * font
        total += max(1, -(-int(w) // max(1, int(width))))
    return total


def _text_h(text: str, width: float, font: float) -> float:
    return _lines(text, width, font) * font * 1.45


# ---------- 도형 기본 ----------

def _text(shape, text: str, size: float = 10, color=INK, bold=False, align=PP_ALIGN.LEFT,
          anchor=MSO_ANCHOR.MIDDLE, margin=Inches(0.06)):
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right"):
        setattr(tf, m, margin)
    for m in ("margin_top", "margin_bottom"):
        setattr(tf, m, min(margin, Inches(0.03)))
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
    s = slide.shapes.add_shape(shape, int(x), int(y), max(1, int(w)), max(1, int(h)))
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


def _alpha(shape, opacity: int):
    """채우기 투명도. opacity는 0~100(%)."""
    clr = shape._element.spPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
    a = clr.makeelement(qn("a:alpha"), {"val": str(opacity * 1000)})
    clr.append(a)


def _label(slide, x, y, w, h, text, **kw):
    name = kw.pop("name", None)
    s = _box(slide, x, y, w, h, fill=None, line=None, name=name)
    _text(s, text, **kw)
    return s


def _line(slide, x1, y1, x2, y2, name, color=LINE, width=0.75):
    ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(x1), int(y1), int(x2), int(y2))
    ln.line.color.rgb = color
    ln.line.width = Pt(width)
    ln.name = name
    return ln


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
    """장표 위쪽 머리 칸. cells: [(텍스트, 너비 인치, 굵게, 이름, 글자 크기)]"""
    x = Inches(0.3)
    for text, width, bold, name, size in cells:
        s = _box(slide, x, Inches(0.25), Inches(width), Inches(0.42), name=name)
        _text(s, text, size=size, bold=bold)
        x += Inches(width)


# ---------- 와이어프레임 ----------

class _Canvas:
    """화면 틀 하나. 좌표는 px로 받고 EMU로 바꿔 그린다."""

    def __init__(self, slide, screen_id: str, ox: int, oy: int, k: float, background: bool = False):
        self.slide, self.sid, self.ox, self.oy, self.k = slide, screen_id, ox, oy, k
        self.background = background
        self.marks: list[tuple[Component, float, float, float, float]] = []

    def e(self, v: float) -> int:
        return int(v * self.k)

    def pt(self, px: float) -> float:
        return max(4.0, px * self.k / EMU_PER_PT)

    def name(self, c: Component, suffix: str = "") -> str:
        # 배경으로 깐 부모 화면 도형은 '/'를 넣지 않아 수정 감지 대상에서 뺀다.
        if self.background:
            return f"bg-{self.sid}-{c.id}{'-' + suffix if suffix else ''}"
        return f"{self.sid}/{c.id}{'/' + suffix if suffix else ''}"

    # 도형
    def box(self, x, y, w, h, **kw):
        return _box(self.slide, self.ox + self.e(x), self.oy + self.e(y), self.e(w), self.e(h), **kw)

    def label(self, x, y, w, h, text, font, *, name, color=INK, bold=False, align=PP_ALIGN.LEFT,
              anchor=MSO_ANCHOR.MIDDLE, underline=False):
        s = self.box(x, y, w, h, fill=None, line=None, name=name)
        _text(s, text, size=self.pt(font), color=color, bold=bold, align=align, anchor=anchor, margin=0)
        if underline:
            for p in s.text_frame.paragraphs:
                for r in p.runs:
                    r.font.underline = True
        return s

    def line(self, x1, y1, x2, y2, name, color=LINE, width=0.75):
        return _line(self.slide, self.ox + self.e(x1), self.oy + self.e(y1), self.ox + self.e(x2),
                     self.oy + self.e(y2), name, color, width)


def _align(c: Component, default=PP_ALIGN.LEFT):
    return {"center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT, "left": PP_ALIGN.LEFT}.get(c.align, default)


def _intrinsic_w(c: Component) -> float | None:
    """가로 줄(행) 안에서 글자나 모양만큼만 자리를 차지하는 요소의 너비."""
    t = _norm(c.type)
    if c.w is not None:
        return c.w
    if t == "아이콘":
        return 24
    if t == "아바타":
        return 40
    if t == "배지":
        return _text_w(c.label, FONT_PX["배지"]) + 20
    if t == "텍스트링크":
        return _text_w(c.label, FONT_PX["텍스트링크"]) + 8
    if t == "토글" and not c.label:
        return 40
    if t in ("체크박스", "라디오") and not c.label and not c.items:
        return 20
    if t in ("기본버튼", "보조버튼") and c.size == "small":
        return _text_w(c.label, 13) + 24
    if c.align and t in TEXTS:
        return None
    return None


def _row_widths(c: Component, w: float, gap: float) -> list[float]:
    fixed = [_intrinsic_w(ch) for ch in c.children]
    used = sum(f for f in fixed if f is not None) + gap * max(0, len(c.children) - 1)
    flex = [i for i, f in enumerate(fixed) if f is None]
    share = max(0, (w - used) / len(flex)) if flex else 0
    return [share if f is None else f for f in fixed]


def _choice_widths(c: Component) -> list[float]:
    return [20 + 6 + _text_w(it, BASE_FONT) + 8 for it in c.items]


def _popup_parts(c: Component):
    lines = c.label.split("\n") if c.label else []
    title = lines[0] if lines else ""
    body = "\n".join(lines[1:]).strip("\n")
    return title, body


def _stack_h(children: list[Component], w: float, gap: float) -> float:
    items = [ch for ch in children if _norm(ch.type) not in OVERLAYS]
    if not items:
        return 0
    return sum(_measure(ch, ch.w or w) for ch in items) + gap * (len(items) - 1)


def _measure(c: Component, w: float) -> float:
    t = _norm(c.type)
    if c.h is not None:
        return c.h
    if t in TEXTS:
        return _text_h(c.label, w, FONT_PX[t])
    if t == "텍스트링크":
        return max(24, _text_h(c.label, w, FONT_PX[t]))
    if t == "토글":
        return max(40, _text_h(c.label, w - 52, BASE_FONT) + 12) if c.label else 24
    if t in ("체크박스", "라디오"):
        if c.items and sum(_choice_widths(c)) + 16 * (len(c.items) - 1) > w:
            return 32 * len(c.items)
        return 32 if (c.items or c.label) else 20
    if t in ("기본버튼", "보조버튼") and c.size == "small":
        return 32
    if t == "행":
        gap = 8
        widths = _row_widths(c, w, gap)
        return max((_measure(ch, cw) for ch, cw in zip(c.children, widths)), default=0)
    if t == "카드":
        if c.children:
            return _stack_h(c.children, w - 24, 8) + 24
        return max(56, _text_h(c.label, w - 24, BASE_FONT) + 24)
    if t == "묶음":
        return _stack_h(c.children, w, 8)
    if t == "목록":
        if c.children:
            return sum(_measure(ch, w) + 20 for ch in c.children)
        return 44 * len([ln for ln in c.label.split("\n") if ln.strip()] or [""])
    if t == "빈화면":
        if c.children:
            return _stack_h(c.children, w, 12) + 48
        return 96 + 12 + _text_h(c.label, w, BASE_FONT) + 48
    if t in FIXED_H:
        return FIXED_H[t]
    return max(48, _text_h(c.label, w - 16, BASE_FONT) + 16)


def _overlay_h(c: Component, w: float) -> float:
    t = _norm(c.type)
    if c.h is not None:
        return c.h
    if t == "토스트":
        return _text_h(c.label, w - 32, FONT_PX["토스트"]) + 24
    if t == "플로팅버튼":
        return 56
    inner = w - 48
    title, body = _popup_parts(c)
    h = 24 + (20 if t == "바텀시트" else 0)
    if title:
        h += _text_h(title, inner, 17)
    if body:
        h += 8 + _text_h(body, inner, BASE_FONT)
    if c.children:
        h += (20 if (title or body) else 0) + _stack_h(c.children, inner, 12)
    return h + 24


def _draw_stack(cv: _Canvas, children: list[Component], x, y, w, gap):
    for ch in children:
        if _norm(ch.type) in OVERLAYS:
            continue
        cw = ch.w or w
        h = _measure(ch, cw)
        _draw(cv, ch, x, y, cw, h)
        y += h + gap
    return y


def _icon(cv: _Canvas, name: str, x, y, size, shape_name):
    glyph = ICON_GLYPH.get(name)
    if glyph:
        cv.label(x, y, size, size, glyph, size * 0.75, name=shape_name, bold=True, align=PP_ALIGN.CENTER)
    else:
        s = cv.box(x + 2, y + 2, size - 4, size - 4, fill=WHITE, line=DARK, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
                   name=shape_name)
        _text(s, name, size=cv.pt(min(9, size * 0.35)), color=SUB, align=PP_ALIGN.CENTER, margin=0)


def _choice_mark(cv: _Canvas, t: str, x, y, on: bool, name: str):
    shp = MSO_SHAPE.OVAL if t == "라디오" else MSO_SHAPE.ROUNDED_RECTANGLE
    cv.box(x, y, 20, 20, fill=WHITE, line=DARK, shape=shp, name=name)
    if on:
        cv.box(x + 5, y + 5, 10, 10, fill=DARK, line=None, shape=shp, name=f"{name}-on")


def _draw(cv: _Canvas, c: Component, x, y, w, h):
    t = _norm(c.type)
    nm = cv.name(c)
    font = FONT_PX.get(t, BASE_FONT)

    if t == "상단바":
        cv.box(x, y, w, h, fill=WHITE, line=None, name=f"{nm}-bg" if cv.background else f"{nm}/bg")
        cv.line(x, y + h, x + w, y + h, f"{nm}-line" if cv.background else f"{nm}/line")
        left_w = 12 + 32 * len(c.left)
        right_w = 12 + 32 * len(c.right)
        for i, ic in enumerate(c.left):
            _icon(cv, ic, x + 8 + 32 * i, y + (h - 28) / 2, 28, cv.name(c, f"left{i + 1}"))
        for i, ic in enumerate(c.right):
            _icon(cv, ic, x + w - 8 - 32 * (len(c.right) - i), y + (h - 28) / 2, 28, cv.name(c, f"right{i + 1}"))
        side = max(left_w, right_w, PAD)
        al = _align(c, PP_ALIGN.CENTER)
        tx = left_w if al == PP_ALIGN.LEFT and c.left else (PAD if al == PP_ALIGN.LEFT else side)
        tw = w - tx - (side if al != PP_ALIGN.LEFT else right_w)
        cv.label(x + tx, y, tw, h, c.label, font, name=nm, bold=True, align=al)

    elif t == "탭":
        items = c.items or [c.label]
        iw = w / len(items)
        cv.line(x, y + h, x + w, y + h, cv.name(c, "line"))
        for i, it in enumerate(items):
            on = c.selected == i if c.selected is not None else i == 0
            cv.label(x + iw * i, y, iw, h, it, font, name=cv.name(c, str(i + 1)), bold=on,
                     color=INK if on else SUB, align=PP_ALIGN.CENTER)
            if on:
                cv.box(x + iw * i, y + h - 3, iw, 3, fill=INK, line=None, name=cv.name(c, f"{i + 1}-on"))

    elif t == "하단탭바":
        items = c.items or [c.label]
        iw = w / len(items)
        cv.box(x, y, w, h, fill=WHITE, line=None, name=cv.name(c, "bg"))
        cv.line(x, y, x + w, y, cv.name(c, "line"))
        for i, it in enumerate(items):
            on = c.selected == i
            cx = x + iw * i
            cv.box(cx + iw / 2 - 10, y + 8, 20, 20, fill=INK if on else WHITE, line=INK if on else LINE,
                   shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=cv.name(c, f"{i + 1}-icon"))
            cv.label(cx, y + 32, iw, 16, it, font, name=cv.name(c, str(i + 1)), bold=on,
                     color=INK if on else SUB, align=PP_ALIGN.CENTER)

    elif t in ("입력창", "검색창", "선택상자"):
        s = cv.box(x, y, w, h, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
                   name=cv.name(c, "box"))
        s.adjustments[0] = 0.12
        tx = 12
        if t == "검색창":
            _icon(cv, "검색", x + 8, y + (h - 24) / 2, 24, cv.name(c, "icon"))
            tx = 38
        tw = w - tx - (28 if t == "선택상자" else 12)
        cv.label(x + tx, y, tw, h, c.label, font, name=nm, color=SUB)
        if t == "선택상자":
            cv.label(x + w - 26, y, 18, h, "▾", font, name=cv.name(c, "arrow"), color=SUB, align=PP_ALIGN.CENTER)

    elif t in ("기본버튼", "보조버튼", "플로팅버튼"):
        primary = t != "보조버튼"
        shape = MSO_SHAPE.OVAL if t == "플로팅버튼" else MSO_SHAPE.ROUNDED_RECTANGLE
        s = cv.box(x, y, w, h, fill=DARK if primary else WHITE, line=None if primary else DARK, shape=shape,
                   name=cv.name(c, "box"))
        if t != "플로팅버튼":
            s.adjustments[0] = 0.15
        f = 13 if c.size == "small" else font
        cv.label(x + 4, y, w - 8, h, c.label, f if t != "플로팅버튼" else 22, name=nm,
                 color=WHITE if primary else DARK, bold=True, align=PP_ALIGN.CENTER)

    elif t == "텍스트링크":
        cv.label(x, y, w, h, c.label, font, name=nm, color=DARK, align=_align(c, PP_ALIGN.LEFT), underline=True)

    elif t in TEXTS:
        cv.label(x, y, w, h, c.label, font, name=nm, bold=t == "제목", color=SUB if t == "안내문구" else INK,
                 align=_align(c), anchor=MSO_ANCHOR.TOP)

    elif t in ("체크박스", "라디오"):
        if c.items:
            vertical = h > 32
            cx, cy = x, y
            for i, (it, iw) in enumerate(zip(c.items, _choice_widths(c))):
                _choice_mark(cv, t, cx, cy + 6, c.selected == i, cv.name(c, f"{i + 1}-mark"))
                cv.label(cx + 26, cy, iw - 26, 32, it, BASE_FONT, name=cv.name(c, str(i + 1)))
                if vertical:
                    cy += 32
                else:
                    cx += iw + 16
        else:
            _choice_mark(cv, t, x, y + (h - 20) / 2, c.selected == 1, cv.name(c, "mark"))
            if c.label:
                cv.label(x + 26, y, w - 26, h, c.label, BASE_FONT, name=nm)

    elif t == "토글":
        on = c.selected == 1
        sx = x + w - 40
        cv.box(sx, y + (h - 22) / 2, 40, 22, fill=DARK if on else FILL, line=DARK, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
               name=cv.name(c, "switch")).adjustments[0] = 0.5
        kx = sx + (20 if on else 2)
        cv.box(kx, y + (h - 18) / 2, 18, 18, fill=WHITE, line=DARK, shape=MSO_SHAPE.OVAL, name=cv.name(c, "knob"))
        if c.label:
            cv.label(x, y, w - 52, h, c.label, BASE_FONT, name=nm)

    elif t == "배지":
        s = cv.box(x, y, w, h, fill=WHITE, line=DARK, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=cv.name(c, "box"))
        s.adjustments[0] = 0.5
        cv.label(x, y, w, h, c.label, font, name=nm, color=DARK, bold=True, align=PP_ALIGN.CENTER)

    elif t == "아이콘":
        _icon(cv, c.label, x, y, min(w, h), nm)

    elif t == "아바타":
        cv.box(x, y, w, h, fill=FILL, line=LINE, shape=MSO_SHAPE.OVAL, name=nm)

    elif t == "이미지":
        s = cv.box(x, y, w, h, fill=FILL, line=LINE, name=cv.name(c, "box"))
        cv.line(x, y, x + w, y + h, cv.name(c, "x1"))
        cv.line(x + w, y, x, y + h, cv.name(c, "x2"))
        if c.label:
            cv.label(x, y + h / 2 - 10, w, 20, c.label, 12, name=nm, color=SUB, align=PP_ALIGN.CENTER)

    elif t == "구분선":
        cv.line(x, y, x + w, y, nm)

    elif t == "로딩":
        ring = 28
        cv.box(x + w / 2 - ring / 2, y + 2, ring, ring, fill=None, line=DARK, line_w=2, shape=MSO_SHAPE.OVAL,
               name=cv.name(c, "ring"))
        if c.label:
            cv.label(x, y + ring + 4, w, h - ring - 4, c.label, 12, name=nm, color=SUB, align=PP_ALIGN.CENTER)

    elif t == "행":
        gap = 8
        cx = x
        for ch, cw in zip(c.children, _row_widths(c, w, gap)):
            ch_h = _measure(ch, cw)
            _draw(cv, ch, cx, y + (h - ch_h) / 2, cw, ch_h)
            cx += cw + gap

    elif t == "묶음":
        _draw_stack(cv, c.children, x, y, w, 8)

    elif t == "카드":
        s = cv.box(x, y, w, h, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=cv.name(c, "box"))
        s.adjustments[0] = 0.06
        if c.children:
            _draw_stack(cv, c.children, x + 12, y + 12, w - 24, 8)
        else:
            cv.label(x + 12, y + 12, w - 24, h - 24, c.label, BASE_FONT, name=nm, anchor=MSO_ANCHOR.TOP)

    elif t == "목록":
        cy = y
        rows = c.children or [
            Component(id=f"{c.id}-{i + 1}", type="본문", label=ln)
            for i, ln in enumerate([ln for ln in c.label.split("\n") if ln.strip()] or [""])
        ]
        for i, ch in enumerate(rows):
            rh = (_measure(ch, w) + 20) if c.children else 44
            ch_h = _measure(ch, w) if c.children else _text_h(ch.label, w, BASE_FONT)
            _draw(cv, ch, x, cy + (rh - ch_h) / 2, w, ch_h)
            cy += rh
            if i < len(rows) - 1:
                cv.line(x, cy, x + w, cy, cv.name(c, f"div{i + 1}"))

    elif t == "빈화면":
        if c.children:
            _draw_stack(cv, c.children, x, y + 24, w, 12)
        else:
            img = 96
            cv.box(x + w / 2 - img / 2, y + 24, img, img, fill=FILL, line=LINE, shape=MSO_SHAPE.OVAL,
                   name=cv.name(c, "image"))
            cv.label(x, y + 24 + img + 12, w, h - img - 60, c.label, BASE_FONT, name=nm, color=SUB,
                     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.TOP)

    elif t in ("팝업", "바텀시트"):
        sheet = t == "바텀시트"
        s = cv.box(x, y, w, h + (12 if sheet else 0), fill=WHITE, line=DARK, line_w=1,
                   shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=cv.name(c, "box"))
        s.adjustments[0] = 0.04 if not sheet else 0.06
        cy = y + 24
        if sheet:
            cv.box(x + w / 2 - 20, y + 8, 40, 4, fill=LINE, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
                   name=cv.name(c, "handle"))
            cy += 20
        inner = w - 48
        title, body = _popup_parts(c)
        if title:
            th = _text_h(title, inner, 17)
            cv.label(x + 24, cy, inner, th, title, 17, name=nm, bold=True, anchor=MSO_ANCHOR.TOP)
            cy += th
        if body:
            bh = _text_h(body, inner, BASE_FONT)
            cv.label(x + 24, cy + 8, inner, bh, body, BASE_FONT, name=cv.name(c, "body"), color=DARK,
                     anchor=MSO_ANCHOR.TOP)
            cy += 8 + bh
        if c.children:
            _draw_stack(cv, c.children, x + 24, cy + (20 if (title or body) else 0), inner, 12)

    elif t == "토스트":
        s = cv.box(x, y, w, h, fill=DARK, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=cv.name(c, "box"))
        s.adjustments[0] = 0.3
        cv.label(x + 16, y, w - 32, h, c.label, font, name=nm, color=WHITE, align=PP_ALIGN.CENTER)

    else:  # 표, 기타
        s = cv.box(x, y, w, h, fill=FILL, line=LINE, name=cv.name(c, "box"))
        cv.label(x + 8, y + 8, w - 16, h - 16, c.label or c.type, BASE_FONT, name=nm, anchor=MSO_ANCHOR.TOP)

    if not cv.background and (c.changed or c.marker is not None):
        cv.marks.append((c, x, y, w, h))


def _layout_root(screen: Screen, fw: float, fh: float):
    """화면 맨 위 요소의 위치를 정한다. 돌려주는 값: [(요소, x, y, w, h)], 화면 높이, 하단탭바 높이.

    상단바, 탭, 하단탭바는 화면 너비 전체를 쓰고, 나머지는 좌우 여백 안에 위에서 아래로 쌓는다.
    """
    placed = []
    cursor = 0.0
    prev_full = None
    tabbar = None
    for c in screen.components:
        t = _norm(c.type)
        if t in OVERLAYS:
            continue
        if t == "하단탭바":
            tabbar = c
            continue
        full = t in FULL_WIDTH
        cw = c.w if c.w is not None else (fw if full else fw - PAD * 2)
        cx = c.x if c.x is not None else (0 if full else PAD)
        ch = _measure(c, cw)
        if c.y is not None:
            placed.append((c, cx, c.y, cw, ch))
            continue
        if prev_full is None:
            cursor += 0 if full else PAD
        elif prev_full and full:
            cursor += 0
        elif prev_full:
            cursor += PAD
        else:
            cursor += GAP
        placed.append((c, cx, cursor, cw, ch))
        cursor += ch
        prev_full = full
    bottom = max([y + h for _, _, y, _, h in placed] + [0])
    tab_h = _measure(tabbar, fw) if tabbar else 0
    height = max(fh, bottom + PAD + tab_h)
    if tabbar:
        placed.append((tabbar, 0, height - tab_h, fw, tab_h))
    return placed, height, tab_h


def _place_overlays(screen: Screen, fw: float, fh: float, tab_h: float):
    out = []
    for c in screen.components:
        t = _norm(c.type)
        if t not in OVERLAYS:
            continue
        if t == "팝업":
            w = c.w or min(296, fw - 64)
            h = _overlay_h(c, w)
            x, y = (fw - w) / 2, (fh - h) / 2
        elif t == "바텀시트":
            w = c.w or fw
            h = _overlay_h(c, w)
            x, y = (fw - w) / 2, fh - h
        elif t == "토스트":
            w = c.w or min(fw - 32, _text_w(c.label, FONT_PX["토스트"]) + 40)
            h = _overlay_h(c, w)
            x, y = (fw - w) / 2, fh - tab_h - 24 - h
        else:  # 플로팅버튼
            w = h = c.w or 56
            x, y = fw - 16 - w, fh - tab_h - 16 - h
        x = c.x if c.x is not None else x
        y = c.y if c.y is not None else y
        out.append((c, x, y, c.w or w, c.h or h))
    return out


def _parent_id(screen_id: str) -> str | None:
    m = re.match(r"^(.*)-P\d+$", screen_id)
    return m[1] if m else None


def _draw_marks(cv: _Canvas):
    for c, x, y, w, h in cv.marks:
        if c.changed:
            cv.box(x - 3, y - 3, w + 6, h + 6, fill=None, line=MARK, line_w=1.5, name=f"{cv.sid}/{c.id}/changed")
    for c, x, y, w, h in cv.marks:
        if c.marker is not None:
            d = 20
            m = cv.box(x + w - d / 2, y - d / 2, d, d, fill=MARK, line=None, shape=MSO_SHAPE.OVAL,
                       name=f"{cv.sid}/marker/{c.marker}")
            _text(m, str(c.marker), size=8, color=WHITE, bold=True, align=PP_ALIGN.CENTER, margin=0)


def _draw_wireframe(slide, screen: Screen, area, screens_by_id: dict[str, Screen]):
    ax, ay, aw, ah = area
    fw, fh0 = FRAMES.get(screen.frame, FRAMES["mobile"])
    parent = screens_by_id.get(_parent_id(screen.id) or "")
    overlays = [c for c in screen.components if _norm(c.type) in OVERLAYS]
    base = parent if (parent and overlays) else None

    placed, fh, tab_h = _layout_root(screen, fw, fh0)
    if base is not None:
        b_placed, b_fh, b_tab = _layout_root(base, fw, fh0)
        fh, tab_h = max(fh, b_fh), b_tab
    margin = Inches(0.15)
    k = min((aw - margin * 2) / fw, (ah - margin * 2) / fh)  # EMU per px
    w, h = int(fw * k), int(fh * k)
    fx, fy = ax + (aw - w) // 2, ay + (ah - h) // 2

    frame_shape = MSO_SHAPE.ROUNDED_RECTANGLE if screen.frame == "mobile" else MSO_SHAPE.RECTANGLE
    frame = _box(slide, fx, fy, w, h, fill=WHITE, line=INK, line_w=1.5, shape=frame_shape,
                 name=f"{screen.id}/frame")
    if screen.frame == "mobile":
        frame.adjustments[0] = 0.03

    if base is not None:
        bg = _Canvas(slide, base.id, fx, fy, k, background=True)
        for c, x, y, cw, ch in b_placed:
            if _norm(c.type) == "하단탭바":
                y = fh - ch
            _draw(bg, c, x, y, cw, ch)

    cv = _Canvas(slide, screen.id, fx, fy, k)
    # 팝업 위에 위치를 직접 적은 요소(예전 형식)는 팝업 다음에 그린다.
    on_top = [p for p in placed if overlays and p[0].y is not None]
    for c, x, y, cw, ch in placed:
        if (c, x, y, cw, ch) in on_top:
            continue
        if _norm(c.type) == "하단탭바":
            y = fh - ch
        _draw(cv, c, x, y, cw, ch)

    if any(_norm(c.type) in ("팝업", "바텀시트") for c in overlays):
        dim = _box(slide, fx, fy, w, h, fill=BLACK, line=None, shape=frame_shape, name=f"{screen.id}/dim")
        if screen.frame == "mobile":
            dim.adjustments[0] = 0.03
        _alpha(dim, 40)
    for c, x, y, cw, ch in _place_overlays(screen, fw, fh, tab_h) + on_top:
        _draw(cv, c, x, y, cw, ch)
    _draw_marks(cv)


# ---------- 장표 ----------

def _note_height(note: str) -> tuple[float, int]:
    """비고 칸 높이(인치)와 글자 크기(pt)."""
    if not note:
        return 0.42, 9
    for size in (9, 8, 7):
        per_line = int(12.5 * 72 / size * 1.3)
        lines = sum(max(1, -(-len(ln) // per_line)) for ln in note.splitlines()) + 1
        h = lines * size * 1.3 / 72 + 0.1
        if h <= 1.6:
            return max(0.42, h), size
    return 1.6, 7


def _table_size(rows, avail_in: float) -> int:
    """설명 표가 와이어프레임 영역 높이 안에 들어가는 가장 큰 글자 크기(pt)."""
    for size in (9, 8, 7):
        per_line = int(2.0 * 72 / size * 1.05)
        lines = 0
        for r in rows[1:]:
            lines += sum(max(1, -(-len(ln) // per_line)) for ln in str(r[2]).splitlines())
        h = (lines * size * 1.25 + len(rows) * 5) / 72 + 0.3
        if h <= avail_in:
            return size
    return 7


def _screen_slide(prs, screen: Screen, version: str, screens_by_id: dict[str, Screen]):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _header(slide, [
        (screen.id, 1.3, True, f"{screen.id}/header/id", 11),
        (screen.name, 4.2, True, f"{screen.id}/header/name", 11),
        (f"경로: {screen.path}" if screen.path else "경로: -", 4.0, False, f"{screen.id}/header/path", 9),
        (version, 1.0, False, f"{screen.id}/header/version", 11),
        (screen.status, 1.0, True, f"{screen.id}/header/status", 11),
        (", ".join(screen.requirements) or "-", 1.233, False, f"{screen.id}/header/req", 9),
    ])
    note_text = f"비고: {screen.note}" if screen.note else "비고: -"
    note_h, note_size = _note_height(screen.note)
    top = Inches(0.8)
    bottom = SLIDE_H - Inches(0.2) - Inches(note_h) - Inches(0.08)
    area = (Inches(0.3), top, Inches(8.9), bottom - top)
    _box(slide, *area, fill=WHITE, line=LINE, name=f"{screen.id}/area")
    _draw_wireframe(slide, screen, area, screens_by_id)

    rows = [["No", "항목", "설명"]]
    for d in screen.descriptions:
        text = d.text + (f"\n정책: {d.policy}" if d.policy else "")
        rows.append([d.no, d.item, text])
    if screen.status == "참고" and len(rows) == 1:
        rows.append(["-", "참고 화면", "흐름 이해를 위한 화면이에요. 변경 없음."])
    size = _table_size(rows, (bottom - top) / 914400)
    _table(slide, Inches(9.35), top, Inches(3.68), rows,
           [Inches(0.42), Inches(1.15), Inches(2.11)], name=f"{screen.id}/desc", size=size)

    note = _box(slide, Inches(0.3), bottom + Inches(0.08), Inches(12.73), Inches(note_h),
                name=f"{screen.id}/note")
    _text(note, note_text, size=note_size, color=SUB, anchor=MSO_ANCHOR.TOP)


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
    by_id = {s.id: s for s in screens}

    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    _cover(prs, title, version, today)
    _history(prs, version, today)
    _index(prs, screens)
    for s in screens:
        _screen_slide(prs, s, version, by_id)

    out_dir = paths.output(task_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"화면설계서_{title.replace(' ', '')}_{version}.pptx"
    prs.save(out)
    return out
