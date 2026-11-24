"""엔진 명령 모음. 명령은 04_개발_설계.md 5.1을 따른다."""
import argparse
import importlib
import json
import platform
import sys
from pathlib import Path

from . import __version__

MIN_PYTHON = (3, 11)
REQUIRED = {
    "pptx": "python-pptx",
    "docx": "python-docx",
    "openpyxl": "openpyxl",
    "yaml": "PyYAML",
    "pypdf": "pypdf",
}


def doctor() -> int:
    """Python 버전과 필요한 패키지를 점검한다. 문제가 없으면 0을 돌려준다."""
    problems = []
    if sys.version_info < MIN_PYTHON:
        problems.append(f"Python {platform.python_version()}은 너무 낮아요. 3.11 이상이 필요해요.")
    for module, package in REQUIRED.items():
        try:
            importlib.import_module(module)
        except ImportError:
            problems.append(f"{package} 패키지가 없어요.")
    if problems:
        print("플랜윗 엔진 점검: 문제 있음")
        for p in problems:
            print(f"- {p}")
        return 1
    print(f"플랜윗 엔진 점검: 정상 (엔진 {__version__}, Python {platform.python_version()})")
    return 0


def _look(task_dir: Path, look: str | None) -> str:
    """화면 설계서의 화면 그림 방식. 지정하면 과제에 저장하고, 안 하면 저장된 값(기본 wire)을 쓴다."""
    f = task_dir / ".planwit" / "settings.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    if look:
        data["look"] = look
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    chosen = data.get("look", "design")
    if chosen == "design":
        from . import build_proto
        if build_proto.find_browser() is None:
            print("안내: 화면을 캡처할 브라우저(Edge 또는 Chrome)가 없어 와이어프레임으로 만들어요.")
            return "wire"
    return chosen


def build(kind: str, task: str, version: str, look: str | None = None) -> int:
    from . import build_dev, build_pptx, build_proto, paths, snapshot

    task_dir = Path(task).resolve()
    look = _look(task_dir, look)
    try:
        # all: 기획안.html과 개발명세.md. 화면 설계서(.pptx)는 pptx를 지정할 때만 만든다.
        if kind in ("proto", "all") or (kind == "pptx" and look == "design"):
            for out in build_proto.build(task_dir, capture=(kind in ("pptx", "proto"))):
                if out.suffix == ".png":
                    continue
                print(f"생성: {out.relative_to(task_dir).as_posix()}")
        if kind == "pptx":
            out = build_pptx.build(task_dir, version=version, look=look)
            snapshot.record(task_dir, out)
            print(f"생성: {out.relative_to(task_dir).as_posix()}")
        if kind == "dev" or (kind == "all" and paths.dev_spec(task_dir).is_file()):
            for out in build_dev.build(task_dir):
                print(f"생성: {out.relative_to(task_dir).as_posix()}")
    except PermissionError as e:
        print(f"생성 실패: 파일이 다른 프로그램에서 열려 있어요. 파워포인트를 닫고 다시 시도해 주세요. ({e.filename})")
        return 1
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"생성 실패: {e}")
        return 1
    return 0


def validate(task: str) -> int:
    from . import validate as v

    problems, notes = v.check_all(Path(task).resolve())
    if notes:
        print("확인할 것")
        for n in notes:
            print(f"- {n}")
    if not problems:
        print("ID 검사: 문제 없음")
        return 0
    print("ID 검사: 고칠 것")
    for p in problems:
        print(f"- {p}")
    return 1


def serve(task: str, port: int, no_open: bool) -> int:
    from . import build_proto, feedback, paths

    task_dir = Path(task).resolve()
    if not (paths.output_of(task_dir) / paths.PLAN).is_file():
        build_proto.build(task_dir, capture=False)
    feedback.serve(task_dir, port=port, open_browser=not no_open)
    return 0


