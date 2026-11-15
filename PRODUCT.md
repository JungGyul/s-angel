# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **부원 (주 사용자):** S-ANGEL 홍보대사 부원. 대부분 휴대폰으로 접속해 의전 활동에 신청/취소하고, 추첨 결과(당첨/미당첨)와 S-ANGEL 캘린더를 확인한다. 짧고 잦은 방문, 이동 중 한 손 조작.
- **운영진 (staff):** 의전 활동 생성, 일반 추첨·특별추첨(여러 날짜 묶음) 실행, 명단 검토·확정, 부원 승인/가중치 관리, 통계 확인, 캘린더 일정 관리. 휴대폰과 PC를 모두 사용.
- **회계 열람자 (can_view_accounting):** 기수(연도)별 회계 장부와 행사별 수입/지출 열람.

## Product Purpose
성균관대학교 공식 학교발전 홍보대사 S-ANGEL의 내부 운영 도구. 의전 활동 신청과 공정한 가중치 기반 추첨, 회계 장부, S-ANGEL 일정을 한곳에서 관리한다. 성공 = 부원이 몇 초 안에 신청/결과를 확인하고, 운영진이 실수 없이 추첨·확정을 끝내는 것.

## Positioning
떨어진 사람에게 다음 기회를 더 주는 가중치 추첨(탈락 시 +1, 당첨 시 초기화)과, 여러 날짜를 하나로 묶어 한 번에 정산하는 특별추첨이 핵심 메커니즘이다.

## Operating Context
- Django 5.1 서버 렌더링 + 템플릿, 일부 fetch 기반 비동기 액션(신청/취소/추첨). Render 배포.
- 승인제 회원가입(운영진 승인 후 이용), 성별 슬롯(남/여) 구분 모집.
- 회계: 기수(BudgetYear) → 행사(AccountingEvent) → 거래(Transaction), 엑셀 내보내기.
- 캘린더: S-ANGEL 일정(ClubSchedule) 월간 보기, 운영진 편집.

## Capabilities and Constraints
- 한국어 전용 UI. 기존 URL 이름/뷰 계약은 유지.
- DB 스키마 변경은 최소화(필요 시 추가 마이그레이션만).
- 외부 리소스는 CDN(Font Awesome, Pretendard 등) 사용 가능.

## Brand Commitments
- 이름: S-ANGEL (대문자 표기). 정식 명칭: 성균관대학교 공식 학교발전 홍보대사 ("학생홍보대사", "동아리" 등으로 표기하지 않는다). 구성원 호칭은 "부원" 또는 "엔젤".
- 네이비(#1E3A8A 계열) 정체성 유지. 사용자 지정: 라이트 기반 리퀴드 글래스, 다크모드 지원.

## Evidence on Hand
- 실제 데이터는 운영 DB에만 존재. 로고/사진 에셋 없음(파비콘만). 가짜 수치나 후기를 만들지 않는다.

## Product Principles
1. 모바일 우선: 엄지 하나로 신청·확인이 끝나야 한다.
2. 상태가 곧 정보: 신청 가능/마감/추첨 완료/확정/당첨 여부는 한눈에 구분되어야 한다.
3. 되돌릴 수 없는 작업(확정, 삭제, 추첨)은 명확한 확인과 결과 피드백을 거친다.
4. 장식보다 사용성: 유리 질감은 위계와 깊이를 위해서만 쓴다.

## Accessibility & Inclusion
WCAG AA 대비, 44px 이상 터치 타깃, 키보드 포커스, prefers-reduced-motion / prefers-reduced-transparency 대응.
