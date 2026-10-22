# 북펀딩 모니터

알라딘 북펀드, YES24 그래제본소, 교보 바로펀딩을 매일 아침 수집해 한 화면에서 보고, 지정한 분야의 신규 펀딩은 Teams로 알림.

## 구조

```
run.py                     수집 → 병합 → 신규 감지 → Teams 알림
crawler/aladin.py          목록 + 상세(펴낸곳, 주제 분류, 상품구성)
crawler/yes24.py           목록(달성률, 금액, 남은 일수) + 상세/상품 페이지
crawler/kyobo.py           메인의 상세 번호를 시드로 앞뒤 번호 탐색
config/categories.json     서점 분류 → 분야 매핑, 분야별 담당 멘션
docs/index.html            대시보드 (GitHub Pages)
docs/data/fundings.json    누적 데이터 (Actions가 커밋)
```

## 운영 설정

- 실행: 매일 07:30 cron-job.org가 `actions/workflows/crawl.yml/dispatches`를 호출 (토큰 권한: Actions 쓰기). GitHub 자체 예약은 사용 안 함
- 알림: Secret `TEAMS_WEBHOOK_URL` (Teams 워크플로 '채팅/채널에 웹후크 경고 보내기'로 만든 URL)
- 알림 분야: `config/categories.json`의 `alert.categories` (비우면 전체). 분야별로 다른 채널은 `alert.channels`에 Secret 이름 지정
- 수집 기준: 2026-01-01 이후 마감된 펀딩만 (`run.py`의 SINCE)

## 수동 실행 옵션 (Actions → Run workflow)

- debug: 받은 HTML을 아티팩트로 저장 (파서 점검용)
- test_alert: 수집 없이 알림 분야의 최근 3건으로 Teams 시험 발송
- backfill: 알라딘·교보의 올해 종료 펀딩을 번호를 거슬러 채움 (중간에 끊기면 다음 실행에서 이어감)
- only: 한 서점만 실행

## 데이터 기준

- 등록일: 예스24·교보는 공개된 시작일, 알라딘은 처음 발견한 날. 과거 채우기 건은 목표 달성일·마감일 중 이른 날
- 수량: 알라딘·예스24는 실제 권수, 교보는 펀딩액 ÷ 펀딩가로 추정(`count_est`, 화면에 '약'으로 표시)
- 추이: 수집할 때마다 펀딩액·수량·달성률을 하루 1건씩 `history`에 쌓음 (최근 120일)
- 분야: `config/categories.json` 키워드로 교보 분야에 맞춤. 안 맞으면 '미분류'

## 로컬 실행

```
pip install -r requirements.txt
python run.py                  # 전체
python run.py --only yes24     # 한 서점만
DEBUG_DIR=debug python run.py  # 받은 HTML 저장
python -m pytest tests         # 파서 테스트
```

## 운영 원칙

- 요청 사이 1초 안팎 대기, 하루 1회 실행, 서점당 최대 8분
- 사내 참고용으로만 사용
- 한 서점이 실패해도 나머지는 계속 수집. 실패 여부는 대시보드 왼쪽 아래 '서점별 마지막 수집'에 표시
