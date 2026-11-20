import shutil
import sys
from pathlib import Path

import pytest
from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from planwit import build_pptx, snapshot  # noqa: E402
from planwit.screens import load_screens  # noqa: E402

SAMPLE = Path(__file__).parent / "samples" / "2026-11-20_로그인_정책_개선"


@pytest.fixture
def task(tmp_path):
    dst = tmp_path / SAMPLE.name
    shutil.copytree(SAMPLE, dst, ignore=shutil.ignore_patterns("회사양식", ".planwit"))
    return dst


def test_parse_screens(task):
    screens = load_screens(task)
    assert [s.id for s in screens] == ["SCR-010", "SCR-020", "SCR-020-P1"]
    login = screens[0]
    assert login.status == "변경"
    assert login.requirements == ["FR-001", "FR-003"]
    assert login.components[4].changed and login.components[4].marker == 2
    assert login.descriptions[1].policy == "POL-001"


def test_build_creates_named_shapes(task):
    out = build_pptx.build(task, today="2026.11.20")
    assert out.name == "화면설계서_로그인정책개선_v0.1.pptx"
    prs = Presentation(str(out))
    assert len(prs.slides) == 3 + 3  # 표지, 변경 이력, 화면 목록 + 화면 3개
    names = {sh.name for slide in prs.slides for sh in slide.shapes}
    for expected in ["SCR-010/c5", "SCR-010/c5/changed", "SCR-010/marker/2", "SCR-010/desc", "SCR-020-P1/c2"]:
        assert expected in names


def test_snapshot_reads_back_same_text(task):
    out = build_pptx.build(task, today="2026.11.20")
    snapshot.record(task, out)
    texts = snapshot.pptx_texts(out)
    assert texts["SCR-010/c5"] == "아이디 또는 비밀번호가 맞지 않아요. (4/5회)"
    assert texts["SCR-010/desc/2"].startswith("실패 안내 | 실패 횟수를 함께 표시")
    assert (task / ".planwit" / "manifest.json").exists()
