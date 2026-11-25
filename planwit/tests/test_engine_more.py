import shutil
import sys
from pathlib import Path

import pytest
import yaml
from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from planwit import build_dev, build_pptx, detect, snapshot, validate  # noqa: E402
from planwit.extract import to_text  # noqa: E402

SAMPLE = Path(__file__).parent / "samples" / "2026-11-20_로그인_정책_개선"


@pytest.fixture
def workspace(tmp_path):
    task = tmp_path / "과제" / SAMPLE.name
    shutil.copytree(SAMPLE, task, ignore=shutil.ignore_patterns("3_결과물", ".planwit"))
    return tmp_path


def _task(ws):
    return ws / "과제" / SAMPLE.name


def test_build_dev(workspace):
    from planwit.screens import load_screens

    files = build_dev.build(_task(workspace))
    assert [f.name for f in files] == ["개발명세.md"]
    text = files[0].read_text(encoding="utf-8")
    assert "### SCR-010" in text and "## 화면 목록" in text
    s = next(x for x in load_screens(_task(workspace)) if x.id == "SCR-010")
    data = build_dev.screen_spec(s)
    assert data["status"] == "changed"
    assert data["policies"] == ["POL-001"]
    btn = next(c for c in data["components"] if c["id"] == "c6")
    assert btn["type"] == "button.primary" and "활성화" in btn["behavior"]


def test_validate_sample_is_clean(workspace):
    assert validate.check(_task(workspace)) == []


def test_validate_finds_missing_screen(workspace):
    (_task(workspace) / "2_기획문서" / "03_화면설계" / "SCR-030.md").unlink()
    problems = validate.check(_task(workspace))
    assert any("SCR-030" in p for p in problems)


def test_detect_reports_edited_text(workspace):
    task = _task(workspace)
    out = build_pptx.build(task, today="2026.11.20")
    snapshot.record(task, out)
    assert detect.scan(workspace) == ""

    prs = Presentation(str(out))
    for slide in prs.slides:
        for sh in slide.shapes:
            if sh.name == "SCR-010/c5":
                sh.text_frame.paragraphs[0].runs[0].text = "입력한 정보가 맞지 않아요. (4/5회)"
    prs.save(str(out))

    msg = detect.scan(workspace)
    assert "SCR-010/c5" in msg and "입력한 정보가 맞지 않아요" in msg and "SCR-010.md" in msg


def test_extract_pptx(workspace):
    out = build_pptx.build(_task(workspace), today="2026.11.20")
    text = to_text(out)
    assert "다시 만나서 반가워요" in text


def test_migrate_old_layout(tmp_path):
    from planwit import paths

    task = tmp_path / "과제" / "2026-11-20_예전_과제"
    (task / "원본" / "04_화면설계").mkdir(parents=True)
    (task / "입력").mkdir()
    (task / "회사양식").mkdir()
    (task / "개발용" / "화면").mkdir(parents=True)
    (task / "과제요약.md").write_text("# 예전 과제\n\n- 원본: `원본/02_영향분석.md`, 화면 `개발용/화면/`\n", encoding="utf-8")
    (task / "검수함.md").write_text("# 검수함\n", encoding="utf-8")
    (task / "결정기록.md").write_text("# 결정 기록\n\n| 날짜 | 결정 | 이유 | 출처 |\n|---|---|---|---|\n| 2026.11.20 | 가 | 나 | 다 |\n",
                                    encoding="utf-8")
    (task / "개발용" / "화면" / "SCR-010.yaml").write_text("id: SCR-010\n", encoding="utf-8")
    moved = paths.migrate(task)
    assert moved
    for name in ["00_과제요약.md", "01_검수함.md", "1_입력자료", "2_기획문서/04_화면설계", "3_결과물"]:
        assert (task / name).exists(), name
    for gone in ["개발용", "02_결정기록.md", "3_결과물/개발용"]:
        assert not (task / gone).exists(), gone
    text = (task / "00_과제요약.md").read_text(encoding="utf-8")
    assert "`2_기획문서/02_영향분석.md`" in text and "`3_결과물/개발명세.md`" in text
    assert "## 결정 기록" in text and "| 2026.11.20 | 가 | 나 | 다 |" in text
    assert paths.migrate(task) == []  # 두 번 실행해도 그대로


