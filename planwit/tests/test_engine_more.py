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
    files = build_dev.build(_task(workspace))
    data = yaml.safe_load((_task(workspace) / "3_결과물" / "개발용" / "SCR-010.yaml").read_text(encoding="utf-8"))
    assert len(files) == 4
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
    (task / "결정기록.md").write_text("# 결정 기록\n", encoding="utf-8")
    (task / "개발용" / "화면" / "SCR-010.yaml").write_text("id: SCR-010\n", encoding="utf-8")
    moved = paths.migrate(task)
    assert moved
    for name in ["00_과제요약.md", "01_검수함.md", "02_결정기록.md", "1_입력자료", "2_기획문서/04_화면설계",
                 "3_결과물/개발용/SCR-010.yaml"]:
        assert (task / name).exists(), name
    assert not (task / "개발용").exists()
    text = (task / "00_과제요약.md").read_text(encoding="utf-8")
    assert "`2_기획문서/02_영향분석.md`" in text and "`3_결과물/개발용/`" in text
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
