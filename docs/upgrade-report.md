# S-ANGEL 사이트 업그레이드 전체 보고서

- 작성일: 2026-11-16
- 대상: `s-angel/` (Django 5.1, Render 배포)
- 상태: **코드 작업·검수 완료, 커밋·배포 전** (로컬 미리보기에서 검증)

---

## 0. 한눈에 보기

| 항목 | 결과 |
|---|---|
| 자동 테스트 | **192개 전부 통과** (작업 전 약 30개 → 신규 보안·로직·가중치·쿼리 테스트 추가) |
| Django 점검 | `manage.py check` 이상 없음, `makemigrations --check` 누락 없음 |
| 운영 정적 파일 | 운영 설정으로 `collectstatic` 성공 (141개 파일, 압축·해시 처리) |
| 화면 검증 | 모바일(390px)·데스크탑(1440px) 전 페이지 캡처, 핵심 흐름 클릭 테스트 |
| 검수 | 디자인 스킬 1회 + **Fable 5.2 3회**(백엔드 1, 화면 1, 화면+백엔드 통합 1) → 지적 사항 반영 |
| 성능(모바일 느린 4G) | 전송량 554KB → 353KB, 로드 완료 3.1초 → 2.1초, LCP 1.56초 → 1.41초 |
| DB 변경 | 추가 마이그레이션 3개 (`0012`~`0014`) — §7 배포 주의사항 필독 |

---

## 1. 디자인

### 1.1 원칙
- **기존 정체성 유지**: 흰 배경 `#F9FAFB`, 흰 카드 + 회색 테두리 `#E5E7EB`, S-ANGEL 네이비, Pretendard. 다크모드 없음.
- **리퀴드 글래스는 떠 있는 레이어에만**: 상단 바, 하단 탭바, 메뉴, 확인창(바텀시트), 알림(토스트), 모바일 하단 저장 바.
- 공통 디자인 시스템: `static/css/sangel.css`, `static/js/sangel.js`, `templates/layouts/` — 모든 페이지가 이걸 씀(기존엔 페이지마다 따로 만든 HTML).
- 규칙 문서: `DESIGN.md`

### 1.2 버튼 (A안 · 부드러운 단색)
| 종류 | 모양 | 쓰는 곳 |
|---|---|---|
| 핵심 버튼 | 중간 톤 네이비 단색 `#3A57A8`, 둥근 네모 | 등록·저장·최종 확정·확인창 확인, 홈 “새 의전 만들기” 타일 |
| 반복 버튼 | 연한 네이비 바탕 + 네이비 테두리·글자 | 신청하기, 추첨 실행, 명단 검토 등 |
| 보조 버튼 | 흰 바탕 + 회색 테두리 | 임시저장, 취소 등 |
| 위험 버튼 | 연한 빨강 바탕 + 빨강 글자 | 삭제 확인 |
- 남색→보라 그라데이션 등 “AI 느낌” 색 제거. 특별추첨 표시의 보라색도 네이비로.
- 상태 표시: 모집 중(파랑), **확정(초록)**, 당첨(초록), 미당첨(빨강), 결과 대기·추첨 전(노랑), 검토 중(회색), 행사·본인·1로 초기화(연한 네이비).

### 1.3 리퀴드 글래스 (Apple 디자인 원칙)
- **상단 바**: 페이지 맨 위에선 차분한 흰 바 → 스크롤하면 **손가락 움직임에 1:1로 따라** 작아지며 떠 있는 유리 캡슐로 변함(폭·높이·모서리·그림자·투명도 연동, 끊김 없음).
- **하단 탭바**: 더 투명하고 흐림이 강한 유리, 위쪽 빛 반사, 선택된 탭 아래 **유리 렌즈**, 콘텐츠가 바 아래로 자연스럽게 흐려짐.
- 휴대폰 ‘동작 줄이기/투명도 줄이기’ 설정 시 자동으로 완화.

### 1.4 로고·서체
- 로그인: 날개 마크 + **고딕 “S-ANGEL”**(Pretendard, 네이비) + “로그인” 제목. 부제목 없음.
- 상단 바: 날개 마크 + 같은 고딕 워드마크. 아이폰 홈 화면 아이콘 추가.

