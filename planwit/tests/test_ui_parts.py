"""앱 기본 UI: 상태바, 하단 고정 주요 버튼, 설정줄, 세그먼트, 시간선택, 어두운 화면."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from planwit import build_proto  # noqa: E402
from planwit.screens import parse_screen  # noqa: E402

SCREEN = """# SCR-500 루틴 · 신규

- 플랫폼: 앱

## 구성

```yaml
frame: mobile
theme: dark
components:
  - {id: c1, type: 상단바, label: 루틴, left: [뒤로]}
  - {id: c2, type: 세그먼트, items: [아침, 저녁], selected: 1}
  - {id: c3, type: 설정줄, label: 잠드는 시각, value: "PM 11:30"}
  - {id: c4, type: 설정줄, label: 알림, selected: 1}
  - {id: c5, type: 시간선택, label: "PM 11:30"}
  - {id: c6, type: 기본버튼, label: 저장}
```
"""


def test_app_parts_render(tmp_path):
    f = tmp_path / "SCR-500.md"
    f.write_text(SCREEN, encoding="utf-8")
    s = parse_screen(f)
    html = build_proto.screen_markup(s, {s.id: s})
    assert 'class="statusbar"' in html
    assert 'class="screen dark"' in html
    assert '<span class="s on">저녁</span>' in html
    assert '<span class="val">PM 11:30<i class="chev"></i></span>' in html
    assert 'data-cid="c4"' in html and 'switch on' in html
    assert '<i class="c">11</i>' in html and '<i class="c">30</i>' in html and '<i class="on">PM</i>' in html
    # 맨 끝 기본버튼은 하단에 고정
    assert '<footer class="cta"><button class="btn primary" data-cid="c6"' in html
