# Design — S-ANGEL

성균관대학교 공식 학교발전 홍보대사 S-ANGEL 운영 도구의 디자인 규칙. 구현: `s_angel/static/css/sangel.css`, `s_angel/static/js/sangel.js`, `s_angel/templates/layouts/`.

## 원칙
- **기존 흰색 + 네이비 정체성 유지.** 배경 #F9FAFB, 흰 카드 + #E5E7EB 테두리 + 옅은 그림자, Pretendard. 그라데이션·보라색 금지.
- **버튼(A안·부드러운 단색, 둥근 네모 12px):** 핵심 동작(등록·저장·최종 확정·확인창 확인) = 단색 #3A57A8 / 반복 동작(신청하기·추첨 실행·명단 검토) = 연한 네이비(navy-50 바탕, navy-200 테두리, navy-700 글자) / 보조 = 흰 바탕 회색 테두리 / 위험 = 연한 빨강.
- **리퀴드 글래스는 떠 있는 레이어에만**: 상단 앱바, 모바일 하단 탭바, 메뉴, 바텀시트(확인창), 토스트, 모바일 sticky 액션바. 일반 카드·버튼·폼에는 쓰지 않는다.
- 다크모드 없음.
- 모바일 우선: 터치 타깃 44px 이상, 입력 폰트 16px, 가로 스크롤 금지(표는 `.table--stack` 또는 리스트).

## 로고
- `static/images/logo.png` 원본, `logo-mark-lg.webp`(로그인), `logo-mark.webp`(앱바), `apple-touch-icon.png`. 워드마크 "S-ANGEL"은 Pretendard 800 고딕, 네이비 단색.

## 내비게이션
- 모바일: 하단 글래스 탭바(선택 탭 아래 유리 렌즈) — 부원: 홈 · 캘린더 · (회계) / 운영진: 홈 · 캘린더 · 회계 · 특별추첨 · 관리. 내 정보는 프로필 메뉴.
- 상단 바: 스크롤에 1:1로 연동해 떠 있는 유리 캡슐로 축소(`--p` 0→1).
- 데스크탑: 앱바 안 pill 내비. 활성 탭은 URL 기반(`nav_section`).
- 같은 목적지로 가는 버튼을 한 화면에 중복하지 않는다. 탭으로 오는 페이지엔 뒤로가기 링크를 두지 않는다(그 외는 "‹ 홈").
- 저장/확정 sticky 바가 있는 화면에선 모바일 탭바를 숨긴다.
- 위험한 동작(삭제·권한 변경)은 ⋯ 행 메뉴 안에 두고 확인 시트를 거친다.

## 상태 색
- 모집 중 info, 마감·검토 중 neutral, **확정 green**, 당첨·수입 green, 미당첨·지출 red, 대기·추첨 전만 amber, 행사·본인·1로 초기화 navy-soft(`.chip--navy`). 진행 카운트는 navy, 목표 초과 시만 경고.

## 문구
- 합니다체로 통일. 인사·홍보성 문구 금지.
- 용어: 추첨 대상 = 의전, 회계 묶음 = 행사, 신청(지원 X), 회계 기간 = 연도(기수는 부원 기수에만). 구성원 = 부원.
- 아이콘은 Font Awesome 6 Free **자체 호스팅 부분집합**(`static/vendor/fa/`). 새 아이콘을 쓰면 부분집합 재생성 필요. 이모지 금지.

## 컴포넌트
`.page(--narrow|--wide) .page-head .section`, `.panel`, `.list-row`, `.btn--primary|secondary|ghost|danger|danger-ghost`, `.chip--*`, `.field .input .select .segmented .stepper .form-actions(--sticky)`, `.table(--stack)`, `.stats .kv`, `.alert .empty`, `.menu.row-menu`, JS `SA.toast / SA.confirm / SA.ajax`, `form[data-confirm][data-danger]`, `form[data-busy]`.
