"""교보 바로펀딩 — 목록은 JS로 불러오므로, 메인에 노출된 상세 번호를 시드로 삼고
앞뒤 번호를 탐색해 새 프로젝트를 찾음 (/funding/detail/{번호})."""
import json
import re
from datetime import date, datetime

from .common import (SiteDown, KST, fetch, soup_of, lines_of, meta, to_int, new_item, closest_date,
                     period_from_md, ref_date)

BASE = "https://event.kyobobook.co.kr"
MAIN_URL = f"{BASE}/funding"
DETAIL_URL = f"{BASE}/funding/detail/{{}}"
BOOTSTRAP = 40      # 첫 실행 때 최신 번호에서 거꾸로 훑을 개수
MAX_MISSES = 5      # 최신 번호 이후 연속으로 비어 있으면 탐색 중단
MAX_AHEAD = 20      # 최신 번호 이후 최대 탐색 개수 (무한 탐색 방지)
STOP = 8            # 과거 채우기: 기준일 이전·없는 번호가 연속 이만큼 나오면 멈춤

def ids_on_main(html: str) -> set[int]:
    return {int(x) for x in re.findall(r"/funding/detail/(\d+)", html)}


STATUS = {"진행 중": "진행중", "진행중": "진행중", "마감임박": "마감임박", "종료": "종료", "오픈예정": "오픈예정", "오픈 예정": "오픈예정"}


def _ld(soup) -> dict:
    """페이지에 들어 있는 schema.org JSON-LD (도서명·출판사·장르·ISBN)."""
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = tag.string or ""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # 설명문에 따옴표가 그대로 들어가 JSON이 깨지는 경우가 있어 필요한 값만 직접 추출
            g = lambda pat: (m.group(1) if (m := re.search(pat, raw, re.S)) else None)
            data = {"@type": g(r'"@type"\s*:\s*"(Book|Product)"'), "name": g(r'"name"\s*:\s*"([^"]+)"'),
                    "genre": g(r'"genre"\s*:\s*"([^"]+)"'),
                    "publisher": {"name": g(r'"publisher"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"')},
                    "brand": {"name": g(r'"brand"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"')},
                    "workExample": [{"isbn": g(r'"isbn"\s*:\s*"([^"]+)"')}]}
        if isinstance(data, dict) and data.get("@type") in ("Book", "Product"):
            return data
    return {}


def _md(text: str | None) -> list[tuple[int, int]]:
    return [(int(m), int(d)) for m, d in re.findall(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text or "")]


BOOK_ROOTS = ("국내도서", "외국도서", "eBook", "e북", "전자책")


def is_goods(it: dict) -> bool:
    """핫트랙스·교보Only 같은 굿즈 펀딩인지. 분류가 없으면 페이지의 상품 유형(Book/Product)으로 판단."""
    cat = (it.get("category_raw") or "").strip()
    if cat:
        return not cat.startswith(BOOK_ROOTS)
    return it.get("kind") == "goods"


