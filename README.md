# 북펀딩 모니터

알라딘 북펀드, YES24 그래제본소, 교보 바로펀딩을 하루 두 번 수집해 한 화면에서 보고, 신규 펀딩은 슬랙으로 알림.

## 구조

```
run.py                     수집 → 병합 → 신규 감지 → 슬랙 알림
crawler/aladin.py          목록 + 상세(펴낸곳, 주제 분류, 상품구성)
crawler/yes24.py           목록(달성률, 금액, 남은 일수) + 상세/상품 페이지
crawler/kyobo.py           메인의 상세 번호를 시드로 앞뒤 번호 탐색
config/categories.json     서점 분류 → 분야 매핑, 분야별 담당 멘션
docs/index.html            대시보드 (GitHub Pages)
docs/data/fundings.json    누적 데이터 (Actions가 커밋)
```

## 처음 설정

1. 이 폴더를 새 GitHub 저장소에 올림
2. Settings → Pages → Branch `main`, 폴더 `/docs` 선택
3. Settings → Secrets → Actions에 `SLACK_WEBHOOK_URL` 추가 (없으면 알림만 생략)
4. Actions → 북펀딩 수집 → Run workflow, `debug` 체크하고 첫 실행
5. 실행 결과의 `debug-html` 아티팩트로 실제 페이지 구조 확인 → 필요하면 파서 보정

첫 실행은 기존 펀딩이 전부 신규로 잡히므로 알림을 보내지 않음.

## 예약 실행

워크플로에 매일 09:00, 18:00(KST) 예약이 들어 있음. GitHub 예약 실행은 지연되거나 건너뛰는 경우가 있어 cron-job.org에서 아래 요청을 같은 시각에 보내는 걸 권장.

```
POST https://api.github.com/repos/{owner}/{repo}/actions/workflows/crawl.yml/dispatches
Authorization: Bearer {fine-grained token, Actions: write}
Accept: application/vnd.github+json
Body: {"ref":"main"}
```

## 데이터 기준

- 등록일: 세 서점 모두 공개하지 않음 → 처음 발견한 날(`first_seen`)로 기록. 상세에 기간이 있으면 `start_date`도 채움
- 수량: 알라딘은 권수 그대로, YES24·교보는 펀딩액 ÷ 펀딩가로 추정(`count_est`, 화면에 '약'으로 표시)
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

- 요청 사이 1초 안팎 대기, 하루 2회만 실행
- 사내 참고용으로만 사용
- 한 서점이 실패해도 나머지는 계속 수집. 실패 여부는 대시보드 왼쪽 아래 '서점별 마지막 수집'에 표시
