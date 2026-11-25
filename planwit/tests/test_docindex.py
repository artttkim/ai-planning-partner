"""자료 폴더 색인 (내용은 읽지 않고 이름, 날짜, 크기만)."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from planwit import docindex  # noqa: E402
from planwit.extract import skim  # noqa: E402


def _touch(root: Path, rel: str, age_days: float = 0, size: int = 100):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def test_categories_versions_and_noise(tmp_path):
    src = tmp_path / "회사자료"
    _touch(src, "01_서비스소개/타이미C 서비스 소개서.pdf")
    _touch(src, "기획/모닝루틴_PRD_v1.docx", age_days=30)
    _touch(src, "기획/모닝루틴_PRD_v2.docx", age_days=10)
    _touch(src, "기획/모닝루틴_PRD_최종.docx", age_days=1)
    _touch(src, "운영/알람 운영정책.xlsx")
    _touch(src, "02. 전략기획/사업검토_261026.pptx", age_days=3)
    _touch(src, "02. 전략기획/사업검토_261026-2.pptx", age_days=2)
    _touch(src, "02. 전략기획/사업검토_261026-3.pptx", age_days=1)
    _touch(src, "데이터/11월 리텐션 리포트.pptx")
    _touch(src, "캡처/메인.png")
    _touch(src, "기획/~$모닝루틴_PRD_최종.docx")   # 열려 있는 임시 파일
    _touch(src, "node_modules/a.md")
    _touch(src, "기획/설치파일.exe")

    files = {f["path"]: f for f in docindex.scan(src)}
    assert "기획/~$모닝루틴_PRD_최종.docx" not in files
    assert not any(p.startswith("node_modules") for p in files)
    assert not any(p.endswith(".exe") for p in files)
    assert files["01_서비스소개/타이미C 서비스 소개서.pdf"]["category"] == "서비스 소개"
    assert files["운영/알람 운영정책.xlsx"]["category"] == "정책"
    assert files["데이터/11월 리텐션 리포트.pptx"]["category"] == "지표"
    assert files["캡처/메인.png"]["category"] == "화면 캡처"

    reps = docindex._groups(list(files.values()))
    prd = [r for r in reps if "PRD" in r["path"]]
    review = [r for r in reps if "사업검토" in r["path"]]
    assert len(review) == 1 and review[0]["path"].endswith("-3.pptx") and review[0]["versions"] == 3
    assert len(prd) == 1 and prd[0]["path"] == "기획/모닝루틴_PRD_최종.docx" and prd[0]["versions"] == 3


def test_build_writes_index_and_reports_changes(tmp_path):
    src = tmp_path / "회사자료"
    svc = tmp_path / "ws" / "타이미C"
    _touch(src, "기획/수면 기능 기획서.pptx")
    md, info = docindex.build(src, svc)
    assert md == svc / "서비스지식" / "자료색인.md"
    text = md.read_text(encoding="utf-8")
    assert "### 기획서 (1)" in text and "기획/수면 기능 기획서.pptx" in text
    assert "새로 생기거나 바뀐" not in text  # 첫 색인

    _touch(src, "지표/수면 KPI.xlsx")
    md, info = docindex.build(src, svc)
    assert info["changed"] == 1
    assert "지표/수면 KPI.xlsx" in md.read_text(encoding="utf-8").split("새로 생기거나 바뀐 파일")[1]

    hits = docindex.find(svc, ["수면"])
    assert {h["path"] for h in hits} == {"기획/수면 기능 기획서.pptx", "지표/수면 KPI.xlsx"}
    assert Path(hits[0]["full"]).is_file()


def test_skim_keeps_headings_and_limits_length():
    text = "# 서비스 소개\n" + "본문 문장입니다. " * 500 + "\n## 핵심 지표\n" + "내용. " * 500
    out = skim(text, 600)
    assert "# 서비스 소개" in out and "## 핵심 지표" in out
    assert len(out) < 800