def feedback_cmd(task: str, action: str, fid: str | None, status: str | None, note: str) -> int:
    from . import feedback

    task_dir = Path(task).resolve()
    if action == "list":
        items = feedback.pending(task_dir)
        if not items:
            print("새 피드백 없음")
            return 0
        for i in items:
            where = f"{i['screen']}" + (f" / {i['cid']} ({i['label']})" if i.get("cid") else " / 화면 전체")
            body = f"문구 \"{i.get('before')}\" → \"{i.get('after')}\"" if i["kind"] == "문구" else i["text"]
            extra = f" | 앞서 플랜윗 질문: {i['answer']} | 기획자 답: {i['reply']}" if i.get("reply") else ""
            print(f"{i['id']} | {where} | {body}{extra}")
        return 0
    if action == "wait":
        # 기획자가 기획안에서 '지금 반영해 줘'를 누를 때까지 기다린다 (백그라운드로 실행)
        if feedback.wait_request(task_dir):
            print("반영 요청이 왔어요. 새 피드백:")
            return feedback_cmd(task, "list", None, None, "")
        print("기다리는 시간이 끝났어요.")
        return 0
    if action == "set":
        try:
            item = feedback.set_status(task_dir, fid or "", status or "", note)
        except ValueError as e:
            print(e)
            return 1
        print(f"{fid}: {status}" if item else f"{fid}: 없음")
        return 0 if item else 1
    return 2


def next_id(task: str, policy: bool) -> int:
    from . import paths, service

    print(service.next_id(paths.service_root_of(Path(task).resolve()), "POL" if policy else "SCR"))
    return 0


def base(task: str, item: str) -> int:
    from . import service

    try:
        out = service.base(Path(task).resolve(), item)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"가져오기 실패: {e}")
        return 1
    print(f"기준본에서 가져옴: {item} → {out.name}")
    return 0


def merge(task: str, dry_run: bool) -> int:
    from . import build_dev, build_proto, paths, service

    task_dir = Path(task).resolve()
    done, conflicts = service.merge(task_dir, dry_run=dry_run)
    if conflicts:
        print("합치기 전에 풀어야 할 충돌 (아무것도 바꾸지 않았어요)")
        for c in conflicts:
            print(f"- {c}")
    if done:
        print("합칠 것" if (dry_run or conflicts) else "기준본에 합침")
        for d in done:
            print(f"- {d}")
    if not done and not conflicts:
        print("기준본과 달라진 것이 없어요.")
    if not dry_run and not conflicts and done:
        root = paths.service_root_of(task_dir)
        svc = paths.service(root)
        build_proto.build(svc, capture=False)
        build_dev.build(svc)
        print(f"기준본 갱신: {root.name}/{paths.SERVICE}/{paths.PLAN}, {paths.DEV_SPEC}, 화면목록.md")
    return 1 if conflicts else 0


def extract(path: str, out: str | None) -> int:
    from . import extract as ex

    try:
        text = ex.to_text(Path(path))
    except Exception as e:  # 읽지 못한 이유를 그대로 보여 준다
        print(f"읽기 실패: {Path(path).name}: {e}")
        return 1
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"저장: {out}")
    else:
        print(text)
    return 0


def detect(workspace: str | None, hook: bool) -> int:
    from . import detect as d
    from . import paths

    if hook:
        # 훅에서는 표준 입력으로 세션 정보(JSON)가 들어온다. 어떤 오류도 기획자의 요청을 막지 않게 한다.
        # 플랜윗 작업 공간이 아니면 아무것도 읽거나 쓰지 않는다.
        try:
            raw = sys.stdin.read()
            workspace = json.loads(raw).get("cwd") if raw.strip() else None
        except Exception:
            workspace = None
        root = Path(workspace or Path.cwd())
        try:
            if not paths.is_workspace(root):
                return 0
            _migrate_tasks(root)
            msg = d.scan(root)
            from . import feedback as fbm
            fmsg = fbm.pending_message(root)
            if fmsg:
                msg = (msg + "\n\n" if msg else "") + fmsg
        except Exception:
            return 0
    else:
        root = Path(workspace or Path.cwd())
        if not paths.is_workspace(root):
            print(f"플랜윗 작업 공간이 아님: {root}", file=sys.stderr)
            return 1
        msg = d.scan(root)
    if msg:
        print(msg)
    elif not hook:
        print("직접 고친 파일 없음")
    return 0


def _migrate_tasks(root: Path):
    """작업 공간의 과제/ 아래 과제만 옮긴다. 작업 공간 밖은 건드리지 않는다."""
    from . import paths
    for task in paths.all_tasks(root):
        if task.is_dir():
            moved = paths.migrate(task)
            if moved:
                print(f"{task.name}: " + ", ".join(moved))


