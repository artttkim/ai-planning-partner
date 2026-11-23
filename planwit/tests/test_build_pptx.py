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
    assert [s.id for s in screens] == ["SCR-010", "SCR-020", "SCR-020-P1", "SCR-030"]
    login = screens[0]
    assert login.status == "변경"
    assert login.requirements == ["FR-001", "FR-003"]
    assert login.components[4].changed and login.components[4].marker == 2
    assert login.descriptions[1].policy == "POL-001"


def test_build_creates_named_shapes(task):
    out = build_pptx.build(task, today="2026.11.20")
    assert out.name == "화면설계서_로그인정책개선_v0.1.pptx"
    prs = Presentation(str(out))
    assert len(prs.slides) == 3 + 4  # 표지, 변경 이력, 화면 목록 + 화면 4개
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


NESTED = """# SCR-090 방 상세 · 신규

- 관련 기능: FR-001

## 구성

```yaml
frame: mobile
components:
  - {id: c1, type: 상단바, label: 방, left: [뒤로]}
  - id: c2
    type: 행
    children:
      - {id: c2-1, type: 보조버튼, label: 복사, size: small}
      - {id: c2-2, type: 기본버튼, label: 공유하기, marker: 1}
  - {id: c3, type: 하단탭바, items: [알람, 다함께], selected: 1}
```

## 설명

| No | 항목 | 설명 | 정책 |
|---|---|---|---|
| 1 | 공유하기 | 공유 시트를 연다 | |
"""

POPUP = """# SCR-090-P1 확인 · 신규

- 관련 기능: FR-001

## 구성

```yaml
frame: mobile
components:
  - id: c1
    type: 팝업
    label: "나갈까요?\n나가면 알람이 울리지 않아요."
    children:
      - {id: c2, type: 기본버튼, label: 나가기, marker: 1}
```

## 설명

| No | 항목 | 설명 | 정책 |
|---|---|---|---|
| 1 | 나가기 | 나간다 | |
"""


def test_nested_components_and_popup_background(task):
    folder = task / "원본" / "03_화면설계"
    (folder / "SCR-090.md").write_text(NESTED, encoding="utf-8")
    (folder / "SCR-090-P1.md").write_text(POPUP, encoding="utf-8")
    screen = {s.id: s for s in load_screens(task)}["SCR-090"]
    assert screen.components[1].children[1].marker == 1
    assert screen.components[2].items == ["알람", "다함께"]
    out = build_pptx.build(task, today="2026.11.20")
    names = {sh.name for slide in Presentation(str(out)).slides for sh in slide.shapes}
    for expected in ["SCR-090/c2-1", "SCR-090/c2-2", "SCR-090/marker/1", "SCR-090/c3/2",
                     "SCR-090-P1/c2", "SCR-090-P1/dim", "bg-SCR-090-c2-2"]:
        assert expected in names
