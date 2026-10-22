"""서점별 수집 → 기존 데이터와 병합 → 신규 감지 → Teams/슬랙 알림.

python run.py                 # 전체 실행
python run.py --only aladin   # 한 서점만
DEBUG_DIR=debug python run.py # 받은 HTML을 debug/에 저장 (셀렉터 점검용)
"""
import argparse
import json
import os
import traceback
from datetime import datetime

import requests

from crawler import aladin, yes24, kyobo
from crawler.common import KST, today, set_budget, ref_date

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "docs", "data", "fundings.json")
CATS = os.path.join(ROOT, "config", "categories.json")
STORES = {"aladin": ("알라딘", aladin), "yes24": ("YES24", yes24), "kyobo": ("교보", kyobo)}
KEEP_HISTORY = 120
ACTIVE = ("진행중", "마감임박", "오픈예정")
STORE_BUDGET = 8 * 60  # 서점 하나에 최대 8분
BACKFILL_BUDGET = 20 * 60  # 과거 채우기는 서점당 최대 20분 (끊기면 다음 실행에서 이어서)
# 이 날짜 이전에 끝난 펀딩은 수집하지 않음. 해가 바뀌어도 고정값이라 쌓인 데이터는 지워지지 않음
SINCE = os.environ.get("SINCE") or "2026-01-01"
MAX_ALERT = 20  # 한 번에 알림에 싣는 최대 건수


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


GENERIC = ("국내도서", "외국도서", "eBook", "전자책", "도서")


def map_category(raw: str | None, cfg: dict) -> tuple[str, str]:
    """분류 경로를 큰 분류부터 한 단계씩 보며 규칙에 맞는 첫 분야를 고름.
    '국내도서 > 인문 > 독서/비평 > 독서 에세이' → 인문 (아래 단계의 '에세이'보다 큰 분류 우선)."""
    if raw:
        segs = [x.strip() for x in raw.split(">") if x.strip() and x.strip() not in GENERIC] or [raw]
        for seg in segs:
            for r in cfg["rules"]:
                if any(k in seg for k in r["keywords"]):
                    return r["category"], r.get("owner", "")
    fb = cfg["fallback"]
    return fb["category"], fb.get("owner", "")


def merge(old: dict | None, new: dict, cfg: dict) -> dict:
    d = today()
    if old:
        merged = dict(old)
        for k, v in new.items():
            if v not in (None, [], ""):
                merged[k] = v
    else:
        merged = dict(new, first_seen=d, history=[])
    merged["last_seen"] = d
    # 등록일: 서점이 공개한 시작일 → 매일 수집에서 처음 발견한 날 → (과거 채우기 건) 목표 달성일·마감일 중 이른 날
    late = [x for x in (merged.get("achieved_date"), merged.get("end_date"), merged.get("release_date")) if x]
    merged["reg_date"] = merged.get("start_date") or (
        min(late) if merged.get("backfilled") and late else merged.get("first_seen"))
    merged["category"], _ = map_category(merged.get("category_raw"), cfg)
    if not merged.get("count") and merged.get("amount") and merged.get("price"):
        merged["count_est"] = round(merged["amount"] / merged["price"])

    snap = {"d": d, "amount": merged.get("amount"), "count": merged.get("count") or merged.get("count_est"),
            "rate": merged.get("rate")}
    hist = merged.setdefault("history", [])
    if hist and hist[-1]["d"] == d:
        hist[-1] = snap
    else:
        hist.append(snap)
    merged["history"] = hist[-KEEP_HISTORY:]
    return merged


def _line(it: dict, cfg: dict) -> tuple[str, str]:
    """알림 한 건: (제목 줄, 보조 정보 줄)."""
    _, owner = map_category(it.get("category_raw"), cfg)
    meta = [STORES[it['store']][0], it.get("publisher") or "출판사 미확인", it["category"]]
    if it.get("end_date"):
        meta.append(f"~{it['end_date'][5:].replace('-', '/')} 마감")
    if owner:
        meta.append(f"담당 {owner}")
    title = (it.get("title") or it["id"]).replace("[", "(").replace("]", ")")  # 링크 문법 충돌 방지
    return title, " | ".join(meta)


