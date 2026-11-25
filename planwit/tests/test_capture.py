"""기존 화면 캡처를 바탕으로 쓰는 화면 (capture)."""
import shutil
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from planwit import build_proto, quality  # noqa: E402
from planwit.screens import capture_file, load_screens  # noqa: E402

SAMPLE = Path(__file__).parent / "samples" / "2026-11-20_로그인_정책_개선"

CAPTURE_SCREEN = """# SCR-010 로그인 · 변경

- 경로: 홈 > 로그인
- 관련 기능: FR-001, FR-003
- 플랫폼: 앱
- 참고 화면: 로그인 (지금 화면)

## 구성

```yaml
frame: mobile
capture: 로그인.png
components:
  - {id: c5, type: 오류문구, label: 아이디 또는 비밀번호가 맞지 않아요. (4/5회), changed: true, marker: 2, x: 16, y: 300, w: 328, h: 24}
  - {id: c6, type: 기본버튼, label: 로그인, marker: 1, x: 16, y: 340, w: 328, h: 48}
```

## 설명

| No | 항목 | 설명 | 정책 |
|---|---|---|---|
| 1 | 로그인 버튼 | 아이디와 비밀번호가 모두 입력되면 누를 수 있다. 누르면 추가 인증(SCR-020)으로 이동한다 | |
| 2 | 실패 안내 | 실패 횟수를 함께 보여 준다. 5회 실패하면 추가 인증(SCR-020)으로 이동한다 | POL-001 |
"""


