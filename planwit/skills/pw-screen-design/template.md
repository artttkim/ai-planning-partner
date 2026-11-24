# SCR-010 <화면명> · <신규|변경|참고>

- 경로: <메뉴 경로. 예: 홈 > 로그인>
- 관련 기능: FR-001, FR-003
- 플랫폼: <앱|웹>

## 구성

```yaml
frame: mobile          # mobile(360x800) 또는 web(1440x1024). 위치(x, y)는 적지 않는다
components:
  - id: c1
    type: 상단바
    label: <화면 제목>
    left: [뒤로]
    right: [더보기]
  - id: c2
    type: 카드
    marker: 1
    children:
      - id: c2-1
        type: 행
        children:
          - {id: c2-1-1, type: 배지, label: <배지 글자>}
          - {id: c2-1-2, type: 제목, label: <제목>}
      - {id: c2-2, type: 본문, label: <본문>}
  - id: c3
    type: 행               # 나란히 놓이는 요소
    children:
      - {id: c3-1, type: 보조버튼, label: <버튼>, marker: 2}
      - {id: c3-2, type: 기본버튼, label: <버튼>, marker: 3}
  - id: c4
    type: 목록             # 예시 데이터 2~3줄
    children:
      - id: c4-1
        type: 행
        children:
          - {id: c4-1-1, type: 아바타}
          - {id: c4-1-2, type: 본문, label: <이름>}
          - {id: c4-1-3, type: 텍스트링크, label: <동작>}
  - id: c5
    type: 오류문구
    label: <실제 문구>
    changed: true          # 기존 화면에서 바뀐 요소만
  - id: c6
    type: 하단탭바
    items: [<탭1>, <탭2>, <탭3>]
    selected: 0
```

## 설명

| No | 항목 | 설명 | 정책 |
|---|---|---|---|
| 1 | <요소 이름> | <동작, 조건, 값, 문구> | |
| 2 | <요소 이름> | <동작, 조건, 값, 문구> | POL-001 |
| 3 | <요소 이름> | <동작, 조건, 값, 문구> | |

## 비고

<이 화면에만 해당하는 짧은 참고, 두 줄 이내. 상태, 예외, 규칙은 쓰지 않는다 (SKILL.md 3장). 없으면 이 장을 지운다>