def test_engine_ignores_folders_outside_workspace(tmp_path, capsys):
    """플랜윗 작업 공간이 아닌 폴더는 훅과 migrate가 건드리지 않는다."""
    import io
    import json as _json

    from planwit import cli, paths

    other = tmp_path / "other_project"
    (other / "원본").mkdir(parents=True)
    (other / "검수함.md").write_text("다른 프로젝트 파일", encoding="utf-8")
    (other / "과제" / "x" / "원본").mkdir(parents=True)
    assert not paths.is_workspace(other)

    assert cli.main(["migrate", str(other)]) == 1
    sys_stdin = sys.stdin
    try:
        sys.stdin = io.StringIO(_json.dumps({"cwd": str(other)}))
        assert cli.main(["detect", "--hook"]) == 0
    finally:
        sys.stdin = sys_stdin
    assert (other / "원본").is_dir() and (other / "검수함.md").is_file()
    assert (other / "과제" / "x" / "원본").is_dir()

    ws = tmp_path / "ws"
    (ws / "과제" / "t" / "원본").mkdir(parents=True)
    (ws / paths.WORKSPACE_MARK).write_text("", encoding="utf-8")
    assert paths.is_workspace(ws)
    assert cli.main(["migrate", str(ws)]) == 0
    assert (ws / "과제" / "t" / paths.DOCS).is_dir()


def test_proto_html_and_design_deck(workspace):
    """디자인 화면: HTML에 번호 요소와 화면 이동이 들어가고, 화면 설계서에 캡처와 번호가 들어간다."""
    import base64
    import json as _json

    from planwit import build_proto
    from planwit.screens import load_screens

    task = _task(workspace)
    pages = build_proto.build(task, capture=False)
    assert pages == [build_proto.proto_path(task)]
    text = pages[0].read_text(encoding="utf-8")
    assert "data-marker=" in text and 'id="SCR-010"' in text and 'id="SCR-020-P1"' in text
    assert "data-go=" in text and "data-back=" in text

    # 브라우저 없이 캡처와 위치 파일을 흉내 낸다.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==")
    for s in load_screens(task):
        build_proto.image_path(task, s.id).write_bytes(png)
        boxes = {c.id: [10, 10, 100, 40] for top in s.components for c in top.walk()}
        build_proto.boxes_path(task, s.id).write_text(
            _json.dumps({"width": 360, "height": 760, "boxes": boxes}), encoding="utf-8")
    out = build_pptx.build(task, look="design")
    names = [sh.name for slide in Presentation(out).slides for sh in slide.shapes]
    assert "SCR-010/image" in names
    assert any(n.startswith("SCR-010/marker/") for n in names)


def test_design_deck_needs_proto(workspace):
    with pytest.raises(ValueError):
        build_pptx.build(_task(workspace), look="design")


def _ws_with_tasks(tmp_path):
    from planwit import paths

    ws = tmp_path / "ws"
    (ws / paths.WORKSPACE_MARK).parent.mkdir(parents=True, exist_ok=True)
    (ws / paths.WORKSPACE_MARK).write_text("", encoding="utf-8")
    tasks = []
    for name in ("2026-11-20_가", "2026-11-21_나"):
        t = ws / "서비스A" / "과제" / name
        shutil.copytree(SAMPLE, t, ignore=shutil.ignore_patterns("3_결과물", ".planwit"))
        tasks.append(t)
    return ws, tasks


