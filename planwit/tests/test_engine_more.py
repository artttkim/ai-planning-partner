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
    shutil.copytree(SAMPLE, task, ignore=shutil.ignore_patterns("회사양식", "개발용", ".planwit"))
    return tmp_path


def _task(ws):
    return ws / "과제" / SAMPLE.name


def test_build_dev(workspace):
    files = build_dev.build(_task(workspace))
    data = yaml.safe_load((_task(workspace) / "개발용" / "화면" / "SCR-010.yaml").read_text(encoding="utf-8"))
    assert len(files) == 4
    assert data["status"] == "changed"
    assert data["policies"] == ["POL-001"]
    btn = next(c for c in data["components"] if c["id"] == "c6")
    assert btn["type"] == "button.primary" and "활성화" in btn["behavior"]


def test_validate_sample_is_clean(workspace):
    assert validate.check(_task(workspace)) == []


def test_validate_finds_missing_screen(workspace):
    (_task(workspace) / "원본" / "03_화면설계" / "SCR-030.md").unlink()
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
