# 플랜윗 (PLANWIT)

함께 기획하는 AI 파트너. 기획자가 PRD를 주면 상세 기획 산출물(화면 설계서, 정책서, 개발용 명세)을 단계별로 만들고, 기획자에게 꼭 필요한 것만 검수받습니다.

## 설치

Claude Code 채팅창에 아래 두 줄을 차례로 입력합니다.

```
/plugin marketplace add artttkim/ai-planning-partner
/plugin install planwit@ai-planning-partner
```

파일을 만들려면 Python 3.11 이상이 필요합니다. 설치할 때 "Add python.exe to PATH"를 체크하세요.

## 처음 설정

작업 공간으로 쓸 빈 폴더를 Claude Code에서 열고 아래를 입력합니다.

```
/planwit:setup
```

## 사용

PRD 파일을 채팅창에 올리고 "상세 기획 시작해 줘"라고 말하면 됩니다.

## 구성

| 폴더 | 내용 |
|---|---|
| `skills/` | 명령 스킬과 단계별 엔진 스킬 |
| `engine/` | 파일 생성과 읽기를 맡는 Python 엔진 (`python engine/run.py doctor`) |

설계는 저장소의 `04_개발_설계.md`를 따릅니다.