### 1.5 문구·용어
- 전부 **합니다체**, 인사·홍보 문구 삭제, 이모지 → 아이콘.
- 용어: 추첨 대상 = **의전**, 회계 묶음 = **행사**, **신청**, 회계 기간 = **연도**(기수는 부원 기수만), 구성원 = **부원**, 관리자 = **운영진**.
- 버튼 이름: 새로 만들기 = **등록**, 고치기 = **저장**.

---

## 2. 화면 구조·사용성

### 2.1 내비게이션
- 모바일 하단 탭 / 데스크탑 상단 메뉴
  - 부원: 홈 · 캘린더 · (권한 있으면) 회계
  - 운영진: 홈 · 캘린더 · 회계 · 특별추첨 · 관리
- **내 정보**는 오른쪽 위 프로필(이니셜) 메뉴에서.
- 뒤로가기: 제목 왼쪽 **44px 둥근 버튼**. 탭으로 들어오는 화면엔 없음.
- 같은 곳으로 가는 중복 버튼 정리, 저장 바가 있는 화면에선 탭바가 비켜남.
- 터치 영역 44px 이상, 확인창·메뉴 닫으면 원래 버튼으로 포커스 복귀.

### 2.2 부원
- 홈 상단: 이름 · 기수 · 현재 추첨 가중치(인사말 없음).
- **✓ 신청하기**(연한 네이비 둥근 네모) → 신청 후 같은 자리에 **✕ 신청 취소**(전체 폭), 카드 상단에 “신청 완료” 표시. 새로고침 없음.
- 나의 신청 내역: 당첨 / 미당첨 / 결과 대기.
- 로그인 상태에서 비밀번호 변경: 현재 비밀번호 확인 후 변경(아이디·이름·기수 재입력 없음).

### 2.3 운영진
- 의전 카드: 추첨 실행 → 명단 검토·확정 → (확정 후) 당첨자. **수정·삭제는 ⋯ 메뉴**, 추첨 후엔 “의전 수정” 숨김.
- 명단 검토: 행을 눌러 추가/제외, “신청 · 남 · 여” 요약, 하단 고정 임시저장·최종 확정, 신청자별 **추첨 가중치·확정 가중치** 표시(확정 화면에선 숨김).
- 특별추첨: 날짜별 섹션·날짜 바로가기(의전명 표시), 다른 날짜로 이동, 정산 미리보기, 묶음 단위 1회 확정.
- 부원 관리: 가입 승인/거절, **가중치 −/+**(바뀔 때만 저장 버튼), **회계 열람 스위치**, **삭제 버튼** — 모두 새로고침 없음(승인만 목록 반영을 위해 새로고침).
- 새 의전 입력 칸 높이 정렬(데스크탑 단차 해결), 하루짜리 의전은 날짜 한 번만 표시.

### 2.4 캘린더
- **모바일에서도 달력 칸 안에 일정 제목** 색 막대로 표시, 여러 날 일정은 이어진 막대, 넘치면 “+n”.
- 색: 숫자 입력 없이 견본 선택(네이비·블루·그린·앰버·레드·그레이) + 이미 쓴 색 자동 표시.
- 저장·수정·삭제 후 **보던 달·날짜 유지**, 새로고침 없음.
- 같은 날짜를 한 번 더 누르면 일정 추가, 종료 = 시작 + 1시간 자동, 제목 비우면 칸 아래 오류 문구.

### 2.5 회계·통계
- 장부를 모바일용 리스트로, 날짜 “n월 j일”, 마이너스 “−” 통일.
- **새 회계 연도 생성 시 사유 필수** + 생성자·시각 기록(관리자 페이지에서 확인).
- 엑셀 다운로드는 운영진만 표시.
- 통계: 확정 / 추첨 완료 / 추첨 전 구분, “의전 통계”.

---

## 3. 가중치 시스템 (`docs/weight-system-design.md` §7)

| 항목 | 결정 |
|---|---|
| 확정 가중치 | 지금처럼 **확정한 순서대로** 반영: 당첨 → 1, 미당첨 → +1, 특별추첨은 선발률 정산 |
| 추첨용 가중치 (신규) | 추첨할 때만, 추첨됐지만 **아직 확정 안 된 다른 의전·특별추첨의 임시 결과를 미리 반영**한 값 사용 → 확정 전 연속 추첨에서 같은 사람 연속 당첨 완화 |
| 추첨값 기록 | 추첨에 실제 사용한 값을 신청 기록에 저장 → 검토 화면에 그 값 그대로 표시 |
| 확정 | 운영진이 조정한 **최종 명단 기준**으로 반영, 이중 반영 없음 |
| 앞 의전 명단 변경 | 이미 뽑은 뒤 의전은 다시 뽑지 않음 |
| 확정 의전 삭제 | 가중치 유지 |
| 3 이상 우선 선발 | 유지 (특별추첨에는 원래대로 미적용) |
| 변경 기록 | 확정·특별정산·수동 수정 시 부원별 변경 전/후 기록(관리자 페이지 ‘WeightChange’) |

