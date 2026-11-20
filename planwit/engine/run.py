"""플랜윗 엔진 진입점.

사용법: python run.py <명령> [인자]
이 파일은 어느 폴더에서 실행해도 engine 패키지를 찾을 수 있게 경로를 맞춘다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from planwit.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
