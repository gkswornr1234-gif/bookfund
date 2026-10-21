"""교보 바로펀딩 — 목록은 JS로 불러오므로, 메인에 노출된 상세 번호를 시드로 삼고
앞뒤 번호를 탐색해 새 프로젝트를 찾음 (/funding/detail/{번호})."""
import json
import re
from datetime import date, datetime

from .common import SiteDown, KST, fetch, soup_of, lines_of, meta, to_int, new_item

BASE = "https://event.kyobobook.co.kr"
MAIN_URL = f"{BASE}/funding"
DETAIL_URL = f"{BASE}/funding/detail/{{}}"
BOOTSTRAP = 40      # 첫 실행 때 최신 번호에서 거꾸로 훑을 개수
MAX_MISSES = 5      # 최신 번호 이후 연속으로 비어 있으면 탐색 중단
MAX_AHEAD = 20      # 최신 번호 이후 최대 탐색 개수 (무한 탐색 방지)

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


def _closest(m: int, d: int, ref: date) -> date:
    """연도 없는 'M월 D일'을 기준일에 가장 가까운 연도로."""
    cands = []
    for y in (ref.year - 1, ref.year, ref.year + 1):
        try:
            cands.append(date(y, m, d))
        except ValueError:
            pass
    return min(cands, key=lambda x: abs((x - ref).days))


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
    today_ = datetime.now(KST).date()
    period = _md(info.get("기간"))
    if period:
        end = _closest(*period[-1], today_)
        it["end_date"] = end.isoformat()
        if len(period) > 1:
            st = _closest(*period[0], end)
            it["start_date"] = (st if st <= end else st.replace(year=st.year - 1)).isoformat()
    if ship := _md(info.get("발송")):
        ref = date.fromisoformat(it["end_date"]) if it["end_date"] else today_
        it["release_date"] = _closest(*ship[0], ref).isoformat()

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
                out.append(it)
                misses_ahead = 0
            elif n > top:
                misses_ahead += 1
    except SiteDown as e:
        print(f"  ! {e}", flush=True)
    print(f"[교보] {len(out)}건")
    return out