def test_service_ids_merge_and_conflict(tmp_path):
    """과제를 기준본에 합치고, 같은 화면을 다른 과제가 먼저 바꿨으면 충돌로 알린다."""
    from planwit import paths, service, validate as v

    ws, (a, b) = _ws_with_tasks(tmp_path)
    (paths.docs(a) / "05_기능명세_정책.md").write_text(
        "# 정책\n\n## POL-001 로그인 실패 제한\n\n| 항목 | 값 |\n|---|---|\n| 횟수 | 5회 |\n", encoding="utf-8")
    # 두 과제가 같은 번호를 새로 만들면 validate가 잡는다
    problems, notes = v.check_all(a)
    assert any("SCR-020" in p and "next-id" in p for p in problems)
    svc = ws / "서비스A"
    assert service.next_id(svc) == "SCR-040" and service.next_id(svc, "POL").startswith("POL-")

    done, conflicts = service.merge(a)
    assert done and not conflicts
    assert (paths.service(svc) / "화면" / "SCR-010.md").is_file()
    base_text = (paths.service(svc) / "화면" / "SCR-010.md").read_text(encoding="utf-8")
    assert "· 기준" in base_text and "changed: true" not in base_text and "- 반영: 2026-11-20_가" in base_text
    assert (paths.service(svc) / "정책.md").is_file() and (paths.service(svc) / "화면목록.md").is_file()

    # 기준본에서 가져오지 않고 같은 화면을 고친 과제는 충돌
    done, conflicts = service.merge(b, dry_run=True)
    assert conflicts == [] or all("기준본" in c for c in conflicts)

    # 기준본에서 가져와 고치면 합쳐진다
    (find := (paths.docs(b) / "03_화면설계" / "SCR-010.md")).unlink()
    service.base(b, "SCR-010")
    text = find.read_text(encoding="utf-8")
    assert "- 기준본: " in text and "· 변경" in text
    find.write_text(text.replace("로그인", "로그인하기", 1), encoding="utf-8")
    done, conflicts = service.merge(b, dry_run=True)
    assert not any("SCR-010" in c for c in conflicts)
    assert any("SCR-010" in d and "갱신" in d for d in done)

    # 그사이 다른 과제가 기준본을 바꾸면 충돌
    svc_file = paths.service(svc) / "화면" / "SCR-010.md"
    svc_file.write_text(svc_file.read_text(encoding="utf-8").replace("로그인", "로그인 화면", 1), encoding="utf-8")
    done, conflicts = service.merge(b, dry_run=True)
    assert any("SCR-010" in c and "먼저 바꿨" in c for c in conflicts)



def test_feedback_store_and_hook_message(tmp_path):
    from planwit import feedback

    ws = tmp_path / "ws"
    task = ws / "과제" / "2026-11-24_예시"
    task.mkdir(parents=True)
    a = feedback.add(task, {"screen": "SCR-010", "cid": "c3", "label": "버튼", "kind": "메모", "text": "위로 올려 줘"})
    b = feedback.add(task, {"screen": "SCR-010", "kind": "문구", "before": "확인", "after": "저장하기"})
    assert (a["id"], b["id"]) == ("F001", "F002")
    assert len(feedback.pending(task)) == 2 and "새 피드백 2개" in feedback.pending_message(ws)
    feedback.set_status(task, "F001", "질문", "어디까지 올릴까요?")
    feedback.set_status(task, "F002", "반영함")
    assert feedback.pending(task) == [] and feedback.pending_message(ws) == ""
    feedback.reply(task, "F001", "상단바 바로 아래")
    item = feedback.pending(task)[0]
    assert item["id"] == "F001" and item["reply"] == "상단바 바로 아래" and item["answer"] == "어디까지 올릴까요?"


