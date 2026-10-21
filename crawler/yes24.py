"""YES24 예스펀딩(그래제본소).
목록 카드(.fUnit): 제목·달성률·펀딩액·남은 일수·상품번호
상세(.stateDl): 펀딩액·펀딩수(부)·목표액·기간, 펀딩 구성(.stepBoxUnit): 펀딩가·구성품
상품 페이지(/product/goods/{상품번호}): 출판사·분야 — 펀딩 페이지에는 없어서 따로 읽음"""
import re

from .common import (SiteDown, fetch, soup_of, lines_of, to_int, days_later, period_from_md, new_item)

BASE = "https://www.yes24.com"
LIST_URL = f"{BASE}/Mall/YesFunding/Main?gb=BOOK"  # gb=BOOK: 그래제본소(도서)만
DETAIL_URL = f"{BASE}/campaign/01_Book/yesFunding/yesFundingBook.aspx?EventNo={{}}"
GOODS_URL = f"{BASE}/product/goods/{{}}"
ENC = "cp949"


def _status(ico: str, txt: str) -> str | None:
    if "마감임박" in txt:
        return "마감임박"
    if "진행" in ico:
        return "진행중"
    if re.search(r"예정|오픈", ico):
        return "오픈예정"
    if re.search(r"종료|성공|마감|실패", ico):
        return "종료"
    return None


def parse_list(html: str) -> list[dict]:
    soup = soup_of(html)
    items = []
    for u in soup.select(".fUnit"):
        a = u.select_one('a[href*="EventNo="]')
        m = re.search(r"EventNo=(\d+)", a["href"]) if a else None
        if not m:
            continue
        it = new_item("yes24", m.group(1), DETAIL_URL.format(m.group(1)))
        g = lambda sel: (e.get_text(" ", strip=True) if (e := u.select_one(sel)) else "")
        it["title"] = g(".info_tit") or None
        it["rate"] = to_int(g(".num_per .yes_b"))
        it["amount"] = to_int(g(".num_won .yes_b"))
        sta = g(".staTxt")
        it["status"] = _status(g(".staIco"), sta)
        if d := re.search(r"(\d+)\s*일\s*남음", sta):
            it["end_date"] = days_later(int(d.group(1)))
        it["goods_id"] = u.get("data-product-id") or None
        if (img := u.select_one(".fImg")) and (bg := re.search(r"url\('?([^')]+)", img.get("style", ""))):
            it["image"] = bg.group(1)
        items.append(it)
    return items


def parse_detail(html: str, it: dict) -> dict:
    soup = soup_of(html)
    state = {}
    for dl in soup.select(".stateDl dl"):
        if (dt := dl.find("dt")) and (dd := dl.find("dd")):
            state[dt.get_text(strip=True)] = dd.get_text(" ", strip=True)
    it["amount"] = to_int(state.get("펀딩액")) or it["amount"]
    it["count"] = to_int(re.sub(r"부.*", "", state.get("펀딩수", ""))) or None
    it["goal"] = to_int(state.get("목표액")) or None
    pairs = [(int(m), int(d)) for m, d in re.findall(r"(\d{1,2})/(\d{1,2})", state.get("기간", ""))]
    s, e = period_from_md(pairs)
    it["start_date"], it["end_date"] = s or it["start_date"], e or it["end_date"]
    if it["goal"] and it["amount"] is not None:
        it["rate"] = round(it["amount"] / it["goal"] * 100)
    if ico := soup.select_one(".stateDl .state_ico"):
        it["status"] = _status(ico.get_text(strip=True), "") if it["status"] != "마감임박" else it["status"]

    # 펀딩 구성: '15,120원: 『책』 1부, 키캡 키링'
    options, prices = [], []
    for u in soup.select(".stepBoxUnit"):
        inp = u.select_one("input[name=fundingGoods]")
        if not inp:
            continue
        gid, _, price = (inp.get("value") or "").partition("♂")
        prices.append(to_int(price))
        it["goods_id"] = it.get("goods_id") or gid or None
        parts = [li.get_text(" ", strip=True) for li in u.select("li")]
        parts = [p for p in parts if p and not re.search(r"달성(액)?별", p)]
        if parts:
            options.append(f"{to_int(price):,}원: {', '.join(parts)}" if to_int(price) else ", ".join(parts))
    prices = [p for p in prices if p]
    if prices:
        it["price"] = min(prices)
    benefits = options[:6]
    txt = "\n".join(lines_of(soup.body or soup))
    tiers = [int(x) for x in re.findall(r"펀딩 참여액의\s*(\d+)\s*%\s*포인트", txt)]
    if tiers:
        benefits.append(f"달성 단계별 한줄평 적립 최대 {max(tiers)}%")
    it["benefits"] = benefits
    if m := re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*이후\s*발송", txt):
        it["release_date"] = f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    return it


def parse_goods(html: str, it: dict) -> None:
    """상품 페이지에서 출판사·분야. 구조가 바뀌어도 하나는 걸리도록 후보를 여러 개 둠."""
    soup = soup_of(html)
    for sel in (".gd_pub a", ".gd_pub", "span.gd_pub"):
        if (el := soup.select_one(sel)) and el.get_text(strip=True):
            it["publisher"] = el.get_text(strip=True)
            break
    if not it["publisher"] and (m := re.search(r'"publisher"\s*:\s*\{[^}]*?"name"\s*:\s*"([^"]+)"', html)):
        it["publisher"] = m.group(1)
    for sel in ("#infoset_goodsCate li", ".yesAlertLi li", ".gd_cate li"):
        cats = [re.sub(r"\s+", " ", li.get_text(" ", strip=True)) for li in soup.select(sel)]
        cats = [c for c in cats if ">" in c]
        if cats:
            it["category_raw"] = re.sub(r"\s*>\s*", " > ", cats[0])
            break
    if not it["category_raw"] and (m := re.search(r'"genre"\s*:\s*"([^"]+)"', html)):
        it["category_raw"] = m.group(1)


def crawl(known: dict) -> list[dict]:
    html = fetch(LIST_URL, encoding=ENC, debug_name="yes24_list.html", retries=2)
    if not html:
        return []
    out = []
    for it in parse_list(html):
        try:
            _one(it, known)
        except SiteDown as e:
            print(f"  ! {e}", flush=True)
            break
        out.append(it)
    print(f"[YES24] {len(out)}건")
    return out


def _one(it: dict, known: dict) -> None:
    """새로 발견했거나 진행 중이면 상세를 읽고, 출판사·분야가 없으면 상품 페이지도 읽음."""
    prev = known.get(it["id"]) or {}
    if prev and it["status"] == "종료":
        return
    if d := fetch(it["url"], encoding=ENC, debug_name=f"yes24_{it['id']}.html"):
        parse_detail(d, it)
    if not (prev.get("publisher") and prev.get("category_raw")) and it.get("goods_id"):
        if g := fetch(GOODS_URL.format(it["goods_id"]), debug_name=f"yes24_goods_{it['goods_id']}.html"):
            parse_goods(g, it)
