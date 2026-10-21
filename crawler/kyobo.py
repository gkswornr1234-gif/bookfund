"""교보 바로펀딩 — 목록은 JS로 불러오므로, 메인에 노출된 상세 번호를 시드로 삼고
앞뒤 번호를 탐색해 새 프로젝트를 찾음 (/funding/detail/{번호})."""
import re

from .common import (fetch, soup_of, lines_of, meta, to_int, find_date_range, label_value,
                     benefit_lines, new_item)

BASE = "https://event.kyobobook.co.kr"
MAIN_URL = f"{BASE}/funding"
DETAIL_URL = f"{BASE}/funding/detail/{{}}"
BOOTSTRAP = 40      # 첫 실행 때 최신 번호에서 거꾸로 훑을 개수
MAX_MISSES = 5      # 최신 번호 이후 연속으로 비어 있으면 탐색 중단

# 페이지에 JSON으로 데이터가 박혀 있는 경우를 대비한 키 후보
JSON_KEYS = {
    "publisher": r"pbcm\w*Nm|pbcm\w*Name|publisher\w*|pblsr\w*",
    "title": r"fndg\w*Nm|fndg\w*Name|prjt\w*Nm|title",
    "start_date": r"\w*(?:Strt|Start|Bgn)\w*(?:Dt|Date|Ymd)",
    "end_date": r"\w*(?:End|Cls)\w*(?:Dt|Date|Ymd)",
    "goal": r"\w*(?:Goal|Trgt)\w*(?:Amt|Amount)",
    "amount": r"\w*(?:Acml|Total|Sum)\w*(?:Amt|Amount)",
}


def ids_on_main(html: str) -> set[int]:
    return {int(x) for x in re.findall(r"/funding/detail/(\d+)", html)}


def _json_pick(html: str, it: dict) -> None:
    for field, key_re in JSON_KEYS.items():
        if it.get(field):
            continue
        m = re.search(rf'"(?:{key_re})"\s*:\s*"?([^",}}]{{1,60}})"?', html)
        if m:
            v = m.group(1).strip()
            it[field] = to_int(v) if field in ("goal", "amount") else v


def parse_detail(html: str, it: dict) -> dict | None:
    soup = soup_of(html)
    title = meta(soup, "og:title") or (soup.title.get_text(strip=True) if soup.title else "")
    title = re.sub(r"\s*[-|]\s*(바로펀딩|교보문고).*$", "", title or "").strip()
    lines = lines_of(soup.body or soup)
    txt = "\n".join(lines)
    if not title or title == "바로펀딩":
        title = None
    if (m := re.search(r"(\d+)%\s*달성", txt)):
        it["rate"] = int(m.group(1))
    if not title and it["rate"] is None:
        return None  # 없는 번호
    it["title"] = title
    it["image"] = meta(soup, "og:image")
    if m := re.search(r"달성\s*\n?\s*([\d,]+)\s*원", txt):
        it["amount"] = to_int(m.group(1))
    for st in ("마감임박", "진행 중", "오픈예정", "종료"):
        if st in txt[:3000]:
            it["status"] = {"진행 중": "진행중"}.get(st, st)
            break
    it["publisher"] = label_value(txt, ("출판사", "펴낸곳", "브랜드", "제조사"))
    it["category_raw"] = label_value(txt, ("분야", "카테고리"))
    s, e = find_date_range(txt)
    it["start_date"], it["end_date"] = s, e
    if m := re.search(r"목표\s*금액\s*[:：]?\s*([\d,]+)\s*원", txt):
        it["goal"] = to_int(m.group(1))
    it["benefits"] = benefit_lines(lines)
    _json_pick(html, it)
    if it["start_date"]:
        it["start_date"] = it["start_date"][:10]
    return it


def crawl(known: dict) -> list[dict]:
    main = fetch(MAIN_URL, debug_name="kyobo_main.html")
    seeds = ids_on_main(main) if main else set()
    known_ids = {int(k) for k in known}
    top = max(seeds | known_ids, default=0)
    if not top:
        print("[교보] 시드 번호를 찾지 못함")
        return []

    targets = set(seeds)
    targets |= {int(k) for k, v in known.items() if v.get("status") != "종료"}
    floor = max(known_ids) if known_ids else top - BOOTSTRAP
    targets |= set(range(floor + 1, top + 1))

    out, done = [], set()
    for n in sorted(targets):
        d = fetch(DETAIL_URL.format(n), debug_name=f"kyobo_{n}.html")
        done.add(n)
        if d and (it := parse_detail(d, new_item("kyobo", n, DETAIL_URL.format(n)))):
            out.append(it)

    # 최신 번호 이후로 새 프로젝트가 더 있는지 탐색
    n, misses = top, 0
    while misses < MAX_MISSES:
        n += 1
        d = fetch(DETAIL_URL.format(n), debug_name=f"kyobo_{n}.html")
        it = parse_detail(d, new_item("kyobo", n, DETAIL_URL.format(n))) if d else None
        if it:
            out.append(it)
            misses = 0
        else:
            misses += 1
    print(f"[교보] {len(out)}건")
    return out