def test_plan_page_script_is_valid_js(workspace):
    """기획안의 스크립트가 문법 오류 없이 읽히는지 (node가 있을 때만)."""
    import re
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    from planwit import build_proto

    out = build_proto.build(_task(workspace), capture=False)[0]
    js = re.findall(r"<script>(.*?)</script>", out.read_text(encoding="utf-8"), re.S)[-1]
    f = out.parent / "check.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_services_are_separate_and_old_layout_moves(tmp_path):
    """서비스마다 번호와 기준본이 따로이고, 예전 구조는 서비스 폴더 아래로 옮겨진다."""
    from planwit import paths, service

    ws, (a, b) = _ws_with_tasks(tmp_path)
    other = ws / "서비스B" / "과제" / "2026-11-22_다"
    shutil.copytree(SAMPLE, other, ignore=shutil.ignore_patterns("3_결과물", ".planwit"))
    # 서비스B는 서비스A와 같은 번호를 써도 겹치지 않는다
    assert service.overlaps(other) == ([], [])
    assert paths.service_root_of(other) == ws / "서비스B"
    assert paths.workspace_of(other) == ws.resolve()
    assert set(p.name for p in paths.all_tasks(ws)) == {"2026-11-20_가", "2026-11-21_나", "2026-11-22_다"}

    old = tmp_path / "old"
    (old / "회사").mkdir(parents=True)
    (old / paths.WORKSPACE_MARK).write_text("", encoding="utf-8")
    shutil.copytree(SAMPLE, old / "과제" / "2026-11-20_예전", ignore=shutil.ignore_patterns("3_결과물", ".planwit"))
    (old / "서비스" / "화면").mkdir(parents=True)
    moved = paths.migrate_workspace(old, "앱")
    assert (old / "앱" / "과제" / "2026-11-20_예전").is_dir() and (old / "앱" / "기준본" / "화면").is_dir()
    assert not (old / "과제").exists() and not (old / "서비스").exists() and moved


def test_cli_build_all_makes_plan_and_dev_view_on_request(workspace):
    """build all은 기획안만, build dev를 한 번 하면 그 뒤로 개발 명세도 함께 갱신된다."""
    from planwit import cli, paths

    task = _task(workspace)
    assert cli.main(["build", "all", str(task)]) == 0
    assert paths.plan(task).is_file() and not paths.dev_spec(task).exists()
    assert '"__dev__": false' in paths.plan(task).read_text(encoding="utf-8")
    assert cli.main(["build", "dev", str(task)]) == 0
    assert cli.main(["build", "all", str(task)]) == 0
    assert paths.dev_spec(task).is_file()



def test_text_feedback_applies_to_source(workspace):
    """문구 수정 피드백은 화면 원본의 label에 바로 반영되고, 글자가 맞지 않으면 하지 않는다."""
    from planwit import feedback
    from planwit.screens import load_screens

    task = _task(workspace)
    s = next(x for x in load_screens(task) if x.id == "SCR-010")
    leaf = next(c for top in s.components for c in top.walk() if c.label and not c.children)
    ok = feedback.apply_text(task, {"kind": "문구", "screen": "SCR-010", "cid": leaf.id, "before": leaf.label, "after": "새 문구, 쉼표: 포함"})
    assert ok
    s2 = next(x for x in load_screens(task) if x.id == "SCR-010")
    assert next(c for top in s2.components for c in top.walk() if c.id == leaf.id).label == "새 문구, 쉼표: 포함"
    assert not feedback.apply_text(task, {"kind": "문구", "screen": "SCR-010", "cid": leaf.id, "before": "다른 글자", "after": "x"})


def test_feedback_edit_delete_only_before_applied(tmp_path):
    from planwit import feedback

    task = tmp_path / "t"
    task.mkdir()
    a = feedback.add(task, {"screen": "SCR-010", "kind": "메모", "text": "처음"})
    b = feedback.add(task, {"screen": "SCR-010", "kind": "메모", "text": "둘째"})
    assert feedback.edit(task, a["id"], "고친 의견")["text"] == "고친 의견"
    feedback.set_status(task, b["id"], "반영함")
    assert feedback.edit(task, b["id"], "x") is None and not feedback.delete(task, b["id"])
    assert feedback.delete(task, a["id"])
    assert [i["id"] for i in feedback.load(task)] == [b["id"]]


