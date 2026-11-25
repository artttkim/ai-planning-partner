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


def _png(w=4, h=8) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\xcc\xcc\xcc" * w for _ in range(h))
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
    assert 'class="cap-img"' in html and "data:image/png;base64," in html
    # 바뀐 요소는 캡처 위에 새로 그린다
    assert 'class="cap-patch" data-changed="1" data-cid="c5" data-marker="2"' in html
    assert "(4/5회)" in html
    # 안 바뀐 요소는 보이지 않는 상자: 번호와 이동만
    assert 'class="cap-hot" data-cid="c6" data-marker="1" data-go="SCR-020"' in html
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