def _png(w=4, h=8, rect=None) -> bytes:
    """회색 바탕 그림. rect=(x0, y0, x1, y1)이면 그 자리에 검은 사각형."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    def row(y):
        px = [b"\x00\x00\x00" if rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3] else b"\xcc\xcc\xcc"
              for x in range(w)]
        return b"\x00" + b"".join(px)
    raw = b"".join(row(y) for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture
def task(tmp_path):
    svc = tmp_path / "서비스A"
    t = svc / "과제" / SAMPLE.name
    shutil.copytree(SAMPLE, t, ignore=shutil.ignore_patterns("3_결과물", ".planwit"))
    (t / "2_기획문서" / "03_화면설계" / "SCR-010.md").write_text(CAPTURE_SCREEN, encoding="utf-8")
    maps = svc / "디자인" / "화면지도"
    maps.mkdir(parents=True)
    (maps / "로그인.png").write_bytes(_png())
    return t


def _scr010(task):
    return next(s for s in load_screens(task) if s.id == "SCR-010")


def test_capture_is_found_in_service_map(task):
    s = _scr010(task)
    assert s.capture == "로그인.png"
    assert capture_file(s) == task.parents[1] / "디자인" / "화면지도" / "로그인.png"


def test_capture_screen_draws_image_and_only_changed_parts(task):
    screens = load_screens(task)
    by_id = {s.id: s for s in screens}
    html = build_proto.screen_markup(by_id["SCR-010"], by_id, build_proto._Nav(screens))
    assert 'class="cap-wrap"' in html and "--cap:url(data:image/png;base64," in html
    assert html.count('class="cap-slice"') == 1  # 넣거나 뺀 영역이 없으면 캡처 한 장 그대로
    # 바뀐 요소는 캡처 위에 새로 그린다
    assert 'class="cap-patch" data-changed="1" data-cid="c5" data-marker="2"' in html
    assert "(4/5회)" in html
    # 안 바뀐 요소는 보이지 않는 상자: 번호와 이동만
    assert 'class="cap-hot" data-cid="c6" data-marker="1" data-go="SCR-020" data-o="16,340,328,48"' in html
    assert ">로그인</button>" not in html


def test_quality_requires_position_and_file(task):
    f = task / "2_기획문서" / "03_화면설계" / "SCR-010.md"
    f.write_text(CAPTURE_SCREEN.replace(", x: 16, y: 340, w: 328, h: 48", "").replace("로그인.png", "없음.png"),
                 encoding="utf-8")
    problems, _ = quality.check(task, load_screens(task))
    assert any("없음.png" in p for p in problems)
    assert any("(c6)에 위치" in p for p in problems)


@pytest.mark.skipif(build_proto.find_browser() is None, reason="브라우저 없음")
def test_capture_build_measures_boxes(task):
    import json
    build_proto.build(task, capture=True)
    data = json.loads(build_proto.boxes_path(task, "SCR-010").read_text(encoding="utf-8"))
    x, y, w, h = data["boxes"]["c6"]
    assert (round(x), round(y), round(w), round(h)) == (16, 340, 328, 48)
    assert data["height"] >= 720  # 4x8 캡처를 360 너비로 늘리면 높이 720


def _with(task, components: str):
    f = task / "2_기획문서" / "03_화면설계" / "SCR-010.md"
    text = CAPTURE_SCREEN.split("components:")[0] + "components:\n" + components + "\n```" + CAPTURE_SCREEN.split("```", 2)[2]
    f.write_text(text, encoding="utf-8")
    screens = load_screens(task)
    by_id = {s.id: s for s in screens}
    return build_proto.screen_markup(by_id["SCR-010"], by_id, build_proto._Nav(screens))


def test_insert_splits_capture_and_pushes_below_down(task):
    # 4x8 캡처 → 360x720. 300 자리에 40px 새 영역
    html = _with(task, """  - {id: c9, type: 안내문구, label: 새 안내, insert: true, y: 300, h: 40}
  - {id: c6, type: 기본버튼, label: 로그인, marker: 1, x: 16, y: 340, w: 328, h: 48}""")
    assert '<div class="cap-slice" style="height:300px;background-position:0 -0px"></div>' in html
    assert '<div class="cap-gap" data-y="300" style="height:40px"></div>' in html
    assert '<div class="cap-slice" style="height:420px;background-position:0 -300px"></div>' in html
    assert 'data-cid="c9" style="left:16px;top:300px;width:328px;height:40px">' in html and "새 안내" in html
    assert 'data-cid="c6" data-marker="1"' in html and "top:380px" in html  # 아래 요소는 40px 밀림


def test_grow_and_remove_adjust_only_the_band(task):
    html = _with(task, """  - {id: c5, type: 오류문구, label: 두 줄 안내, changed: true, x: 16, y: 200, w: 328, h: 20, new_h: 44}
  - {id: c7, type: 텍스트링크, label: 없앨 링크, removed: true, y: 500, h: 30}
  - {id: c6, type: 기본버튼, label: 로그인, marker: 1, x: 16, y: 600, w: 328, h: 48}""")
    assert 'data-cid="c5"' in html and "height:44px" in html
    assert '<div class="cap-gap" data-y="220" style="height:24px"></div>' in html
    assert '<div class="cap-slice" style="height:280px;background-position:0 -220px"></div>' in html  # 220~500
    assert '<div class="cap-slice" style="height:190px;background-position:0 -530px"></div>' in html  # 530~720
    assert "top:594px" in html  # 600 + 24 - 30
    assert 'data-cid="c7"' not in html


def test_image_size_reads_png_and_jpeg(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(_png(7, 3))
    assert build_proto.image_size(p) == (7, 3)
    jpg = tmp_path / "a.jpg"
    jpg.write_bytes(bytes.fromhex("ffd8ffe00004") + b"ab" + bytes.fromhex("ffc000110800200010") + bytes(20))
    assert build_proto.image_size(jpg) == (16, 32)


@pytest.mark.skipif(build_proto.find_browser() is None, reason="브라우저 없음")
def test_box_snaps_to_element_in_capture(task):
    import json
    maps = task.parents[1] / "디자인" / "화면지도"
    (maps / "로그인.png").write_bytes(_png(360, 720, rect=(20, 100, 120, 140)))
    _with(task, "  - {id: c6, type: 기본버튼, label: 로그인, marker: 1, x: 25, y: 106, w: 100, h: 40}")
    build_proto.build(task, capture=True)
    data = json.loads(build_proto.boxes_path(task, "SCR-010").read_text(encoding="utf-8"))
    x, y, w, h = data["boxes"]["c6"]
    assert (round(x), round(y), round(w), round(h)) == (18, 98, 104, 44)  # 사각형 테두리 + 2px