Fable 5.2가 미리보기에서 직접 검증: 연속 추첨 반영, 확정 순서별 결과, 특별추첨 1회 정산 모두 규칙대로 동작.

---

## 4. 백엔드 (보안·정확성)

| 영역 | 내용 |
|---|---|
| 보안 | 상태 변경 요청 POST 전용, 회계 권한 검사, 외부 리다이렉트 차단, **승인 없이 가입되던 경로(`/accounts/signup/`) 차단**, allauth 잔여 화면 정리, 로그인 상태에서 로그인·가입 화면 → 홈 |
| 권한 | 권한 없으면 “권한 없음” 페이지(403), 비로그인은 로그인 화면 |
| 동시성 | 추첨·확정·신청 잠금 처리 → 두 번 눌러도 한 번만 처리, 특별추첨 중복 정산 방지 |
| 추첨 로직 | 성별 정원 외 남는 자리·부족분을 남은 신청자로 보충 |
| 입력 검증 | 의전 인원·날짜, 회계 날짜·금액·구분·행사-연도 일치 → 서버 오류 대신 안내 |
| 비밀번호 재설정 | **기존 방식 유지**(아이디·이름·기수) + 시도 제한(아이디·IP별 10분 5회) + 10분 만료, 운영진 계정은 이 방식으로 재설정 불가 |
| 부원 관리 API | 승인·거절·가중치·회계 열람·삭제가 JSON 응답 지원(새로고침 없는 처리), 운영진 계정 삭제 서버에서 차단 |
| 정리 | 사용하지 않던 소개 페이지, `/rchoice/` 옛 테스트 페이지 삭제 |

---

## 5. 최적화

| 항목 | 내용 | 효과 |
|---|---|---|
| 아이콘 | Font Awesome 전체(CDN) → **실제 쓰는 61개만 자체 호스팅** (`static/vendor/fa/`) | 약 280KB → 11KB, 외부 요청 2개 감소 |
| 로고 | 표시 크기에 맞춰 축소 + WebP | 84KB → 18KB |
| 정적 파일 | **whitenoise** 도입: 압축(gzip/brotli) + 파일명 해시 + 장기 캐시 | 재방문 시 CSS·JS·이미지 재다운로드 없음 |
| DB 쿼리 | 명단 검토·특별추첨·회계 화면의 N+1 제거, 회귀 테스트 추가 | 신청자 5명이든 30명이든 13쿼리로 일정 |
| 스크립트 | 공통 JS 로딩 순서 수정 | 일부 화면 기능이 동작 안 하던 버그 해결 |
| 측정 | 모바일 느린 4G + CPU 4배 저속 | 홈 로드 3.06초 → 2.08초, LCP 1.56 → 1.41초, CLS 0 |

한글 폰트(Pretendard)는 필요한 글자만 받는 방식이라 유지.

---

## 6. 검수 이력

| 회차 | 방법 | 결과 |
|---|---|---|
| 1 | 디자인 스킬 검수(화면 34장 + 소스) | 25건 → 반영 (`docs/design-review-2.md`) |
| 2 | Fable 5.2 백엔드 검수 | 배포 차단 2건(운영 정적 파일 404, 미추가 파일) 포함 20건 → 반영 |
| 3 | Fable 5.2 화면·사용성 E2E | 치명 2건(로그인 오류, 확정 의전 “모집 중” 표시) 포함 28건 → 반영 |
| 4 | Fable 5.2 통합 재검수 | **치명 문제 없음**, 1차 지적 해결 확인, 가중치 시스템 검증 통과 → 잔여 22건 반영 |
| 최종 | 직접 확인 | 테스트 192개 통과, 운영 설정 collectstatic 성공, 신청/취소·부원 관리 클릭 테스트 새로고침 0회 |

---

