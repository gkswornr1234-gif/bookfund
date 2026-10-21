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
from crawler.common import KST, today, set_budget

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "docs", "data", "fundings.json")
CATS = os.path.join(ROOT, "config", "categories.json")
STORES = {"aladin": ("알라딘", aladin), "yes24": ("YES24", yes24), "kyobo": ("교보", kyobo)}
KEEP_HISTORY = 120
ACTIVE = ("진행중", "마감임박", "오픈예정")
STORE_BUDGET = 8 * 60  # 서점 하나에 최대 8분
MAX_ALERT = 20  # 한 번에 알림에 싣는 최대 건수


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def map_category(raw: str | None, cfg: dict) -> tuple[str, str]:
    if raw:
        for r in cfg["rules"]:
            if any(k in raw for k in r["keywords"]):
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
    body = [{"type": "TextBlock", "text": f"북펀딩 신규 {len(items)}건", "weight": "Bolder", "size": "Large"}]
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


def notify(new_items: list[dict], cfg: dict) -> None:
    if not new_items:
        return
    items = sorted(new_items, key=lambda x: (x["category"], x["store"]))
    for env, fn in (("TEAMS_WEBHOOK_URL", notify_teams), ("SLACK_WEBHOOK_URL", notify_slack)):
        if url := os.environ.get(env):
            try:
                fn(url, items, cfg)
            except requests.RequestException as e:
                print(f"{env} 전송 실패: {e}")


def save(db: dict) -> None:
    db["updated_at"] = datetime.now(KST).isoformat(timespec="minutes")
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(STORES))
    args = ap.parse_args()

    cfg = load(CATS, {"rules": [], "fallback": {"category": "미분류"}})
    db = load(DATA, {"updated_at": None, "runs": {}, "items": {}})
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
        for it in got:
            k = f"{key}:{it['id']}"
            is_new = k not in items
            items[k] = merge(items.get(k), it, cfg)
            if is_new:
                new_items.append(items[k])
        save(db)  # 서점 하나 끝날 때마다 저장 (중간에 멈춰도 앞 서점 결과는 남음)

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