def parse_detail(html: str, it: dict) -> dict | None:
    soup = soup_of(html)
    badge = soup.select_one(".prod_price_wrap .badge_list_box .text")
    head = soup.select_one(".prod_title")
    if not badge or not head:
        return None  # 없는 번호
    lines = lines_of(soup.body or soup)
    flat = " ".join(lines)
    ld = _ld(soup)

    it["status"] = STATUS.get(badge.get_text(strip=True), badge.get_text(strip=True))
    it["headline"] = head.get_text(strip=True)
    it["kind"] = "goods" if ld.get("@type") == "Product" else "book"
    it["title"] = (ld.get("name") if ld.get("@type") == "Book" else None) or it["headline"]
    pub = (ld.get("publisher") or {}).get("name") or (ld.get("brand") or {}).get("name") or ""
    it["publisher"] = pub.strip() or None  # 굿즈는 브랜드명
    it["image"] = ld.get("image") or meta(soup, "og:image")
    works = ld.get("workExample") or []
    if works and isinstance(works, list):
        it["isbn"] = works[0].get("isbn")

    if m := re.search(r"([\d,]+)\s*%\s*달성\s*([\d,]+)\s*원\s*목표\s*금액\s*:?\s*([\d,]+)\s*원", flat):
        it["rate"], it["amount"], it["goal"] = (to_int(x) for x in m.groups())

    info = {}
    for li in soup.select(".info_text_list li"):
        k, v = li.select_one(".tit_info"), li.select_one(".txt_info")
        if k and v:
            info[k.get_text(strip=True)] = v.get_text(" ", strip=True)
    ended = it["status"] == "종료"
    st, en = period_from_md(_md(info.get("기간")), ended)
    it["start_date"], it["end_date"] = st, en
    if ship := _md(info.get("발송")):
        ref = date.fromisoformat(en) if en else datetime.now(KST).date()
        it["release_date"] = closest_date(*ship[0], ref, "future").isoformat()

    cat = soup.select_one(".intro_category_list .category_list_item")
    if cat:
        it["category_raw"] = " > ".join(a.get_text(strip=True) for a in cat.select("a"))
    else:
        it["category_raw"] = ld.get("genre")

    benefits = []
    if (i := next((k for k, x in enumerate(lines) if "단독 혜택" in x), None)) is not None:
        benefits += [x for x in lines[i + 1:i + 4] if not x.startswith("-")][:1]
    if (i := next((k for k, x in enumerate(lines) if x == "프로젝트 구성"), None)) is not None:
        for x in lines[i + 1:i + 30]:
            if x == "총 참여 금액":
                break
            if re.match(r"(혜택|구성|옵션)\s*\d*\s*\(", x):
                benefits.append(x)
            elif (p := re.fullmatch(r"([\d,]+)\s*원", x)) and not it["price"]:
                it["price"] = to_int(p.group(1))
    tiers = re.findall(r"참여액\s*(\d+)\s*%\s*적립", info.get("혜택", ""))
    if tiers:
        benefits.append(f"달성 단계별 리뷰 적립 최대 {max(map(int, tiers))}%")
    it["benefits"] = benefits[:8]
    return it


def crawl(known: dict) -> list[dict]:
    main = fetch(MAIN_URL, debug_name="kyobo_main.html", retries=2)
    seeds = ids_on_main(main) if main else set()
    known_ids = {int(k) for k in known}
    top = max(seeds | known_ids, default=0)
    if not top:
        print("[교보] 시드 번호를 찾지 못함")
        return []
    print(f"  메인에서 찾은 번호: {sorted(seeds)}", flush=True)

    targets = set(seeds)
    targets |= {int(k) for k, v in known.items() if v.get("status") != "종료"}
    floor = max(known_ids) if known_ids else top - BOOTSTRAP
    targets |= set(range(floor + 1, top + 1))
    targets |= set(range(top + 1, top + 1 + MAX_AHEAD))

    out, misses_ahead = [], 0
    try:
        for n in sorted(targets):
            if n > top and misses_ahead >= MAX_MISSES:
                break
            d = fetch(DETAIL_URL.format(n), debug_name=f"kyobo_{n}.html")
            it = parse_detail(d, new_item("kyobo", n, DETAIL_URL.format(n))) if d else None
            if it:
                if not is_goods(it):  # 예스24·알라딘과 맞춰 도서 펀딩만
                    out.append(it)
                misses_ahead = 0
            elif n > top:
                misses_ahead += 1
    except SiteDown as e:
        print(f"  ! {e}", flush=True)
    print(f"[교보] {len(out)}건")
    return out


def backfill(known: dict, since: str) -> list[dict]:
    """가장 오래된 수집 번호부터 거꾸로 내려가며 since 이후 펀딩을 채움.
    since 이전 펀딩이나 없는 번호가 연속 STOP번 나오면 멈춤. 중간에 끊겨도 다음 실행에서 이어서 진행."""
    if not known:
        return []
    n, misses, out = min(int(k) for k in known), 0, []
    try:
        while misses < STOP and n > 1:
            n -= 1
            if str(n) in known:
                continue
            d = fetch(DETAIL_URL.format(n), debug_name=f"kyobo_{n}.html")
            it = parse_detail(d, new_item("kyobo", n, DETAIL_URL.format(n))) if d else None
            if it and (ref_date(it) or "9999") >= since:
                if not is_goods(it):
                    out.append(it)
                misses = 0
            else:
                misses += 1
    except SiteDown as e:
        print(f"  ! {e}", flush=True)
    print(f"[교보 과거] {len(out)}건 (마지막 번호 {n})")
    return out
