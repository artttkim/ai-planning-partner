"""기획안 피드백. 기획자가 기획안을 보며 남긴 메모와 문구 수정을 과제에 저장한다.

- 저장: <과제>/.planwit/피드백.json
- 기획안은 serve로 열어야 피드백을 남길 수 있다. serve는 이 PC 안(127.0.0.1)에서만 열리고, 밖으로 보내지 않는다.
- 상태: 대기(새로 남김) → 반영함 / 질문(플랜윗이 물음, 기획자가 답하면 다시 대기) / 닫힘
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from pathlib import Path

from . import paths

STATUSES = ("대기", "반영함", "질문", "닫힘")
_lock = threading.Lock()
_build_lock = threading.Lock()


def store(task_dir: Path) -> Path:
    return Path(task_dir) / ".planwit" / "피드백.json"


def load(task_dir: Path) -> list[dict]:
    f = store(task_dir)
    if not f.is_file():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("items", [])
    except (json.JSONDecodeError, OSError):
        return []


def save(task_dir: Path, items: list[dict]):
    f = store(task_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


def _now() -> str:
    return dt.datetime.now().strftime("%Y.%m.%d %H:%M")


def add(task_dir: Path, item: dict) -> dict:
    with _lock:
        items = load(task_dir)
        n = max((int(i["id"][1:]) for i in items if i.get("id", "F0")[1:].isdigit()), default=0) + 1
        new = {
            "id": f"F{n:03d}",
            "screen": str(item.get("screen", "")),
            "cid": item.get("cid") or None,
            "label": str(item.get("label", ""))[:80],
            "kind": "문구" if item.get("kind") == "문구" else "메모",
            "text": str(item.get("text", "")).strip()[:2000],
            "before": item.get("before"),
            "after": item.get("after"),
            "status": "대기",
            "answer": "",
            "reply": "",
            "created": _now(),
        }
        items.append(new)
        save(task_dir, items)
        return new


def reply(task_dir: Path, fid: str, text: str) -> dict | None:
    """기획자가 플랜윗의 질문에 답한다. 다시 대기로 돌아간다."""
    with _lock:
        items = load(task_dir)
        for i in items:
            if i["id"] == fid:
                i["reply"] = (i.get("reply", "") + ("\n" if i.get("reply") else "") + text.strip())[:2000]
                i["status"] = "대기"
                save(task_dir, items)
                return i
    return None


def edit(task_dir: Path, fid: str, text: str) -> dict | None:
    """반영 전 메모만 고칠 수 있다."""
    with _lock:
        items = load(task_dir)
        for i in items:
            if i["id"] == fid and i["status"] == "대기" and i["kind"] == "메모":
                i["text"] = text.strip()[:2000]
                save(task_dir, items)
                return i
    return None


def delete(task_dir: Path, fid: str) -> bool:
    """반영 전 의견만 지울 수 있다."""
    with _lock:
        items = load(task_dir)
        keep = [i for i in items if not (i["id"] == fid and i["status"] == "대기")]
        if len(keep) == len(items):
            return False
        save(task_dir, keep)
        return True


def set_status(task_dir: Path, fid: str, status: str, note: str = "") -> dict | None:
    if status not in STATUSES:
        raise ValueError(f"상태는 {', '.join(STATUSES)} 중 하나예요.")
    with _lock:
        items = load(task_dir)
        for i in items:
            if i["id"] == fid:
                i["status"] = status
                if note:
                    i["answer"] = note
                save(task_dir, items)
                return i
    return None


def pending(task_dir: Path) -> list[dict]:
    return [i for i in load(task_dir) if i.get("status") == "대기"]


def pending_message(workspace: Path) -> str:
    """훅에서 쓴다. 새 피드백이 있는 과제를 알려 준다."""
    lines = []
    for task in paths.all_tasks(Path(workspace)):
        n = len(pending(task))
        if n:
            lines.append(f"- 과제 `{paths.service_root_of(task).name}/{task.name}`: 새 피드백 {n}개")
    if not lines:
        return ""
    return ("[플랜윗 기획안 피드백] 기획자가 기획안에 피드백을 남겼습니다. 기획자의 요청을 처리한 뒤(요청이 없거나 인사면 바로) "
            "\"새 피드백 N개가 있어요. 반영할까요?\"라고 한 줄로 묻고, 반영하라고 하면 feedback 스킬을 따르세요.\n"
            + "\n".join(lines))


# ---------- 글자 수정 바로 반영 (Claude 없이) ----------

_LABEL_RE = __import__("re").compile(r'label:\s*("(?:[^"\\]|\\.)*"|\'(?:[^\']|\'\')*\'|[^,}\n]+)')


def _component_span(yaml_text: str, cid: str) -> tuple[int, int] | None:
    """구성 YAML에서 요소 하나가 차지하는 글자 범위. 한 줄 형식({id: c2, ...})과 여러 줄 형식(- id: c4) 모두."""
    import re

    m = re.search(r"\{\s*id:\s*" + re.escape(cid) + r"\s*,", yaml_text)
    if m:
        end = yaml_text.find("}", m.end())
        return (m.start(), end + 1) if end > 0 else None
    m = re.search(r"^(\s*)- id:\s*" + re.escape(cid) + r"\s*$", yaml_text, re.M)
    if not m:
        return None
    indent = len(m[1])
    end = len(yaml_text)
    for n in re.finditer(r"^(\s*)- ", yaml_text[m.end():], re.M):
        if len(n[1]) <= indent:
            end = m.end() + n.start()
            break
    # 자식 요소 앞까지만 (자식의 label을 바꾸지 않게)
    child = re.search(r"^\s*children:", yaml_text[m.end():end], re.M)
    return (m.start(), m.end() + child.start() if child else end)


def apply_text(task_dir: Path, item: dict) -> bool:
    """문구 수정 피드백을 화면 원본의 label에 바로 반영한다. 정확히 찾지 못하면 하지 않고 False."""
    import re

    import yaml as _yaml

    from .screens import YAML_RE, find_screen_dir, parse_screen

    if item.get("kind") != "문구" or not item.get("cid") or not item.get("after"):
        return False
    try:
        src = find_screen_dir(task_dir) / f"{item['screen']}.md"
    except FileNotFoundError:
        return False
    if not src.is_file():
        return False
    text = src.read_text(encoding="utf-8")
    ym = YAML_RE.search(text)
    if not ym:
        return False
    body = ym["body"]
    span = _component_span(body, item["cid"])
    if not span:
        return False
    part = body[span[0]:span[1]]
    lm = _LABEL_RE.search(part)
    if not lm:
        return False
    try:
        current = str(_yaml.safe_load(lm[1].strip()))
    except _yaml.YAMLError:
        return False
    norm = lambda v: re.sub(r"\s+", " ", str(v)).strip()
    if norm(current) != norm(item.get("before", "")):
        return False
    new_part = part[:lm.start(1)] + json.dumps(item["after"], ensure_ascii=False) + part[lm.end(1):]
    new_body = body[:span[0]] + new_part + body[span[1]:]
    new_text = text[:ym.start("body")] + new_body + text[ym.end("body"):]
    src.write_text(new_text, encoding="utf-8")
    try:
        parse_screen(src)
    except Exception:
        src.write_text(text, encoding="utf-8")  # 되돌린다
        return False
    return True


def rebuild(task_dir: Path):
    """기획안을 다시 만든다. 개발 명세가 있으면 함께."""
    from . import build_dev, build_proto

    build_proto.build(task_dir, capture=False)
    if (paths.output_of(task_dir) / paths.DEV_SPEC).is_file():
        build_dev.build(task_dir)


# ---------- 메모 반영 요청 ----------

def request_file(task_dir: Path) -> Path:
    return Path(task_dir) / ".planwit" / "반영요청"


def wait_request(task_dir: Path, timeout_hours: float = 3.0) -> bool:
    """기획자가 기획안에서 '지금 반영해 줘'를 누를 때까지 기다린다. 눌렸으면 True."""
    end = time.monotonic() + timeout_hours * 3600
    flag = request_file(task_dir)
    while time.monotonic() < end:
        if flag.exists():
            flag.unlink(missing_ok=True)
            return True
        time.sleep(2)
    return False


def stable_port(task_dir: Path) -> int:
    """과제마다 늘 같은 주소를 쓰게 정한 번호. 파일로 연 기획안이 이 주소를 찾아갈 수 있다."""
    import zlib

    return 17000 + zlib.crc32(str(Path(task_dir).resolve()).encode("utf-8")) % 2000


# ---------- 내 PC 안에서만 여는 기획안 서버 ----------

def serve(task_dir: Path, port: int = 0, open_browser: bool = True, idle_hours: float = 3.0) -> None:
    """기획안을 http://127.0.0.1:<port>/ 로 연다. 피드백을 받아 저장한다. 오래 쓰지 않으면 스스로 닫힌다."""
    import webbrowser
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    task_dir = Path(task_dir)
    plan = paths.output_of(task_dir) / paths.PLAN
    last = [time.monotonic()]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 조용히
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code=200):
            self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            last[0] = time.monotonic()
            if self.path in ("/", "/index.html") or self.path.startswith("/#"):
                if not plan.is_file():
                    return self._send(404, "기획안이 아직 없어요.".encode("utf-8"), "text/plain; charset=utf-8")
                return self._send(200, plan.read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/feedback":
                return self._json({"items": load(task_dir), "requested": request_file(task_dir).exists(),
                                   "version": plan.stat().st_mtime if plan.is_file() else 0})
            if self.path == "/api/ping":  # 파일로 연 기획안이 서버가 켜져 있는지 확인한다
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            self._send(404, b"", "text/plain")

        def do_POST(self):
            last[0] = time.monotonic()
            # 다른 사이트에서 이 서버로 보내는 요청은 받지 않는다
            origin = self.headers.get("Origin", "")
            if origin and not origin.startswith(("http://127.0.0.1", "http://localhost")):
                return self._send(403, b"", "text/plain")
            length = min(int(self.headers.get("Content-Length", "0") or 0), 20000)
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return self._json({"error": "bad json"}, 400)
            if self.path == "/api/feedback":
                if not str(data.get("text", "")).strip() and data.get("kind") != "문구":
                    return self._json({"error": "empty"}, 400)
                item = add(task_dir, data)
                if item["kind"] == "문구":
                    with _build_lock:
                        if apply_text(task_dir, item):
                            rebuild(task_dir)
                            item = set_status(task_dir, item["id"], "반영함", "문구를 바로 바꿨어요") or item
                return self._json(item)
            if self.path == "/api/request":
                request_file(task_dir).parent.mkdir(parents=True, exist_ok=True)
                request_file(task_dir).write_text(_now(), encoding="utf-8")
                return self._json({"ok": True})
            if self.path.startswith("/api/feedback/") and self.path.endswith("/reply"):
                fid = self.path.split("/")[3]
                item = reply(task_dir, fid, str(data.get("text", "")))
                return self._json(item or {"error": "not found"}, 200 if item else 404)
            if self.path.startswith("/api/feedback/") and self.path.endswith("/edit"):
                item = edit(task_dir, self.path.split("/")[3], str(data.get("text", "")))
                return self._json(item or {"error": "반영 전 메모만 고칠 수 있어요"}, 200 if item else 409)
            if self.path.startswith("/api/feedback/") and self.path.endswith("/delete"):
                ok = delete(task_dir, self.path.split("/")[3])
                return self._json({"ok": ok}, 200 if ok else 409)
            if self.path.startswith("/api/feedback/") and self.path.endswith("/close"):
                item = set_status(task_dir, self.path.split("/")[3], "닫힘")
                return self._json(item or {"error": "not found"}, 200 if item else 404)
            self._send(404, b"", "text/plain")

    try:
        server = ThreadingHTTPServer(("127.0.0.1", port or stable_port(task_dir)), Handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    (task_dir / ".planwit").mkdir(parents=True, exist_ok=True)
    (task_dir / ".planwit" / "기획안_주소.txt").write_text(url, encoding="utf-8")
    print(f"기획안: {url}", flush=True)

    def watchdog():
        while True:
            time.sleep(60)
            if time.monotonic() - last[0] > idle_hours * 3600:
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        (task_dir / ".planwit" / "기획안_주소.txt").unlink(missing_ok=True)