def test_description_edit_writes_source(workspace):
    from planwit import feedback
    from planwit.screens import load_screens

    task = _task(workspace)
    s = next(x for x in load_screens(task) if x.descriptions)
    no = s.descriptions[0].no
    assert feedback.apply_desc(task, s.id, no, "노출: 항상 보인다\n동작: 누르면 SCR-020으로 이동한다 | 바로")
    s2 = next(x for x in load_screens(task) if x.id == s.id)
    assert s2.descriptions[0].text == "노출: 항상 보인다<br>동작: 누르면 SCR-020으로 이동한다 / 바로"
    assert not feedback.apply_desc(task, s.id, "99", "x")


def test_quality_gate_catches_missing_essentials(workspace):
    """방향 정의의 빠진 장, 설명 없는 입력 요소, 모호한 말, 흐름에 없는 화면을 잡는다."""
    from planwit import quality
    from planwit.screens import load_screens

    task = _task(workspace)
    summ = task / "00_과제요약.md"
    summ.write_text(summ.read_text(encoding="utf-8") + "\n## 진행 단계\n\n| 순서 | 단계 | 상태 |\n|---|---|---|\n| 2 | 방향 정의 | 대기 |\n", encoding="utf-8")
    docs = task / "2_기획문서"
    (docs / "02_방향정의.md").write_text("# 방향 정의\n\n## 1. 한 문장\n\n## 2. 차별점\n", encoding="utf-8")
    (docs / "03_유저플로우.md").write_text("SCR-010 → SCR-020\n", encoding="utf-8")
    f = docs / "03_화면설계" / "SCR-020.md"
    f.write_text(f.read_text(encoding="utf-8").replace("    marker: 2\n", "", 1).replace("| 2 | 휴대폰 번호 | 필수. 숫자만 10~11자리 | |\n", "")
                 .replace("3분부터 줄어듦", "적절히 줄어듦"), encoding="utf-8")
    problems, _ = quality.check(task, load_screens(task))
    text = "\n".join(problems)
    assert "'출시 발표문' 장이 없어요" in text and "'위험' 장이 없어요" in text
    assert "c3)에 번호와 설명이 없어요" in text
    assert "모호한 말('적절히')" in text
    assert "SCR-030: 유저 플로우에 없는 화면" in text


def test_quality_gate_flow_first(workspace):
    """유저 플로우 단계가 있으면 화면보다 먼저, 페르소나·흐름 대안·메뉴 구조·화면 목록이 있어야 한다."""
    from planwit import quality
    from planwit.screens import load_screens

    task = _task(workspace)
    summ = task / "00_과제요약.md"
    summ.write_text(summ.read_text(encoding="utf-8") + "\n## 진행 단계\n\n| 순서 | 단계 | 상태 |\n|---|---|---|\n| 2 | 유저 플로우 / 메뉴 구조 | 대기 |\n| 3 | 화면 설계 | 대기 |\n", encoding="utf-8")
    docs = task / "2_기획문서"
    for f in docs.glob("*유저플로우*.md"):
        f.unlink()
    problems, _ = quality.check(task, load_screens(task))
    assert any("화면보다 유저 플로우를 먼저" in p for p in problems)

    (docs / "02_유저플로우.md").write_text("# 유저 플로우\n\n## 1. 페르소나\n\n## 5. 흐름\n\nSCR-010 SCR-020 SCR-030\n", encoding="utf-8")
    text = "\n".join(quality.check(task, load_screens(task))[0])
    assert "'흐름 대안' 장이 없어요" in text and "'메뉴 구조' 장이 없어요" in text and "'화면 목록' 장이 없어요" in text
    assert "'페르소나' 장이 없어요" not in text
