"""디자인 화면(프로토타입) 생성. 화면 원본의 구성을 실제 앱 모양의 HTML로 만들고, 브라우저로 캡처한다.

- HTML: 3_결과물/프로토타입/<화면 ID>.html (화면 사이를 눌러 이동할 수 있다)
- 캡처: 3_결과물/프로토타입/<화면 ID>.png
- 번호 위치: .planwit/프로토타입/<화면 ID>.json (요소 ID별 위치와 크기, px)

디자인 값은 엔진의 proto_theme.css를 쓰고, 작업 공간에 회사/디자인.css가 있으면 그 뒤에 덧붙여 덮어쓴다.
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


def _t(s: str) -> str:
    return html.escape(s)


class _Html:
    def __init__(self, links: dict[str, str]):
        self.links = links  # 요소 ID → 이동할 화면 ID

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
        left = "".join(f'<span class="ico">{_svg(n)}</span>' for n in c.left)
        right = "".join(f'<span class="ico">{_svg(n)}</span>' for n in c.right)
        cls = "topbar" + (" left" if c.align == "left" else "")
        return (f'<header {_attrs(c, cls)}><div class="side l">{left}</div>'
                f'<div class="title">{_t(c.label)}</div><div class="side r">{right}</div></header>')

    def _하단탭바(self, c):
        items = "".join(
            f'<div class="tab{" on" if i == c.selected else ""}">{_svg(n, 22)}<span>{_t(n)}</span></div>'
            for i, n in enumerate(c.items))
        return f'<nav {_attrs(c, "tabbar")}>{items}</nav>'

    def _탭(self, c):
        items = "".join(f'<div class="t{" on" if i == c.selected else ""}">{_t(n)}</div>'
                        for i, n in enumerate(c.items))
        return f'<div {_attrs(c, "tabs")}>{items}</div>'

    def _구분선(self, c):
        return f'<hr {_attrs(c, "divider")}>'

    # 입력
    def _입력창(self, c):
        return f'<div {_attrs(c, "input")}><span class="ph">{_t(c.label)}</span></div>'

    def _검색창(self, c):
        return f'<div {_attrs(c, "input search")}>{_svg("검색", 18)}<span class="ph">{_t(c.label)}</span></div>'

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
    def _기본버튼(self, c):
        return f'<button {_attrs(c, "btn primary" + (" small" if c.size == "small" else ""))}>{_t(c.label)}</button>'

    def _보조버튼(self, c):
        return f'<button {_attrs(c, "btn secondary" + (" small" if c.size == "small" else ""))}>{_t(c.label)}</button>'

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
        return f'<span {_attrs(c, "ico solo")}>{_svg(c.label)}</span>'

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

    def _팝업(self, c):
        return f'<div class="dim"></div><div {_attrs(c, "dialog")}>{self._head(c.label)}{self.kids(c)}</div>'

    def _바텀시트(self, c):
        return (f'<div class="dim"></div><div {_attrs(c, "sheet")}><i class="grab"></i>'
                f'{self._head(c.label)}{self.kids(c)}</div>')

    def _토스트(self, c):
        return f'<div {_attrs(c, "toast")}>{_t(c.label)}</div>'

    def _로딩(self, c):
        return f'<div {_attrs(c, "loading")}><i class="spin"></i></div>'

    def _빈화면(self, c):
        return f'<div {_attrs(c, "empty")}><div class="art"></div>{self.kids(c) or "<p>" + _t(c.label) + "</p>"}</div>'

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

_NAV = """
<script>
document.querySelectorAll('[data-go]').forEach(function(el){
  el.style.cursor = 'pointer';
  el.addEventListener('click', function(e){ e.stopPropagation(); location.href = el.getAttribute('data-go') + '.html'; });
});
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
        for target in LINK_RE.findall(d.text):
            if target in known and target != screen.id:
                out[cid] = target
                break
    return out


def _all(screen: Screen):
    for c in screen.components:
        yield from c.walk()


def _theme(task_dir: Path) -> str:
    css = (Path(__file__).with_name("proto_theme.css")).read_text(encoding="utf-8")
    custom = Path(task_dir).parent.parent / "회사" / "디자인.css"
    if custom.is_file():
        css += "\n/* 회사/디자인.css */\n" + custom.read_text(encoding="utf-8")
    return css


def _parent_id(screen_id: str) -> str | None:
    m = re.match(r"^(.*)-P\d+$", screen_id)
    return m[1] if m else None


def _body(screen: Screen, links: dict[str, str]) -> str:
    h = _Html(links)
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


def page(screen: Screen, screens_by_id: dict[str, Screen], css: str, *, collect: bool) -> str:
    fw, fh = FRAMES.get(screen.frame, FRAMES["mobile"])
    known = set(screens_by_id)
    links = _links(screen, known)
    main, over = _body(screen, links)
    parent = screens_by_id.get(_parent_id(screen.id) or "")
    bg = ""
    if parent is not None and over and not main.replace('<main class="content"></main>', ""):
        pmain, _ = _body(parent, {})
        bg = f'<div class="screen bg" style="min-height:{fh}px">{pmain}</div>'
        main = ""
    screen_div = (f'<div class="screen{" overlay-only" if bg else ""}" style="min-height:{fh}px">'
                  f'{main}{over}</div>')
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width={fw}"><title>{_t(screen.id)} {_t(screen.name)}</title>'
            f'<style>{css}\n.screen{{width:{fw}px}}</style></head>'
            f'<body><div class="frame" style="width:{fw}px;--vh:{fh}px">{bg}{screen_div}</div>'
            f'{_COLLECT if collect else _NAV}</body></html>')


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
    return paths.output(task_dir) / PROTO / f"{screen_id}.png"


def build(task_dir: Path, capture: bool = True) -> list[Path]:
    """화면마다 HTML을 만들고(capture=True면) 캡처와 요소 위치를 저장한다."""
    task_dir = Path(task_dir)
    screens = load_screens(task_dir)
    if not screens:
        raise ValueError("화면 원본이 없어요.")
    by_id = {s.id: s for s in screens}
    css = _theme(task_dir)
    out_dir = paths.output(task_dir) / PROTO
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_dir = Path(task_dir) / ".planwit" / PROTO
    meta_dir.mkdir(parents=True, exist_ok=True)
    keep = {s.id for s in screens}
    for old in list(out_dir.glob("SCR-*")) + list(meta_dir.glob("SCR-*")):
        if old.stem not in keep:
            old.unlink()

    browser = find_browser() if capture else None
    if capture and not browser:
        raise FileNotFoundError("화면을 캡처할 브라우저(Edge 또는 Chrome)를 찾지 못했어요.")
    written = []
    for s in screens:
        fw, fh = FRAMES.get(s.frame, FRAMES["mobile"])
        page_html = out_dir / f"{s.id}.html"
        page_html.write_text(page(s, by_id, css, collect=False), encoding="utf-8")
        written.append(page_html)
        if not capture:
            continue
        probe = meta_dir / f"{s.id}.probe.html"
        probe.write_text(page(s, by_id, css, collect=True), encoding="utf-8")
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