def dashboard_url() -> str | None:
    repo = os.environ.get("GITHUB_REPOSITORY")  # Actions가 자동으로 넣어줌: 계정/저장소
    if not repo:
        return None
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}/"


def notify_teams(url: str, items: list[dict], cfg: dict) -> None:
    """Teams 워크플로('웹후크 요청을 받으면 채널에 게시')로 적응형 카드 전송."""
    cats = sorted({it["category"] for it in items})
    head = f"북펀딩 신규 {len(items)}건" + (f" · {', '.join(cats)}" if len(cats) <= 3 else "")
    body = [{"type": "TextBlock", "text": head, "weight": "Bolder", "size": "Large", "wrap": True}]
    for it in items[:MAX_ALERT]:
        title, meta = _line(it, cfg)
        body += [
            {"type": "TextBlock", "text": f"[{title}]({it['url']})", "wrap": True, "spacing": "Medium", "weight": "Bolder"},
            {"type": "TextBlock", "text": meta, "wrap": True, "isSubtle": True, "spacing": "None", "size": "Small"},
        ]
    if len(items) > MAX_ALERT:
        body.append({"type": "TextBlock", "text": f"외 {len(items) - MAX_ALERT}건은 대시보드에서 확인", "isSubtle": True})
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard",
            "version": "1.4", "body": body, "msteams": {"width": "Full"}}
    if dash := dashboard_url():
        card["actions"] = [{"type": "Action.OpenUrl", "title": "대시보드 열기", "url": dash}]
    payload = {"type": "message", "attachments": [
        {"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}]}
    r = requests.post(url, json=payload, timeout=20)
    print(f"Teams 전송: HTTP {r.status_code}")


def notify_slack(url: str, items: list[dict], cfg: dict) -> None:
    lines = [f"*북펀딩 신규 {len(items)}건*"]
    for it in items[:MAX_ALERT]:
        title, meta = _line(it, cfg)
        lines.append(f"<{it['url']}|{title}> / {meta}")
    requests.post(url, json={"text": "\n".join(lines)}, timeout=15)


def secret(name: str) -> str | None:
    """환경변수 → 워크플로가 넘긴 SECRETS_JSON 순으로 찾음 (분야별 채널 웹후크를 이름만으로 추가하기 위해)."""
    if v := os.environ.get(name):
        return v
    try:
        return json.loads(os.environ.get("SECRETS_JSON") or "{}").get(name)
    except json.JSONDecodeError:
        return None


def notify(new_items: list[dict], cfg: dict) -> None:
    """config/categories.json의 alert 설정에 따라 분야별로 걸러 Teams에 보냄.
    alert.categories가 비어 있으면 전체 분야, 분야별 채널은 alert.channels에 웹후크 Secret 이름으로 지정."""
    if not new_items:
        return
    alert = cfg.get("alert") or {}
    watch = set(alert.get("categories") or [])
    channels = alert.get("channels") or {}
    items = [it for it in new_items if not watch or it["category"] in watch]
    items.sort(key=lambda x: (x["category"], x["store"]))
    if not items:
        print(f"신규 {len(new_items)}건 중 알림 대상 분야 없음")
        return
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(channels.get(it["category"], "TEAMS_WEBHOOK_URL"), []).append(it)
    for name, group in groups.items():
        if not (url := secret(name)):
            print(f"{name} Secret이 없어 {len(group)}건 알림 생략")
            continue
        try:
            notify_teams(url, group, cfg)
        except requests.RequestException as e:
            print(f"{name} 전송 실패: {e}")
    if url := secret("SLACK_WEBHOOK_URL"):
        try:
            notify_slack(url, items, cfg)
        except requests.RequestException as e:
            print(f"SLACK_WEBHOOK_URL 전송 실패: {e}")


def save(db: dict) -> None:
    db["updated_at"] = datetime.now(KST).isoformat(timespec="minutes")
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(STORES))
    ap.add_argument("--test-alert", action="store_true", help="수집 없이, 알림 대상 분야의 최근 펀딩 3건으로 알림만 시험 발송")
    ap.add_argument("--backfill", action="store_true", help="SINCE 이후 종료 펀딩까지 채움 (알라딘·교보는 번호, 예스24는 종료 포함 목록)")
    args = ap.parse_args()

    cfg = load(CATS, {"rules": [], "fallback": {"category": "미분류"}})
    db = load(DATA, {"updated_at": None, "runs": {}, "items": {}})
    if args.test_alert:
        watch = set((cfg.get("alert") or {}).get("categories") or [])
        pool = [v for v in db["items"].values() if (not watch or v.get("category") in watch) and v.get("status") != "종료"]
        pool.sort(key=lambda v: v.get("reg_date") or v.get("first_seen") or "", reverse=True)
        print(f"[시험 알림] 대상 {len(pool)}건 중 최근 3건 발송")
        notify(pool[:3], cfg)
        return
    items, runs = db["items"], db.setdefault("runs", {})
    bootstrap = not items  # 첫 실행엔 알림 생략 (기존 펀딩이 전부 신규로 잡히므로)
    new_items = []

    for key, (name, mod) in STORES.items():
        if args.only and key != args.only:
            continue
        print(f"== {name} 수집 시작", flush=True)
        set_budget(STORE_BUDGET)
        known = {v["id"]: v for k, v in items.items() if v["store"] == key}
        try:
            got = mod.crawl(known)
            runs[key] = {"at": datetime.now(KST).isoformat(timespec="minutes"), "ok": bool(got),
                         "count": len(got), "error": None if got else "수집 0건 — 페이지 구조 변경 또는 차단 확인 필요"}
        except Exception as e:  # 한 서점이 실패해도 나머지는 진행
            traceback.print_exc()
            runs[key] = {"at": datetime.now(KST).isoformat(timespec="minutes"), "ok": False,
                         "count": 0, "error": f"{type(e).__name__}: {e}"}
            continue
        if args.backfill and hasattr(mod, "backfill"):
            print(f"== {name} 과거 채우기 (since {SINCE})", flush=True)
            set_budget(BACKFILL_BUDGET)
            known.update({it["id"]: it for it in got})
            try:
                got += [dict(x, backfilled=True) for x in mod.backfill(known, SINCE)]
            except Exception:
                traceback.print_exc()
        for it in got:
            if (ref_date(it) or "9999") < SINCE:
                continue  # 기준일 이전에 끝난 펀딩 (알라딘 메인의 옛날 진열 건 등)
            k = f"{key}:{it['id']}"
            is_new = k not in items
            items[k] = merge(items.get(k), it, cfg)
            if is_new and items[k].get("status") != "종료":  # 이미 끝난 펀딩은 알림 안 함
                new_items.append(items[k])
        save(db)  # 서점 하나 끝날 때마다 저장 (중간에 멈춰도 앞 서점 결과는 남음)

    # 분야 규칙이 바뀌어도 저장된 모든 건에 반영
    for v in items.values():
        v["category"], _ = map_category(v.get("category_raw"), cfg)

    # 기준일 이전 펀딩이 이미 저장돼 있으면 정리
    for k in [k for k, v in items.items() if (ref_date(v) or "9999") < SINCE]:
        del items[k]

    # 목록에서 사라졌고 마감일이 지난 건은 종료 처리
    d = today()
    for v in items.values():
        if v.get("status") in ACTIVE and v.get("end_date") and v["end_date"] < d:
            v["status"] = "종료"

    save(db)
    print(f"신규 {len(new_items)}건, 전체 {len(items)}건")
    if not bootstrap:
        notify(new_items, cfg)


if __name__ == "__main__":
    main()
