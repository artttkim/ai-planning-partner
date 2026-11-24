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
                return self._json({"items": load(task_dir)})
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
                return self._json(add(task_dir, data))
            if self.path.startswith("/api/feedback/") and self.path.endswith("/reply"):
                fid = self.path.split("/")[3]
                item = reply(task_dir, fid, str(data.get("text", "")))
                return self._json(item or {"error": "not found"}, 200 if item else 404)
            if self.path.startswith("/api/feedback/") and self.path.endswith("/close"):
                item = set_status(task_dir, self.path.split("/")[3], "닫힘")
                return self._json(item or {"error": "not found"}, 200 if item else 404)
            self._send(404, b"", "text/plain")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
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