## 7. ⚠️ Render 배포 주의사항

### 7.1 배포 전
1. **DB 백업 먼저** — Render 대시보드 → PostgreSQL → Backups(또는 `pg_dump`). 이번 배포에 기존 칸 형식을 바꾸는 마이그레이션(`0014`)이 있습니다.
2. **새 파일을 반드시 git에 추가** (빠지면 서버가 안 뜨거나 디자인이 깨짐). 아래 §7.5 목록 전체 `git add`.
3. **Render 환경변수 확인**
   | 변수 | 필요 | 비고 |
   |---|---|---|
   | `DJANGO_SECRET_KEY` | 필수 | 기존 값 유지 |
   | `DJANGO_ADMIN_URL` | 필수 | 기존 값 유지 |
   | `DATABASE_URL` | 필수 | Render PostgreSQL |
   | `DJANGO_ALLOWED_HOSTS` | 필수 | 기존 도메인 포함 |
   | `DJANGO_DEBUG` | **False(또는 미설정)** | True면 디버그 툴바·오류 상세가 노출됨 |
   | `REDIS_URL` | 선택 | 없으면 DB 캐시로 자동 동작(비밀번호 재설정 시도 제한용) |
   | `DJANGO_ACCOUNT_ALLOW_REGISTRATION` | 설정하지 말 것 | 기본 False 유지(승인 우회 가입 차단) |
4. **파이썬 버전 표기 확인** — `runtime.txt`는 `python-3.13.1`, `.python-version`은 `3.12`로 서로 다릅니다. Render는 보통 `PYTHON_VERSION` 환경변수 또는 `.python-version`을 따르므로, 지금 쓰는 버전 하나로 맞춰 두는 것을 권장합니다.

### 7.2 배포 시 자동으로 실행되는 것 (`build.sh`)
```bash
pip install -r requirements.txt              # whitenoise 새로 설치
python manage.py migrate --noinput           # 0012 → 0013 → 0014 자동 적용
python manage.py createcachetable            # DB 캐시 테이블 생성(신규)
python manage.py collectstatic --noinput     # 압축·해시된 정적 파일 생성
```
→ **마이그레이션 명령을 직접 칠 필요는 없습니다.** 빌드 로그에서 `Applying applications.0012/0013/0014 ... OK` 를 확인하세요.

### 7.3 이번 마이그레이션 내용
| 번호 | 내용 | 기존 데이터 영향 |
|---|---|---|
| `0012` | 회계 연도에 생성 사유·생성자·생성 시각 칸 추가 | 없음 (기존 연도는 빈 값) |
| `0013` | 의전·특별추첨에 추첨 시각 칸, 가중치 변경 기록 표(`WeightChange`) 추가 | 없음 |
| `0014` | 신청 기록의 `weight` 칸을 정수 → 소수(빈 값 허용)로 변경, 기존 값은 비움 | 이 칸은 지금까지 어디서도 쓰이지 않던 칸(코드 전체 확인). **부원 가중치(`User.weight`)는 그대로** |

- `0014`는 로컬 PostgreSQL 14에서 적용·되돌리기까지 실제 실행해 검증했습니다.

### 7.4 배포 후 확인 순서 (5분)
1. 로그인 화면이 새 디자인(날개 로고 + S-ANGEL)으로 보이는지 → 안 보이면 정적 파일 문제(§7.6)
2. 부원 계정: 의전 신청 → 취소
3. 운영진 계정: 새 의전 등록 → 추첨 실행 → 명단 검토 → 최종 확정 → 가중치 반영 확인
4. 캘린더 일정 추가·삭제, 회계 내역 추가
5. 관리: 가중치 −/+ 저장, 회계 열람 스위치
6. 휴대폰으로 하단 탭바·상단 바 확인