def migrate(workspace, service_name: str | None = None) -> int:
    from . import paths
    root = Path(workspace or Path.cwd())
    if not paths.is_workspace(root):
        print(f"플랜윗 작업 공간이 아님: {root}", file=sys.stderr)
        return 1
    if service_name:
        for m in paths.migrate_workspace(root, service_name):
            print(m)
    elif (root / paths.TASKS).is_dir() or (root / paths.OLD_SERVICE).is_dir():
        print("안내: 과제가 서비스 폴더 밖에 있어요. 'migrate --service <서비스 이름>'으로 서비스 폴더 아래로 옮길 수 있어요.")
    _migrate_tasks(root)
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="planwit", description="플랜윗 엔진")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Python과 패키지 점검")
    sub.add_parser("version", help="엔진 버전")
    b = sub.add_parser("build", help="원본에서 파일 생성")
    b.add_argument("kind", choices=["pptx", "dev", "proto", "all"])
    b.add_argument("task", help="과제 폴더 경로")
    b.add_argument("--version", dest="doc_version", default="v0.1", help="문서 버전 (기본 v0.1)")
    b.add_argument("--look", choices=["wire", "design"], help="화면 그림: wire(와이어프레임), design(디자인 화면). 과제에 저장된다")
    sv = sub.add_parser("serve", help="기획안을 이 PC 안에서 열고 피드백 받기")
    sv.add_argument("task")
    sv.add_argument("--port", type=int, default=0)
    sv.add_argument("--no-open", action="store_true")
    fbp = sub.add_parser("feedback", help="기획안 피드백 보기(list)와 상태 바꾸기(set)")
    fbp.add_argument("task")
    fbp.add_argument("action", choices=["list", "set", "wait"])
    fbp.add_argument("id", nargs="?")
    fbp.add_argument("status", nargs="?", help="반영함, 질문, 닫힘")
    fbp.add_argument("--note", default="", help="기획자에게 보일 플랜윗의 답이나 질문")
    ni = sub.add_parser("next-id", help="서비스 전체에서 아직 쓰지 않은 다음 화면(또는 정책) 번호")
    ni.add_argument("task")
    ni.add_argument("--policy", action="store_true")
    bs = sub.add_parser("base", help="서비스 기준본의 화면이나 정책을 과제로 가져오기")
    bs.add_argument("task")
    bs.add_argument("item", help="SCR-xxx 또는 POL-xxx")
    mg2 = sub.add_parser("merge", help="과제를 서비스 기준본에 합치기")
    mg2.add_argument("task")
    mg2.add_argument("--dry-run", action="store_true", help="합치지 않고 결과만 보기")
    v = sub.add_parser("validate", help="ID 연결 검사")
    v.add_argument("task")
    e = sub.add_parser("extract", help="문서를 텍스트로 변환")
    e.add_argument("path")
    e.add_argument("--out")
    mg = sub.add_parser("migrate", help="예전 구조의 과제 폴더를 지금 구조로 옮기기")
    mg.add_argument("workspace", nargs="?")
    mg.add_argument("--service", help="예전 구조의 과제와 기준본을 이 이름의 서비스 폴더 아래로 옮긴다")
    dt = sub.add_parser("detect", help="직접 고친 회사 양식 파일 감지")
    dt.add_argument("workspace", nargs="?")
    dt.add_argument("--hook", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "build":
        return build(args.kind, args.task, args.doc_version, args.look)
    if args.command == "validate":
        return validate(args.task)
    if args.command == "serve":
        return serve(args.task, args.port, args.no_open)
    if args.command == "feedback":
        return feedback_cmd(args.task, args.action, args.id, args.status, args.note)
    if args.command == "next-id":
        return next_id(args.task, args.policy)
    if args.command == "base":
        return base(args.task, args.item)
    if args.command == "merge":
        return merge(args.task, args.dry_run)
    if args.command == "extract":
        return extract(args.path, args.out)
    if args.command == "detect":
        return detect(args.workspace, args.hook)
    if args.command == "migrate":
        return migrate(args.workspace, args.service)
    return 2
