# S-ANGEL 리디자인 작업 브리프 (2026-11-15)

> ⚠️ 2차 방향 전환: "Glass Drum"(유리 캡슐·다크모드) 방향은 폐기됨. 현재 기준은 DESIGN.md(흰색+네이비, 글래스는 떠 있는 레이어만)와 docs/design-review-2.md.

메인 코디네이터: `메인-claude-3` (peer). 질문/완료 보고는 `peer say 메인-claude-3 "..."`.
백업 원본: `/Users/jung_gyul/Desktop/s-angel-page/s-angel.backup-20261115/` (git 접근 불가 → 이걸 기준으로 diff).

## 명칭
- S-ANGEL = **성균관대학교 공식 학교발전 홍보대사**. 소개·로그인 등 문구에 소속을 쓸 땐 반드시 이 명칭 사용 ("학생홍보대사"/"동아리" 금지).

## 호칭
- 구성원은 **부원** (또는 친근한 문구에서 **엔젤**). '회원', '단원', '동아리원' 금지. 단 '회원가입'은 그대로.

## 방향: "Glass Drum"
- S-ANGEL 네이비(#1E3A8A) 정체성 + 라이트 리퀴드 글래스, 다크모드 자동 지원.
- **유리(glass)는 콘텐츠 위에 떠 있는 레이어에만**: 앱바, 하단 탭바, 바텀시트, 토스트, 모바일 sticky 액션바.
  콘텐츠는 `.panel`(거의 불투명) 위에 둔다. 카드 안에 카드 중첩 금지.
- 모바일 우선: 375px 폭에서 먼저 완성. 터치 타깃 ≥44px, 입력 폰트 16px(iOS 확대 방지), 가로 스크롤 금지(표는 `.table--stack` 또는 `.table-wrap`).
- 이모지 아이콘 금지 → Font Awesome 6 (`fa-solid` / `fa-regular`). 그라데이션 텍스트 금지. 굵은 컬러 border-left 금지.
- 상태는 `.chip` 으로: 신청가능 `--open`, 마감 `--closed`, 추첨완료 `--drawn`, 확정 `--final`, 당첨 `--won`, 미당첨 `--lost`, 대기 `--pending`, 특별추첨 `--special`, 수입 `--income`, 지출 `--expense`.
- 되돌릴 수 없는 작업(삭제/확정/추첨/초기화): `<form data-confirm="질문" data-confirm-title="제목" data-confirm-ok="삭제" data-danger>` → 자동 바텀시트 확인. `window.confirm` / `alert` 직접 쓰지 말 것 (`SA.confirm`, `SA.toast` 사용).
- 일반 POST 폼은 `data-busy` 를 달면 제출 시 버튼 스피너.

## 파일
- 디자인 시스템 CSS: `s_angel/static/css/sangel.css` (상단 주석에 컴포넌트 목록). **페이지 전용 스타일이 꼭 필요하면** 템플릿 `{% block css %}<style>…</style>{% endblock %}` 에 최소한으로, 토큰(`var(--…)`)만 사용. 하드코딩 색상 금지(차트 등 불가피한 경우 제외).
- JS 런타임: `s_angel/static/js/sangel.js` (`SA.toast`, `SA.confirm`, `SA.ajax`, `SA.labelTables`).
- 레이아웃:
  - `layouts/app.html` — 로그인 후 모든 페이지. 블록: `title`, `page_title`, `page_class`(기본 `page`, 넓은 표는 `page page--wide`, 폼은 `page page--narrow`), `content`, `css`, `javascript`. 탭 활성화는 URL 기반 자동.
  - `layouts/auth.html` — 로그인/회원가입/비밀번호 재설정. 블록: `title`, `auth_title`, `auth_sub`, `content`, `auth_foot`.
  - `base.html` — 루트. 에러 페이지는 `{% extends "base.html" %}` + `content` 블록(가운데 유리 카드).
  - 메시지(`messages`)는 레이아웃이 자동 렌더링 → 템플릿에서 따로 출력하지 말 것.
- 참고 구현: `applications/dashboard.html` (메인-claude-3 작성).

## 페이지 골격 예시
```django
{% extends "layouts/app.html" %}
{% block title %}회계 장부{% endblock %}
{% block page_title %}회계{% endblock %}
{% block page_class %}page page--wide{% endblock %}
{% block content %}
<a class="back-link" href="…"><i class="fa-solid fa-chevron-left"></i>대시보드</a>
<header class="page-head">
  <div class="page-head__text">
    <h1 class="page-title">2026년 회계</h1>
    <p class="page-sub">행사별 수입·지출</p>
  </div>
  <div class="page-actions"><a class="btn btn--primary" href="…"><i class="fa-solid fa-plus"></i>내역 추가</a></div>
</header>
<section class="section">
  <div class="section-head"><h2 class="section-title">행사 <span class="count">12</span></h2></div>
  <div class="panel panel--flush">
    <ul class="list">
      <li><a class="list-row" href="…">
        <div class="list-row__main"><div class="list-row__title">신입생 환영회</div><div class="list-row__meta">3월 2일</div></div>
        <div class="list-row__trail"><span class="chip chip--income">+120,000</span><i class="fa-solid fa-chevron-right list-row__chev"></i></div>
      </a></li>
    </ul>
  </div>
</section>
{% endblock %}
```

## 지켜야 할 계약
- URL name, 폼 필드 `name`, POST 대상, CSRF, 뷰가 넘겨주는 context 키는 **그대로**. 기존 JS 동작(fetch 기반 액션, 드래그 등)은 기능 유지하며 새 컴포넌트로 옮긴다.
- crispy/bootstrap 클래스 의존 제거. 폼 필드는 수동 렌더링(`{{ form.x }}` + `.field`)하거나 위젯 attrs 사용.
- 뷰(.py) 수정은 백엔드 담당(codex)만. 템플릿 담당이 context가 더 필요하면 코디네이터에게 요청.
- 끝나면: `cd /Users/jung_gyul/Desktop/s-angel-page/s-angel && DATABASE_URL=sqlite:////Users/jung_gyul/Desktop/s-angel-page/preview.sqlite3 .venv/bin/python manage.py check` 통과 확인 후 보고.
