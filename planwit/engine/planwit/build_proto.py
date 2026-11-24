"""디자인 화면(프로토타입) 생성. 화면 원본의 구성을 실제 앱 모양의 HTML로 만들고, 브라우저로 캡처한다.

- 프로토타입: 3_결과물/프로토타입.html 파일 하나. 모든 화면이 들어 있고, 눌러서 화면 사이를 이동하며 번호와 설명을 함께 본다
- 캡처: .planwit/프로토타입/<화면 ID>.png (화면 설계서에 넣는 그림)
- 번호 위치: .planwit/프로토타입/<화면 ID>.json (요소 ID별 위치와 크기, px)

디자인 값은 엔진의 proto_theme.css를 쓰고, 서비스의 디자인/디자인.css(없으면 회사/디자인.css)가 있으면 그 뒤에 덧붙여 덮어쓴다.
캡처에는 설치된 Edge 또는 Chrome을 쓴다 (PLANWIT_BROWSER로 경로 지정 가능).
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import paths
from .screens import Component, Screen, load_screens

PROTO = "프로토타입"
FRAMES = {"mobile": (360, 760), "web": (1440, 1024)}
OVERLAYS = ("팝업", "바텀시트", "토스트")
LINK_RE = re.compile(r"SCR-\d+(?:-P\d+)?")
ICONS = {
    "뒤로": '<path d="M15 5l-7 7 7 7"/>',
    "닫기": '<path d="M6 6l12 12M18 6L6 18"/>',
    "더보기": '<circle cx="12" cy="5" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="12" cy="19" r="1.4"/>',
    "검색": '<circle cx="11" cy="11" r="6"/><path d="M16 16l4 4"/>',
    "추가": '<path d="M12 5v14M5 12h14"/>',
    "메뉴": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "공유": '<path d="M12 4v11M7 9l5-5 5 5M5 14v5h14v-5"/>',
    "설정": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>',
    "복사": '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 15V6a1 1 0 011-1h9"/>',
    "알람": '<circle cx="12" cy="13" r="7"/><path d="M12 9v4l3 2M5 4L3 6M19 4l2 2"/>',
    "통계": '<path d="M5 20V11M12 20V5M19 20v-7"/>',
    "다함께": '<circle cx="9" cy="8" r="3"/><circle cx="16" cy="9" r="2.5"/><path d="M3 19c0-3 3-5 6-5s6 2 6 5M14 14c3 0 6 1.5 6 4.5"/>',
    "친구": '<circle cx="9" cy="8" r="3"/><circle cx="16" cy="9" r="2.5"/><path d="M3 19c0-3 3-5 6-5s6 2 6 5M14 14c3 0 6 1.5 6 4.5"/>',
    "공휴일": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4M10 13l4 4M14 13l-4 4"/>',
    "달력": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    "체크": '<path d="M5 12l5 5 9-10"/>',
    "사람": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-4 3-6 7-6s7 2 7 6"/>',
}


def _norm(t: str) -> str:
    return t.replace(" ", "")


def _svg(name: str, size: int = 24) -> str:
    body = ICONS.get(name)
    if body is None:
        return f'<span class="glyph">{html.escape(name[:1])}</span>'
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def _attrs(c: Component, cls: str, extra: str = "") -> str:
    a = f'class="{cls}" data-cid="{html.escape(c.id)}"'
    if c.marker is not None:
        a += f' data-marker="{c.marker}"'
    if c.changed:
        a += ' data-changed="1"'
    if c.align:
        a += f' data-align="{html.escape(c.align)}"'
    if c.h and _norm(c.type) not in ("팝업", "바텀시트"):
        extra += f"height:{c.h}px;"
    if extra:
        a += f' style="{extra}"'
    return a


BACK = ' data-back="1"'


def _t(s: str) -> str:
    return html.escape(s)


class _Html:
    def __init__(self, links: dict[str, str], nav: "_Nav | None" = None, screen_id: str = ""):
        self.links = links  # 요소 ID → 이동할 화면 ID
        self.nav = nav
        self.sid = screen_id
        self.in_overlay = False
        self.has_search = False

    def _go(self, target: str | None) -> str:
        return f' data-go="{target}"' if target and target != self.sid else ""

    def kids(self, c: Component) -> str:
        return "".join(self.render(ch) for ch in c.children)

    def render(self, c: Component) -> str:
        t = _norm(c.type)
        fn = getattr(self, "_" + t, None)
        body = fn(c) if fn else self._기타(c)
        target = self.links.get(c.id)
        if target:
            body = body.replace(" data-cid=", f' data-go="{target}" data-cid=', 1)
        return body

    # 구조
    def _상단바(self, c):
        left = "".join(f'<span class="ico"{BACK if n in ("뒤로", "닫기") else ""}>{_svg(n)}</span>' for n in c.left)
        right = "".join(f'<span class="ico">{_svg(n)}</span>' for n in c.right)
        cls = "topbar" + (" left" if c.align == "left" else "")
        return (f'<header {_attrs(c, cls)}><div class="side l">{left}</div>'
                f'<div class="title">{_t(c.label)}</div><div class="side r">{right}</div></header>')

    def _하단탭바(self, c):
        items = "".join(
            f'<div class="tab{" on" if i == c.selected else ""}"{self._go(self.nav and self.nav.tabbar.get(i))}>'
            f'{_svg(n, 22)}<span>{_t(n)}</span></div>'
            for i, n in enumerate(c.items))
        return f'<nav {_attrs(c, "tabbar")}>{items}</nav>'

    def _탭(self, c):
        targets = self.nav.tabs.get(tuple(c.items), {}) if self.nav else {}
        items = "".join(f'<div class="t{" on" if i == c.selected else ""}"{self._go(targets.get(i))}>{_t(n)}</div>'
                        for i, n in enumerate(c.items))
        return f'<div {_attrs(c, "tabs")}>{items}</div>'

    def _구분선(self, c):
        return f'<hr {_attrs(c, "divider")}>'

    # 입력
    def _입력창(self, c):
        return f'<div {_attrs(c, "input")}><input class="ph" placeholder="{_t(c.label)}"></div>'

    def _검색창(self, c):
        return f'<div {_attrs(c, "input search")}>{_svg("검색", 18)}<input class="ph" placeholder="{_t(c.label)}"></div>'

    def _선택상자(self, c):
        label, _, value = c.label.partition(":")
        value = value.strip()
        return (f'<div {_attrs(c, "select")}><span>{_t(label.strip())}</span>'
                f'<span class="val">{_t(value)}<i class="chev"></i></span></div>')

    def _choice(self, c, kind):
        items = c.items or [c.label]
        rows = "".join(
            f'<label class="opt"><i class="{kind}{" on" if i == c.selected else ""}"></i>'
            f'<span>{_t(n)}</span></label>' for i, n in enumerate(items))
        return f'<div {_attrs(c, "choices " + kind + "s")}>{rows}</div>'

    def _체크박스(self, c):
        return self._choice(c, "chk")

    def _라디오(self, c):
        return self._choice(c, "radio")

    def _토글(self, c):
        on = " on" if c.selected else ""
        label = f'<span>{_t(c.label)}</span>' if c.label else ""
        return f'<div {_attrs(c, "toggle-row" + (" bare" if not c.label else ""))}>{label}<i class="switch{on}"></i></div>'

    # 실행
    def _back(self, c) -> str:
        # 팝업 안에서 이동이 정해지지 않은 버튼은 팝업을 닫고 이전 화면으로 돌아간다.
        return BACK if self.in_overlay and c.id not in self.links else ""

    def _기본버튼(self, c):
        return (f'<button {_attrs(c, "btn primary" + (" small" if c.size == "small" else ""))}{self._back(c)}>'
                f'{_t(c.label)}</button>')

    def _보조버튼(self, c):
        return (f'<button {_attrs(c, "btn secondary" + (" small" if c.size == "small" else ""))}{self._back(c)}>'
                f'{_t(c.label)}</button>')

    def _텍스트링크(self, c):
        return f'<a {_attrs(c, "link")}>{_t(c.label)}</a>'

    def _플로팅버튼(self, c):
        return f'<button {_attrs(c, "fab")}>{_t(c.label or "+")}</button>'

    # 표시
    def _제목(self, c):
        return f'<div {_attrs(c, "h")}>{_t(c.label)}</div>'

    def _본문(self, c):
        return f'<div {_attrs(c, "body")}>{_t(c.label)}</div>'

    def _안내문구(self, c):
        return f'<div {_attrs(c, "helper")}>{_t(c.label)}</div>'

    def _오류문구(self, c):
        return f'<div {_attrs(c, "error")}>{_t(c.label)}</div>'

    def _목록(self, c):
        return f'<div {_attrs(c, "list")}>{self.kids(c)}</div>'

    def _카드(self, c):
        return f'<div {_attrs(c, "card")}>{self.kids(c)}</div>'

    def _묶음(self, c):
        cls = "group item" if c.children else "group"
        return f'<div {_attrs(c, cls)}>{self.kids(c)}</div>'

    def _행(self, c):
        return f'<div {_attrs(c, "row")}>{self.kids(c)}</div>'

    def _표(self, c):
        rows = c.items or [c.label]
        body = "".join(f"<tr><td>{_t(r)}</td></tr>" for r in rows)
        return f'<table {_attrs(c, "table")}>{body}</table>'

    def _이미지(self, c):
        return f'<div {_attrs(c, "img")}><span>{_t(c.label)}</span></div>'

    def _아이콘(self, c):
        small = c.size == "small"
        return f'<span {_attrs(c, "ico solo" + (" small" if small else ""))}>{_svg(c.label, 16 if small else 24)}</span>'

    def _아바타(self, c):
        return f'<span {_attrs(c, "avatar")}>{_t(c.label[:1])}</span>'

    def _배지(self, c):
        tone = {"공개": "pub", "비공개": "priv", "방장": "host", "다함께": "with"}.get(c.label, "")
        return f'<span {_attrs(c, "badge " + tone)}>{_t(c.label)}</span>'

    # 피드백
    @staticmethod
    def _head(label: str) -> str:
        # 첫 줄은 제목, 나머지 줄은 본문으로 보여 준다.
        if not label:
            return ""
        first, _, rest = label.partition(chr(10))
        out = f'<div class="h">{_t(first)}</div>'
        if rest.strip():
            out += f'<div class="body">{_t(rest.strip()).replace(chr(10), "<br>")}</div>'
        return out

    def _overlay_kids(self, c) -> str:
        self.in_overlay = True
        try:
            return self.kids(c)
        finally:
            self.in_overlay = False

    def _팝업(self, c):
        return (f'<div class="dim"{BACK}></div><div {_attrs(c, "dialog")}>{self._head(c.label)}'
                f'{self._overlay_kids(c)}</div>')

    def _바텀시트(self, c):
        return (f'<div class="dim"{BACK}></div><div {_attrs(c, "sheet")}><i class="grab"></i>'
                f'{self._head(c.label)}{self._overlay_kids(c)}</div>')

    def _토스트(self, c):
        return f'<div {_attrs(c, "toast")}>{_t(c.label)}</div>'

    def _로딩(self, c):
        return f'<div {_attrs(c, "loading")}><i class="spin"></i></div>'

    def _빈화면(self, c):
        # 검색창이 있는 화면의 빈화면은 "검색 결과 없음"이다: 평소에는 숨기고, 검색 결과가 없을 때 보인다
        cls = "empty pw-search-empty" if self.has_search else "empty"
        return f'<div {_attrs(c, cls)}><div class="art"></div>{self.kids(c) or "<p>" + _t(c.label) + "</p>"}</div>'

    def _기타(self, c):
        return f'<div {_attrs(c, "box")}>{_t(c.label)}{self.kids(c)}</div>'


_COLLECT = """
<script>
(function(){
  var out = {height: Math.ceil(document.querySelector('.frame').getBoundingClientRect().height), boxes: {}};
  document.querySelectorAll('.screen:not(.bg) [data-cid]').forEach(function(el){
    var r = el.getBoundingClientRect();
    out.boxes[el.getAttribute('data-cid')] = [r.left, r.top, r.width, r.height];
  });
  var pre = document.createElement('pre'); pre.id = 'planwit-boxes'; pre.style.display = 'none';
  pre.textContent = JSON.stringify(out); document.body.appendChild(pre);
})();
</script>
"""

def _links(screen: Screen, known: set[str]) -> dict[str, str]:
    """설명에 '누르면 SCR-xxx'처럼 적힌 이동을 요소에 연결한다. 번호가 달린 요소만 대상이다."""
    by_marker = {str(c.marker): c.id for c in _all(screen) if c.marker is not None}
    out = {}
    for d in screen.descriptions:
        cid = by_marker.get(d.no.strip())
        if not cid:
            continue
        # '누르면 ~', '~로 이동', '~을 연다'처럼 이동을 말하는 문장에서만 화면 ID를 찾는다. ('SCR-070과 같다'는 이동이 아니다)
        sentences = re.split(r"(?<=다)[.]?\s+|[.]\s+", d.text)
        for sentence in sentences:
            if not any(w in sentence for w in ("누르면", "이동", "연다", "보여 준다")):
                continue
            found = [t for t in LINK_RE.findall(sentence) if t in known and t != screen.id]
            if found:
                out[cid] = found[0]
                break
    return out


class _Nav:
    """하단 탭과 탭의 항목마다 이동할 화면. 그 항목이 선택된 화면 중 ID가 가장 앞선 화면으로 간다."""

    def __init__(self, screens: list[Screen]):
        self.tabbar: dict[int, str] = {}
        self.tabs: dict[tuple, dict[int, str]] = {}
        for s in sorted(screens, key=lambda x: x.id):
            if _parent_id(s.id):
                continue
            for c in _all(s):
                if c.selected is None:
                    continue
                t = _norm(c.type)
                if t == "하단탭바":
                    self.tabbar.setdefault(c.selected, s.id)
                elif t == "탭":
                    self.tabs.setdefault(tuple(c.items), {}).setdefault(c.selected, s.id)


def _all(screen: Screen):
    for c in screen.components:
        yield from c.walk()


def _theme(task_dir: Path) -> str:
    css = (Path(__file__).with_name("proto_theme.css")).read_text(encoding="utf-8")
    custom = paths.design_css(task_dir)
    if custom:
        css += "\n/* 디자인.css */\n" + custom.read_text(encoding="utf-8")
    return css


def _parent_id(screen_id: str) -> str | None:
    m = re.match(r"^(.*)-P\d+$", screen_id)
    return m[1] if m else None


def _body(screen: Screen, links: dict[str, str], nav: "_Nav | None" = None) -> str:
    h = _Html(links, nav, screen.id)
    h.has_search = any(_norm(c.type) == "검색창" for c in _all(screen))
    normal = [c for c in screen.components if _norm(c.type) not in OVERLAYS + ("하단탭바", "플로팅버튼")]
    tabbar = [c for c in screen.components if _norm(c.type) == "하단탭바"]
    fab = [c for c in screen.components if _norm(c.type) == "플로팅버튼"]
    over = [c for c in screen.components if _norm(c.type) in OVERLAYS]
    top = [c for c in normal if _norm(c.type) == "상단바"]
    rest = [c for c in normal if _norm(c.type) != "상단바"]
    parts = "".join(h.render(c) for c in top)
    parts += f'<main class="content">{"".join(h.render(c) for c in rest)}</main>'
    parts += "".join(h.render(c) for c in fab)
    parts += "".join(h.render(c) for c in tabbar)
    return parts, "".join(h.render(c) for c in over)


def screen_markup(screen: Screen, screens_by_id: dict[str, Screen], nav: "_Nav | None" = None) -> str:
    """화면 하나의 틀 안 내용. 팝업 화면은 부모 화면을 뒤에 깐다."""
    fw, fh = FRAMES.get(screen.frame, FRAMES["mobile"])
    links = _links(screen, set(screens_by_id))
    main, over = _body(screen, links, nav)
    parent = screens_by_id.get(_parent_id(screen.id) or "")
    bg = ""
    if parent is not None and over and not main.replace('<main class="content"></main>', ""):
        pmain, _ = _body(parent, {})
        bg = f'<div class="screen bg" style="min-height:{fh}px">{pmain}</div>'
        main = ""
    screen_div = (f'<div class="screen{" overlay-only" if bg else ""}" style="min-height:{fh}px">'
                  f'{main}{over}</div>')
    return f'<div class="frame" style="width:{fw}px;--vh:{fh}px">{bg}{screen_div}</div>'


def page(screen: Screen, screens_by_id: dict[str, Screen], css: str) -> str:
    """캡처용 화면 하나짜리 HTML. 요소 위치를 모아 문서에 적는다."""
    fw, _ = FRAMES.get(screen.frame, FRAMES["mobile"])
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width={fw}"><title>{_t(screen.id)}</title>'
            f'<style>{css}\n.screen{{width:{fw}px}}</style></head>'
            f'<body>{screen_markup(screen, screens_by_id)}{_COLLECT}</body></html>')


# ---------- 캡처 ----------

def find_browser() -> str | None:
    env = os.environ.get("PLANWIT_BROWSER")
    if env and Path(env).is_file():
        return env
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for p in candidates:
        if Path(p).is_file():
            return p
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _run(browser: str, args: list[str], done=None, timeout: float = 30) -> str:
    """브라우저를 띄워 실행한다. 일이 끝났는데(done) 브라우저가 닫히지 않으면 닫는다. 표준 출력을 돌려준다."""
    import time

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        out_file = Path(profile) / "stdout.txt"
        cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check", "--disable-extensions", f"--user-data-dir={profile}", *args]
        with open(out_file, "wb") as out:
            proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.DEVNULL)
            end = time.monotonic() + timeout
            while proc.poll() is None and time.monotonic() < end:
                if done and done():
                    time.sleep(0.5)
                    break
                time.sleep(0.2)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        return out_file.read_bytes().decode("utf-8", "replace")


def _measure(browser: str, html_path: Path, width: int, height: int) -> dict:
    for _ in range(3):
        dom = _run(browser, ["--virtual-time-budget=2000", f"--window-size={width},{height}", "--dump-dom",
                             html_path.as_uri()])
        m = re.search(r'<pre id="planwit-boxes"[^>]*>(.*?)</pre>', dom, re.S)
        if m:
            return json.loads(html.unescape(m[1]))
    raise RuntimeError(f"{html_path.name}: 화면 위치를 읽지 못했어요.")


def _shoot(browser: str, html_path: Path, png: Path, width: int, height: int, scale: int = 2):
    def ready():
        return png.is_file() and png.stat().st_size > 0

    for _ in range(3):
        png.unlink(missing_ok=True)
        _run(browser, [f"--window-size={width},{height}", f"--force-device-scale-factor={scale}",
                       "--virtual-time-budget=2000", f"--screenshot={png}", html_path.as_uri()], done=ready)
        if ready():
            return
    raise RuntimeError(f"{png.name}: 캡처하지 못했어요.")


def boxes_path(task_dir: Path, screen_id: str) -> Path:
    return Path(task_dir) / ".planwit" / PROTO / f"{screen_id}.json"


def image_path(task_dir: Path, screen_id: str) -> Path:
    return Path(task_dir) / ".planwit" / PROTO / f"{screen_id}.png"


def proto_path(task_dir: Path) -> Path:
    return paths.output_of(task_dir) / paths.PLAN


def links_with_nav(screen: Screen, by_id: dict[str, Screen], nav: "_Nav") -> dict:
    """요소 ID → 누르면 갈 화면. 탭은 항목별 화면, 팝업 안 버튼은 'back'(닫기)."""
    out: dict = dict(_links(screen, set(by_id)))
    for c in _all(screen):
        t = _norm(c.type)
        targets = nav.tabbar if t == "하단탭바" else nav.tabs.get(tuple(c.items), {}) if t == "탭" else None
        if targets:
            m = {c.items[i]: tgt for i, tgt in sorted(targets.items()) if i < len(c.items) and tgt != screen.id}
            if m:
                out[c.id] = m
    for top in screen.components:
        if _norm(top.type) in ("팝업", "바텀시트"):
            for c in top.walk():
                if _norm(c.type) in ("기본버튼", "보조버튼") and c.id not in out:
                    out[c.id] = "back"
    return out


_SHELL_CSS = """
html, body { height: 100%; }
body.pw { margin: 0; background: #eceef1; display: grid; grid-template-columns: 240px 1fr 400px; height: 100vh; overflow: hidden; }
.pw-list, .pw-desc { overflow: auto; background: #fff; padding: 20px 16px; font-size: 13px; }
.pw-list { border-right: 1px solid #e3e5e8; }
.pw-desc { border-left: 1px solid #e3e5e8; }
.pw-title { font-size: 15px; font-weight: 700; margin-bottom: 4px; }
.pw-sub { color: #8a8f98; font-size: 12px; margin-bottom: 16px; }
.pw-list a { display: block; padding: 7px 10px; border-radius: 8px; color: #1b1d21; text-decoration: none; cursor: pointer; }
.pw-list a .id { color: #8a8f98; font-size: 11px; margin-right: 6px; }
.pw-list a.child { padding-left: 26px; }
.pw-list a:hover { background: #f5f6f8; }
.pw-list a.on { background: #2f3441; color: #fff; }
.pw-list a.on .id { color: #c9ccd2; }
.pw-stage { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; min-width: 0; }
.pw-bar { display: flex; gap: 8px; align-items: center; font-size: 13px; color: #4a5160; }
.pw-bar button { font: inherit; border: 1px solid #c9ccd2; background: #fff; border-radius: 8px; padding: 6px 12px; cursor: pointer; }
.pw-bar label { display: inline-flex; gap: 6px; align-items: center; cursor: pointer; margin-left: 8px; }
.pw-phone { box-sizing: content-box; width: 360px; height: min(760px, calc(100vh - 90px)); overflow-y: auto; overflow-x: hidden; background: #fff; border: 8px solid #1b1d21; border-radius: 32px; box-shadow: 0 12px 40px rgba(0,0,0,.18); scrollbar-width: none; }
.pw-phone::-webkit-scrollbar { display: none; }
.scr { display: none; position: relative; }
.scr.on { display: block; }
.scr .screen { width: 360px; }
[data-go], [data-back] { cursor: pointer; }
.pw-mk { position: absolute; width: 20px; height: 20px; border-radius: 50%; background: #e5484d; color: #fff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; z-index: 60; pointer-events: none; }
.pw-box { position: absolute; border: 2px solid #e5484d; border-radius: 6px; z-index: 59; pointer-events: none; }
body.no-marks .pw-mk, body.no-marks .pw-box { display: none; }
.pw-desc table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.pw-desc th:nth-child(1) { width: 34px; }
.pw-desc th:nth-child(2) { width: 84px; }
.pw-desc th { text-align: left; background: #f5f6f8; padding: 8px 6px; font-weight: 600; }
.pw-desc td { border-bottom: 1px solid #eceef1; padding: 8px 6px; vertical-align: top; line-height: 1.5; }
.pw-desc td.no span { display: inline-flex; width: 20px; height: 20px; border-radius: 50%; background: #e5484d; color: #fff; font-size: 11px; font-weight: 700; align-items: center; justify-content: center; }
.pw-desc .pol { color: #8a8f98; font-size: 12px; margin-top: 2px; }
.pw-desc .note { margin-top: 14px; color: #4a5160; white-space: pre-line; }
.pw-draft { font-size: 11px; color: #8a8f98; }
.pw-tabs { display: flex; gap: 4px; margin-bottom: 14px; }
.pw-tabs button { font: inherit; font-size: 13px; border: 1px solid #c9ccd2; background: #fff; border-radius: 8px; padding: 6px 14px; cursor: pointer; }
.pw-tabs button.on { background: #2f3441; color: #fff; border-color: #2f3441; }
.pw-dev td { font-size: 12px; }
.pw-dev td.cid { font-family: Consolas, monospace; color: #4a5160; white-space: nowrap; }
.pw-dev td.kind { font-family: Consolas, monospace; color: #8a8f98; }
.pw-dev tr:hover td { background: #f0f4ff; }
.pw-dev .go { color: #2f6fed; font-size: 12px; margin-top: 2px; }
.pw-dev th:nth-child(1) { width: 92px !important; }
.pw-dev th:nth-child(2) { width: 86px !important; }
.pw-n { display: inline-flex; width: 16px; height: 16px; border-radius: 50%; background: #e5484d; color: #fff; font-size: 10px; font-weight: 700; align-items: center; justify-content: center; }
.pw-hl { outline: 2px dashed #2f6fed !important; outline-offset: 2px; }
.pw-code { margin-top: 14px; }
.pw-code button { font: inherit; font-size: 12px; border: 1px solid #c9ccd2; background: #fff; border-radius: 8px; padding: 5px 10px; cursor: pointer; }
.pw-fb { margin-top: 6px; }
.pw-fb-h { font-weight: 700; margin-bottom: 8px; }
.pw-fb textarea { width: 100%; min-height: 64px; font: inherit; font-size: 13px; border: 1px solid #c9ccd2; border-radius: 8px; padding: 8px; resize: vertical; }
.pw-fb .row2 { display: flex; gap: 6px; align-items: center; margin: 6px 0; flex-wrap: wrap; }
.pw-fb button { font: inherit; font-size: 12px; border: 1px solid #c9ccd2; background: #fff; border-radius: 8px; padding: 5px 10px; cursor: pointer; }
.pw-fb button.main { background: #2f3441; color: #fff; border-color: #2f3441; }
.pw-fb button.on { background: #2f6fed; color: #fff; border-color: #2f6fed; }
.pw-chip { display: inline-flex; gap: 4px; align-items: center; background: #f0f4ff; color: #2f4fa8; border-radius: 6px; padding: 3px 8px; font-size: 12px; }
.pw-chip b { cursor: pointer; font-weight: 400; }
.pw-fbi { border: 1px solid #eceef1; border-radius: 8px; padding: 8px 10px; margin-top: 8px; font-size: 12px; line-height: 1.5; }
.pw-fbi .st { display: inline-block; border-radius: 4px; padding: 0 6px; margin-right: 6px; font-weight: 600; }
.pw-fbi .st.s대기 { background: #fff4e0; color: #b8660b; }
.pw-fbi .st.s반영함 { background: #e7f6ec; color: #1e7b3c; }
.pw-fbi .st.s질문 { background: #fde8e8; color: #c43030; }
.pw-fbi .st.s닫힘 { background: #eceef1; color: #8a8f98; }
.pw-fbi .ans { color: #4a5160; margin-top: 4px; }
.pw-fbi input { width: 100%; font: inherit; font-size: 12px; border: 1px solid #c9ccd2; border-radius: 6px; padding: 5px 7px; margin-top: 6px; }
.input input.ph { border: 0; outline: 0; background: transparent; font: inherit; color: var(--ink); flex: 1; min-width: 0; }
.input input.ph::placeholder { color: var(--sub); }
.pw-mode { display: inline-flex; border: 1px solid #c9ccd2; border-radius: 8px; overflow: hidden; margin-left: 6px; }
.pw-mode button { border: 0 !important; border-radius: 0 !important; }
.pw-mode button.on { background: #2f6fed !important; color: #fff; }
body.pw-editing .pw-phone { border-color: #2f6fed; }
body.pw-editing .pw-phone [data-cid]:hover { outline: 1px dashed #2f6fed; outline-offset: 1px; }
.pw-picked { outline: 2px solid #2f6fed !important; outline-offset: 2px; }
.pw-hint { font-size: 12px; color: #2f4fa8; background: #f0f4ff; border-radius: 8px; padding: 6px 10px; }
.pw-bar { width: 100%; max-width: 560px; justify-content: center; flex-wrap: wrap; }
.pw-bar .grow { flex: 1; }
.pw-primary { font: inherit; font-size: 13px; background: #2f3441 !important; color: #fff !important; border: 0 !important; border-radius: 8px; padding: 7px 14px; cursor: pointer; text-decoration: none; display: inline-block; }
.pw-primary.sm, button.sm { font-size: 12px; padding: 4px 10px; }
.pw-busy { font-size: 13px; color: #2f6fed; font-weight: 600; }
.pw-dot { float: right; min-width: 18px; height: 18px; border-radius: 9px; background: #e8890c; color: #fff; font-size: 11px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; padding: 0 5px; }
.pw-target { font-size: 12px; color: #4a5160; margin-bottom: 6px; display: flex; gap: 6px; align-items: center; }
.pw-edit-tip { font-size: 12px; color: #2f6fed; text-align: center; min-height: 16px; }
.pw-fbi .top { display: flex; align-items: center; gap: 6px; }
.pw-fbi .tg { font-weight: 600; color: #1b1d21; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pw-fbi .acts { margin-left: auto; display: flex; gap: 8px; }
.pw-fbi .acts a { color: #2f6fed; cursor: pointer; font-size: 12px; }
.pw-fbi .tx { margin-top: 4px; white-space: pre-line; }
.pw-fbi .ans.me { color: #8a8f98; }
.pw-fbi .row2 input { flex: 1; margin: 0; }
.pw-fbi textarea { min-height: 52px; margin-top: 6px; }
[contenteditable="true"] { outline: 2px solid #2f6fed !important; background: #fff; }
#pw-ver { color: #8a8f98; font-size: 12px; margin-left: 6px; }
.pw-code pre { margin-top: 8px; background: #f5f6f8; border-radius: 8px; padding: 10px; font-size: 11px; line-height: 1.45; overflow: auto; max-height: 320px; white-space: pre; }
"""

_SHELL_JS = """
<script>
(function(){
  var data = JSON.parse(document.getElementById('pw-data').textContent);
  var phone = document.querySelector('.pw-phone'), hist = [], cur = null;
  function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function parentOf(id){ var m = id.match(/^(.*)-P\\d+$/); return m ? m[1] : null; }
  function marks(sec){
    sec.querySelectorAll('.pw-mk, .pw-box').forEach(function(e){ e.remove(); });
    var base = sec.getBoundingClientRect();
    sec.querySelectorAll('.screen:not(.bg) [data-changed]').forEach(function(el){
      var r = el.getBoundingClientRect(), b = document.createElement('div'); b.className = 'pw-box';
      b.style.left = (r.left - base.left - 3) + 'px'; b.style.top = (r.top - base.top - 3) + 'px';
      b.style.width = (r.width + 6) + 'px'; b.style.height = (r.height + 6) + 'px'; sec.appendChild(b);
    });
    sec.querySelectorAll('.screen:not(.bg) [data-marker]').forEach(function(el){
      var r = el.getBoundingClientRect(), m = document.createElement('div'); m.className = 'pw-mk';
      m.textContent = el.getAttribute('data-marker');
      m.style.left = Math.min(r.right - base.left - 10, 336) + 'px'; m.style.top = Math.max(r.top - base.top - 10, 2) + 'px';
      sec.appendChild(m);
    });
  }
  var view = 'desc';
  function goText(g){
    if (!g) return '';
    if (g === 'back') return '닫고 이전 화면';
    if (typeof g === 'string') return '→ ' + g;
    return Object.keys(g).map(function(k){ return k + ' → ' + g[k]; }).join(', ');
  }
  function dev(id){
    var d = data[id], h = '';
    h += '<table class="pw-dev"><tr><th>요소 ID</th><th>종류</th><th>글자 · 동작</th></tr>';
    d.tree.forEach(function(r){
      var pad = (r.depth * 10) + 'px';
      h += '<tr data-hl="' + esc(r.id) + '"><td class="cid" style="padding-left:' + pad + '">' + (r.no ? '<span class="pw-n">' + esc(r.no) + '</span> ' : '') + esc(r.id) + '</td>' +
           '<td class="kind">' + esc(r.type) + (r.changed ? ' *' : '') + '</td><td>' + esc(r.text || '') +
           (r.behavior ? '<div>' + esc(r.behavior) + '</div>' : '') +
           (r.policy ? '<div class="pol">정책: ' + esc(r.policy) + '</div>' : '') +
           (r.navigate ? '<div class="go">' + esc(goText(r.navigate)) + '</div>' : '') + '</td></tr>';
    });
    h += '</table><div class="pw-sub" style="margin-top:8px">* 이번 과제에서 바뀌는 요소. 줄에 마우스를 올리면 화면에서 위치를 보여 줘요.<br>' + '동작은 이 명세, 모양(색·글꼴·간격·아이콘)은 피그마 디자인 기준이에요.' + (data.__figma__ ? ' <a href="' + esc(data.__figma__) + '" target="_blank">피그마 열기</a>' : '') + '</div>';
    h += '<div class="pw-code"><button id="pw-copy">이 화면 명세 복사 (YAML)</button><pre id="pw-yaml">' + esc(d.yaml) + '</pre></div>';
    return h;
  }
  function copyText(t){
    var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) {}
    ta.remove();
  }
  // ---------- 피드백 (serve로 열었을 때) ----------
  var served = location.protocol.indexOf('http') === 0, fb = [], picked = null, mode = 'play';
  var serverUp = false, planVer = null, requested = false;
  if (!served && data.__port__){
    fetch('http://127.0.0.1:' + data.__port__ + '/api/ping').then(function(r){ return r.json(); })
      .then(function(){ serverUp = true; renderFb(); }).catch(function(){});
  }
  function post(url, d){
    return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(d)}).then(function(r){ return r.json(); });
  }
  function loadFb(){
    if (!served) return;
    fetch('/api/feedback').then(function(r){ return r.json(); }).then(function(d){
      fb = d.items || []; requested = d.requested;
      if (planVer === null) planVer = d.version;
      else if (d.version !== planVer){ location.reload(); return; }  // 기획안이 다시 만들어졌다: 보던 화면 그대로 새로 고친다
      renderFb();
    });
  }
  var STATUS = {'대기': '반영 전', '반영함': '반영됨', '질문': '답 필요', '닫힘': '닫힘'};
  var editingId = null;
  function pending(){ return fb.filter(function(i){ return i.status === '대기'; }); }
  function renderBar(){
    var box = document.getElementById('pw-applybox'); if (!box) return;
    var n = pending().length;
    box.innerHTML = !served ? '' : requested ? '<span class="pw-busy">반영 중…</span>'
      : n ? '<button class="pw-primary" id="pw-apply">의견 ' + n + '개 반영하기</button>' : '';
    document.querySelectorAll('.pw-list a').forEach(function(a){
      var c = fb.filter(function(i){ return i.status === '대기' && i.screen === a.getAttribute('data-to'); }).length;
      var dot = a.querySelector('.pw-dot');
      if (c && !dot){ dot = document.createElement('span'); dot.className = 'pw-dot'; a.appendChild(dot); }
      if (dot){ if (c) dot.textContent = c; else dot.remove(); }
    });
  }
  function itemHtml(i){
    var h = '<div class="pw-fbi"><div class="top"><span class="st s' + esc(i.status) + '">' + esc(STATUS[i.status] || i.status) + '</span>' +
            '<span class="tg">' + esc(i.label || '화면 전체') + '</span>';
    if (i.status === '대기' && i.kind === '메모' && editingId !== i.id)
      h += '<span class="acts"><a data-act="edit" data-id="' + esc(i.id) + '">수정</a><a data-act="del" data-id="' + esc(i.id) + '">삭제</a></span>';
    h += '</div>';
    if (editingId === i.id){
      h += '<textarea class="pw-edit" data-id="' + esc(i.id) + '">' + esc(i.text) + '</textarea>' +
           '<div class="row2"><button class="pw-primary sm" data-act="save" data-id="' + esc(i.id) + '">저장</button>' +
           '<button class="sm" data-act="cancel">취소</button></div>';
    } else {
      h += '<div class="tx">' + (i.kind === '문구' ? '"' + esc(i.before || '') + '" → "' + esc(i.after || '') + '"' : esc(i.text)) + '</div>';
    }
    if (i.answer) h += '<div class="ans">↳ ' + esc(i.answer) + '</div>';
    if (i.reply) h += '<div class="ans me">나: ' + esc(i.reply) + '</div>';
    if (i.status === '질문') h += '<div class="row2"><input data-reply="' + esc(i.id) + '" placeholder="답 적기"><button class="sm" data-act="reply" data-id="' + esc(i.id) + '">답하기</button></div>';
    return h + '</div>';
  }
  function renderFb(){
    renderBar();
    var tb = document.querySelector('.pw-tabs'); if (tb) tb.outerHTML = tabs();
    var box = document.getElementById('pw-fb'); if (!box) return;
    var old = document.getElementById('pw-fbtext'), keep = old ? old.value : '', focused = document.activeElement === old;
    var h = '';
    if (!served){
      var live = 'http://127.0.0.1:' + data.__port__ + '/#' + cur;
      box.innerHTML = h + (serverUp
        ? '<a class="pw-primary" href="' + live + '">의견 남기는 화면으로 가기</a>'
        : '<div class="pw-sub">Claude에게 "기획안 열어 줘"라고 하면 의견을 남길 수 있어요.</div>');
      return;
    }
    h += '<div class="pw-target">대상 <span class="pw-chip">' + (picked ? esc(picked.label) + ' <b id="pw-unpick" title="대상 지우기">×</b>' : '화면 전체') + '</span></div>';
    h += '<textarea id="pw-fbtext" placeholder="바꿀 점을 적어 주세요"></textarea>';
    h += '<div class="row2"><button class="pw-primary" id="pw-fbsend">의견 추가</button>' +
         '<span class="pw-sub" style="margin:0">' + (mode === 'edit' ? '화면에서 요소를 누르면 대상이 돼요' : '"수정하기"에서 대상을 고를 수 있어요') + '</span></div>';
    var mine = fb.filter(function(i){ return i.screen === cur && i.status !== '닫힘'; });
    var order = {'질문': 0, '대기': 1, '반영함': 2};
    mine.sort(function(a, b){ return (order[a.status] - order[b.status]) || (a.id < b.id ? 1 : -1); });
    h += mine.map(itemHtml).join('');
    box.innerHTML = h;
    var nt = document.getElementById('pw-fbtext');
    if (nt){ nt.value = keep; if (focused) nt.focus(); }
  }
  function fbCount(id){ return fb.filter(function(i){ return i.screen === id && i.status !== '닫힘'; }).length; }
  function tabs(){
    var n = fbCount(cur);
    function b(v, label){ return '<button data-view="' + v + '" class="' + (view === v ? 'on' : '') + '">' + label + '</button>'; }
    return '<div class="pw-tabs">' + b('desc', '설명') + b('fb', '의견' + (n ? ' ' + n : '')) + '</div>';
  }
  function desc(id){
    if (view === 'dev' && !data.__dev__) view = 'desc';
    var d = data[id], h = tabs();
    h += '<div class="pw-title">' + esc(id + ' ' + d.name) + '</div>';
    h += '<div class="pw-sub">' + esc(d.status) + (d.path ? ' · ' + esc(d.path) : '') + '</div>';
    var panelEl = document.querySelector('.pw-desc');
    if (view === 'dev'){ panelEl.innerHTML = h + dev(id); return; }
    if (view === 'fb'){ panelEl.innerHTML = h + '<div class="pw-fb" id="pw-fb"></div>'; renderFb(); return; }
    if (d.rows.length){
      h += '<table><tr><th>No</th><th>항목</th><th>설명</th></tr>';
      d.rows.forEach(function(r){
        h += '<tr><td class="no"><span>' + esc(r[0]) + '</span></td><td>' + esc(r[1]) + '</td><td>' + esc(r[2]) +
             (r[3] ? '<div class="pol">정책: ' + esc(r[3]) + '</div>' : '') + '</td></tr>';
      });
      h += '</table>';
    }
    if (d.note) h += '<div class="note">비고: ' + esc(d.note) + '</div>';
    panelEl.innerHTML = h;
    renderBar();
  }
  function show(id, push){
    var sec = document.getElementById(id); if (!sec) return;
    if (push !== false && cur && cur !== id) hist.push(cur);
    document.querySelectorAll('.scr.on').forEach(function(e){ e.classList.remove('on'); });
    sec.classList.add('on'); cur = id; phone.scrollTop = 0; picked = null;
    document.querySelectorAll('.pw-picked').forEach(function(x){ x.classList.remove('pw-picked'); });
    document.querySelectorAll('.pw-list a').forEach(function(a){ a.classList.toggle('on', a.getAttribute('data-to') === id); });
    desc(id); marks(sec);
    if (history.replaceState) history.replaceState(null, '', '#' + id + (view === 'dev' ? '~dev' : ''));
  }
  function back(){
    var p = hist.pop() || parentOf(cur);
    if (p) show(p, false);
  }
  function labelOf(t){
    var inp = t.querySelector('input');
    return ((t.innerText || '').trim().split(String.fromCharCode(10))[0] || (inp && inp.placeholder) || t.getAttribute('data-cid')).slice(0, 30);
  }
  function editText(el){
    var before = (el.innerText || '').trim();
    el.setAttribute('contenteditable', 'true'); el.focus();
    function done(){
      el.removeAttribute('contenteditable'); el.removeEventListener('blur', done);
      var after = (el.innerText || '').trim();
      if (after && after !== before){
        post('/api/feedback', {screen: cur, cid: el.getAttribute('data-cid'), label: before.slice(0, 30), kind: '문구', before: before, after: after}).then(loadFb);
      }
    }
    el.addEventListener('blur', done);
    el.addEventListener('keydown', function(k){ if (k.key === 'Enter'){ k.preventDefault(); el.blur(); } if (k.key === 'Escape'){ el.innerText = before; el.blur(); } });
  }
  function setMode(m){
    mode = m;
    try { sessionStorage.setItem('pw-mode', m); } catch (e) {} document.body.classList.toggle('pw-editing', m === 'edit');
    document.querySelectorAll('.pw-mode button').forEach(function(b){ b.classList.toggle('on', b.getAttribute('data-mode') === m); });
    if (m === 'play'){ picked = null; document.querySelectorAll('.pw-picked').forEach(function(x){ x.classList.remove('pw-picked'); }); }
    var tip = document.getElementById('pw-tip');
    if (tip) tip.textContent = m === 'edit' ? '글자를 누르면 바로 고쳐지고, 다른 요소를 누르면 의견 대상이 돼요' : '';
    renderFb();
  }
  document.querySelectorAll('.pw-mode button').forEach(function(b){ b.addEventListener('click', function(){ setMode(b.getAttribute('data-mode')); }); });
  // 둘러보기: 검색창에 입력하면 같은 화면의 목록을 거르고, 맞는 것이 없으면 "검색 결과 없음"을 보여 준다
  function searchFilter(inp){
    var scr = inp.closest('.screen'), q = inp.value.trim().toLowerCase(), any = false;
    scr.querySelectorAll('.opt, .list > .group.item, .list > .row, .list > .card').forEach(function(el){
      var ok = !q || (el.innerText || '').toLowerCase().indexOf(q) >= 0;
      el.style.display = ok ? '' : 'none'; if (ok) any = true;
    });
    scr.querySelectorAll('.pw-search-empty').forEach(function(el){ el.classList.toggle('show', !!q && !any); });
    var sec = document.getElementById(cur); if (sec) marks(sec);
  }
  phone.addEventListener('input', function(e){
    if (mode === 'play' && e.target.closest('.input.search')) searchFilter(e.target);
  });
  phone.addEventListener('click', function(e){
    if (mode === 'play'){
      var clr = e.target.closest('.pw-search-empty .btn');
      if (clr){
        var inp = clr.closest('.screen').querySelector('.input.search input');
        if (inp){ inp.value = ''; searchFilter(inp); inp.focus(); }
        return;
      }
    }
    if (mode === 'edit'){
      if (e.target.closest('[contenteditable="true"]')) return;
      e.preventDefault(); e.stopPropagation();
      var t = e.target.closest('[data-cid]');
      if (!t || t.closest('.bg')) return;
      document.querySelectorAll('.pw-picked').forEach(function(x){ x.classList.remove('pw-picked'); });
      t.classList.add('pw-picked');
      picked = {cid: t.getAttribute('data-cid'), label: labelOf(t)};
      renderFb();
      // 글자만 있는 요소는 그 자리에서 고친다
      if (!t.querySelector('[data-cid], input, svg, i') && (t.innerText || '').trim()) editText(t);
      return;
    }
    if (e.target.closest('input')) return;
    var el = e.target.closest('[data-go], [data-back]');
    if (!el || el.closest('.bg')) return;
    e.preventDefault();
    if (el.hasAttribute('data-go')) show(el.getAttribute('data-go')); else back();
  });
  document.querySelectorAll('.pw-list a').forEach(function(a){
    a.addEventListener('click', function(){ hist = []; show(a.getAttribute('data-to')); });
  });
  document.getElementById('pw-back').addEventListener('click', back);
  document.getElementById('pw-home').addEventListener('click', function(){ hist = []; show(data.__start__ ? data.__start__ : Object.keys(data)[0]); });
  document.getElementById('pw-applybox').addEventListener('click', function(e){
    if (e.target.id === 'pw-apply'){ requested = true; renderBar(); post('/api/request', {}).then(loadFb); }
  });
  var panel = document.querySelector('.pw-desc');
  panel.addEventListener('click', function(e){
    var act = e.target.getAttribute && e.target.getAttribute('data-act'), fid = e.target.getAttribute && e.target.getAttribute('data-id');
    if (act === 'edit'){ editingId = fid; renderFb(); return; }
    if (act === 'cancel'){ editingId = null; renderFb(); return; }
    if (act === 'save'){
      var ta = panel.querySelector('textarea.pw-edit'); var t = ta ? ta.value.trim() : '';
      editingId = null;
      if (t) post('/api/feedback/' + fid + '/edit', {text: t}).then(loadFb); else renderFb();
      return;
    }
    if (act === 'del'){ if (confirm('이 의견을 지울까요?')) post('/api/feedback/' + fid + '/delete', {}).then(loadFb); return; }
    if (act === 'reply'){
      var inp = panel.querySelector('input[data-reply="' + fid + '"]');
      if (inp && inp.value.trim()) post('/api/feedback/' + fid + '/reply', {text: inp.value}).then(loadFb);
      return;
    }
    var b = e.target.closest('[data-view]');
    if (b){ view = b.getAttribute('data-view'); try { sessionStorage.setItem('pw-view', view); } catch (x) {} desc(cur); if (history.replaceState) history.replaceState(null, '', '#' + cur + (view === 'dev' ? '~dev' : '')); return; }
    if (e.target.id === 'pw-copy'){ copyText(data[cur].yaml); e.target.textContent = '복사했어요'; }
    if (e.target.id === 'pw-unpick'){ picked = null; document.querySelectorAll('.pw-picked').forEach(function(x){ x.classList.remove('pw-picked'); }); renderFb(); }
    if (e.target.id === 'pw-fbsend'){
      var t = document.getElementById('pw-fbtext'), text = t.value.trim(); if (!text) return;
      t.value = '';
      post('/api/feedback', {screen: cur, cid: picked && picked.cid, label: picked ? picked.label : '', kind: '메모', text: text}).then(function(){ picked = null; loadFb(); });
    }
  });
  function hl(id, on){
    var sec = document.getElementById(cur); if (!sec) return;
    sec.querySelectorAll('.screen:not(.bg) [data-cid="' + id + '"]').forEach(function(el){ el.classList.toggle('pw-hl', on); });
  }
  panel.addEventListener('keydown', function(e){
    var id = e.target.getAttribute && e.target.getAttribute('data-reply');
    if (id && e.key === 'Enter' && e.target.value.trim()){ post('/api/feedback/' + id + '/reply', {text: e.target.value}).then(loadFb); }
  });
  panel.addEventListener('mouseover', function(e){ var r = e.target.closest('[data-hl]'); if (r) hl(r.getAttribute('data-hl'), true); });
  panel.addEventListener('mouseout', function(e){ var r = e.target.closest('[data-hl]'); if (r) hl(r.getAttribute('data-hl'), false); });
  document.getElementById('pw-marks').addEventListener('change', function(e){ document.body.classList.toggle('no-marks', !e.target.checked); });
  window.addEventListener('resize', function(){ var s = document.querySelector('.scr.on'); if (s) marks(s); });
  var hash = location.hash.slice(1).split('~'), start = hash[0];
  try { var sv = sessionStorage.getItem('pw-view'); if (sv) view = sv; } catch (x) {}
  if (hash[1] === 'dev' && data.__dev__) view = 'dev';
  show(document.getElementById(start) ? start : data.__start__, false);
  loadFb();
  if (served){
    document.querySelector('.pw-mode').style.display = '';
    try { if (sessionStorage.getItem('pw-mode') === 'edit') setMode('edit'); } catch (e) {}
  }
  if (served) setInterval(function(){
    var a = document.activeElement;
    if (editingId || (a && (a.id === 'pw-fbtext' || a.hasAttribute('data-reply') || a.isContentEditable))) return;
    loadFb();
  }, 3000);
})();
</script>
"""


def bundle(screens: list[Screen], by_id: dict[str, Screen], css: str, title: str, version: str = "",
           figma: str = "", dev_ready: bool = False, port: int = 0) -> str:
    """모든 화면을 파일 하나에 담은 프로토타입. 화면 사이를 눌러 이동하고, 번호와 설명을 함께 본다."""
    nav = _Nav(screens)
    order = sorted(screens, key=lambda s: s.id)
    sections = "".join(f'<section class="scr" id="{_t(s.id)}">{screen_markup(s, by_id, nav)}</section>'
                       for s in order)
    links = "".join(
        f'<a data-to="{_t(s.id)}" class="{"child" if _parent_id(s.id) else ""}"><span class="id">{_t(s.id)}</span>'
        f'{_t(s.name)}</a>' for s in order)
    from .build_dev import screen_spec, to_yaml

    def flat(items, depth=0):
        rows = []
        for it in items:
            pol = it.get("policy")
            rows.append({"id": it["id"], "depth": depth, "type": it["type"], "text": it.get("text", ""),
                         "no": it.get("no", ""), "behavior": it.get("behavior", ""),
                         "policy": ", ".join(pol) if isinstance(pol, list) else (pol or ""),
                         "navigate": it.get("navigate"), "changed": it.get("changed", False)})
            rows += flat(it.get("children", []), depth + 1)
        return rows

    data = {}
    for s in order:
        spec = screen_spec(s, links_with_nav(s, by_id, nav))
        data[s.id] = {"name": s.name, "status": s.status, "path": s.path, "note": s.note,
                      "rows": [[d.no, d.item, d.text, d.policy] for d in s.descriptions],
                      }
    data["__start__"] = order[0].id
    data["__figma__"] = figma
    data["__dev__"] = False  # 개발 보기는 두지 않는다. 개발자는 기획안과 개발명세.md를 본다
    data["__port__"] = port
    data["__dev__"] = dev_ready
    data["__dev__"] = dev_ready
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_t(title)} 기획안</title>'
            f'<style>{css}\n{_SHELL_CSS}</style></head>'
            f'<body class="pw"><nav class="pw-list"><div class="pw-title">{_t(title)}</div>'
            f'<div class="pw-sub">기획안 · 화면 모양은 초안이에요 (디자인은 피그마)</div>{links}</nav>'
            f'<div class="pw-stage"><div class="pw-bar"><button id="pw-back">← 뒤로</button><button id="pw-home">처음 화면</button>'
            f'<span class="pw-mode" style="display:none"><button data-mode="play" class="on">둘러보기</button><button data-mode="edit">수정하기</button></span>'
            f'<label><input type="checkbox" id="pw-marks" checked>번호</label><span class="grow"></span><span id="pw-applybox"></span></div>'
            f'<div class="pw-edit-tip" id="pw-tip"></div>'
            f'<div class="pw-phone">{sections}</div></div><aside class="pw-desc"></aside>'
            f'<script type="application/json" id="pw-data">{payload}</script>{_SHELL_JS}</body></html>')


def build(task_dir: Path, capture: bool = True) -> list[Path]:
    """기획안.html(프로토타입 + 설명 + 의견) 하나를 만들고, capture=True면 화면마다 캡처와 요소 위치를 저장한다.

    캡처는 화면 설계서(.pptx)를 만들 때만 필요하다."""
    from .screens import task_title

    task_dir = Path(task_dir)
    screens = load_screens(task_dir)
    if not screens:
        return []
    by_id = {s.id: s for s in screens}
    css = _theme(task_dir)
    meta_dir = Path(task_dir) / ".planwit" / PROTO
    meta_dir.mkdir(parents=True, exist_ok=True)
    keep = {s.id for s in screens}
    for old in meta_dir.glob("SCR-*"):
        if old.name.split(".")[0] not in keep:
            old.unlink()
    for old in (paths.output(task_dir) / PROTO, paths.output(task_dir) / f"{PROTO}.html"):  # 예전 이름
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
        elif old.is_file():
            old.unlink()

    out = proto_path(task_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    import datetime as _dt
    version = f"만든 시각 {_dt.datetime.now():%Y.%m.%d %H:%M}"
    from .build_dev import figma_link
    dev_ready = paths.is_service(task_dir) or (paths.output_of(task_dir) / paths.DEV_SPEC).is_file()
    from .feedback import stable_port
    out.write_text(bundle(screens, by_id, css, task_title(task_dir), version, figma_link(task_dir), dev_ready,
                          stable_port(task_dir)), encoding="utf-8")
    written = [out]

    browser = find_browser() if capture else None
    if capture and not browser:
        raise FileNotFoundError("화면을 캡처할 브라우저(Edge 또는 Chrome)를 찾지 못했어요.")
    for s in screens:
        if not capture:
            break
        fw, fh = FRAMES.get(s.frame, FRAMES["mobile"])
        probe = meta_dir / f"{s.id}.probe.html"
        probe.write_text(page(s, by_id, css), encoding="utf-8")
        try:
            data = _measure(browser, probe, fw, fh)
            height = max(fh, int(data["height"]))
            png = image_path(task_dir, s.id)
            _shoot(browser, probe, png, fw, height)
        finally:
            probe.unlink(missing_ok=True)
        data.update(width=fw, height=height)
        boxes_path(task_dir, s.id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        written.append(png)
    return written