### 7.5 git에 추가해야 할 새 파일 (34개)
```
DESIGN.md
PRODUCT.md
docs/design-review-2.md
docs/redesign-brief.md
docs/upgrade-report.md
docs/weight-system-design.md
s_angel/applications/accounting_forms.py
s_angel/applications/decorators.py
s_angel/applications/weight_service.py
s_angel/applications/migrations/0012_budgetyear_created_at_budgetyear_created_by_and_more.py
s_angel/applications/migrations/0013_draw_weights_and_weightchange.py
s_angel/applications/migrations/0014_application_draw_weight_snapshot.py
s_angel/applications/test_backend_security.py
s_angel/applications/test_draw_weight_snapshots.py
s_angel/applications/test_event_form_validation.py
s_angel/applications/test_query_scaling.py
s_angel/applications/test_review_regressions.py
s_angel/applications/test_special_lottery_security.py
s_angel/applications/test_special_weight_flow.py
s_angel/applications/test_weight_system.py
s_angel/static/css/sangel.css
s_angel/static/js/sangel.js
s_angel/static/vendor/fa/fa-subset.css
s_angel/static/vendor/fa/fa-solid-sub.woff2
s_angel/static/vendor/fa/fa-regular-sub.woff2
s_angel/static/images/logo.png
s_angel/static/images/logo-mark.webp
s_angel/static/images/logo-mark-lg.webp
s_angel/static/images/apple-touch-icon.png
s_angel/templates/layouts/app.html
s_angel/templates/layouts/auth.html
s_angel/templates/partials/messages.html
s_angel/templates/applications/_review_pick.html
s_angel/users/tests/test_reset_security.py
```
그 외 수정된 기존 파일 약 55개 + 삭제 파일(`applications/introduction.html`)도 함께 커밋. 가장 쉬운 방법:
```bash
cd s-angel
git add -A
git status            # .venv, staticfiles/, *.sqlite3 같은 게 안 들어갔는지 확인
git commit -m "S-ANGEL 리디자인·가중치 시스템·보안·최적화"
git push
```

### 7.6 문제가 생기면
| 증상 | 원인/조치 |
|---|---|
| 화면이 스타일 없이 깨짐 | 정적 파일 미추가 또는 collectstatic 실패 → 빌드 로그 확인, §7.5 파일 git 추가 여부 확인 |
| 서버가 안 뜸 (ImportError) | `decorators.py`·`weight_service.py`·`accounting_forms.py` 누락 |
| 500 오류 (column does not exist) | 마이그레이션 미적용 → 빌드 로그의 migrate 단계 확인 |
| 되돌려야 할 때 | Render에서 **이전 배포로 롤백 + DB 백업 복원**을 함께. `0014`가 적용된 DB에서 코드만 이전 버전으로 돌리면 `weight` 칸 형식이 달라 문제가 될 수 있음 |
| 무료 플랜 첫 접속이 느림 | Render 무료 인스턴스 잠자기(코드 문제 아님) |

참고: 비밀번호 재설정 IP 제한은 Render 프록시 헤더를 신뢰하지 않고 접속 IP 기준이라, IP 제한보다 **아이디별 제한**이 실제로 동작합니다(보안상 문제없음).

---

## 8. 그 외 권장
1. **프로젝트를 iCloud 데스크탑 밖으로 이동** (예: `~/dev/s-angel-page`). iCloud가 `.venv` 파일을 비워서 Django가 멈추는 문제가 있었습니다(테스트는 `/tmp` 별도 환경에서 실행).
2. 백업 폴더 `s-angel.backup-20261115`는 불완전한 복사본 → 되돌릴 땐 git 기준.
3. 테스트 실행 명령(로컬):
   ```bash
   DATABASE_URL=sqlite:////tmp/sangel-test.sqlite3 python -m pytest -q
   ```

---

## 9. 작업 분배

| 담당 | 작업 |
|---|---|
| 메인-claude-3 (코디네이터) | 조율, 공통 디자인 시스템·레이아웃, 대시보드, 부원 관리, 로그인·로고, 글래스 상단 바·탭바, 버튼 시안, 최적화, 검수 진행, 보고서 |
| 에스엔-사이트-codex-1 | 백엔드 보안·정확성, whitenoise, 가중치 시스템, 회계 연도 사유, 쿼리 최적화, 테스트 |
| 메인-claude-2 | 회계 · 캘린더 · 통계 |
| 에스엔-추첨-claude | 의전·추첨·특별추첨 화면 |
| 에스엔-사이트-agy-1 | 로그인·회원가입·에러 페이지 (초반에만, 사용량 절약) |
| Fable 5.2 | 독립 검수 3회 |

## 10. 참고 문서
- `DESIGN.md` — 디자인 규칙
- `PRODUCT.md` — 서비스 개요
- `docs/weight-system-design.md` — 가중치 설계(§7 최종 사양)
- `docs/design-review-2.md` — 1차 디자인 검수
