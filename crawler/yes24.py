"""YES24 예스펀딩(그래제본소) — 목록에 달성률·금액·남은 일수, 상세/상품 페이지에 출판사·분야."""
import re

from .common import (flat_of, SiteDown, fetch, soup_of, lines_of, to_int, days_later, find_date_range,
                     label_value, benefit_lines, new_item)

BASE = "https://www.yes24.com"
LIST_URL = f"{BASE}/Mall/YesFunding/Main?gb=BOOK"  # gb=BOOK: 그래제본소(도서)만
DETAIL_URL = f"{BASE}/campaign/01_Book/yesFunding/yesFundingBook.aspx?EventNo={{}}"
GOODS_URL = f"{BASE}/product/goods/{{}}"
ENC = "cp949"


def parse_list(html: str) -> list[dict]:
    soup = soup_of(html)
    items, seen = [], set()
    for a in soup.select('a[href*="yesFundingBook.aspx?EventNo="]'):
        m = re.search(r"EventNo=(\d+)", a["href"])
        if not m or m.group(1) in seen:
            continue
        no = m.group(1)
        # 링크에서 위로 올라가며 '달성'이 들어 있는 카드 컨테이너를 찾음
        box = a
        for _ in range(6):
            box = box.parent
            if box is None or "달성" in box.get_text():
                break
        if box is None:
            continue
        seen.add(no)
        it = new_item("yes24", no, DETAIL_URL.format(no))
        txt = flat_of(box)
        if t := re.search(r"'([^']+)'\s*펀딩 바로가기", txt):
            it["title"] = t.group(1).strip()
        if t := re.search(r"(\d+)\s*%\s*달성\s*([\d,]+)\s*원", txt):
            it["rate"], it["amount"] = int(t.group(1)), to_int(t.group(2))
        if t := re.search(r"(\d+)일 남음", txt):
            it["end_date"] = days_later(int(t.group(1)))
            it["status"] = "진행중"
        elif "마감임박" in txt:
            it["status"] = "마감임박"
        elif "오픈예정" in txt or "오픈 예정" in txt:
            it["status"] = "오픈예정"
        elif "종료" in txt:
            it["status"] = "종료"
        img = box.find("img")
        if img:
            it["image"] = img.get("src") or img.get("data-original")
        items.append(it)
    return items


def parse_goods(html: str, it: dict) -> None:
    """상품 상세에서 출판사·분야·정가 (YES24 상품 페이지 공통 구조)."""
    soup = soup_of(html)
    if el := soup.select_one(".gd_pub"):
        it["publisher"] = it["publisher"] or el.get_text(strip=True)
    cats = [li.get_text(" ", strip=True) for li in soup.select("#infoset_goodsCate li")]
    if cats:
        it["category_raw"] = it["category_raw"] or re.sub(r"\s+", " ", cats[0])
    if el := soup.select_one(".gd_infoTb .nor_price, .nor_price em"):
        it["price"] = it["price"] or to_int(el.get_text())


def parse_detail(html: str, it: dict) -> dict:
    soup = soup_of(html)
    lines = lines_of(soup.body or soup)
    txt = "\n".join(lines)
    it["publisher"] = label_value(txt, ("출판사", "펴낸곳"))
    it["category_raw"] = label_value(txt, ("분야", "카테고리"))
    s, e = find_date_range(txt)
    it["start_date"], it["end_date"] = s or it["start_date"], e or it["end_date"]
    if m := re.search(r"목표\s*금액\s*[:：]?\s*([\d,]+)\s*원", txt):
        it["goal"] = to_int(m.group(1))
    if m := re.search(r"(?:펀딩가|펀딩\s*금액|판매가)\s*[:：]?\s*([\d,]+)\s*원", txt):
        it["price"] = to_int(m.group(1))
    if m := re.search(r"([\d,]+)\s*(?:명|분)(?:이|의)?\s*(?:참여|후원|펀딩)", txt):
        it["backers"] = to_int(m.group(1))
    it["benefits"] = benefit_lines(lines)
    # 펀딩 상품의 실제 상품번호가 있으면 상품 페이지로 출판사·분야 보완
    if not (it["publisher"] and it["category_raw"]):
        if m := re.search(r"/(?:Product/Goods|product/goods)/(\d+)", html):
            g = fetch(GOODS_URL.format(m.group(1)), debug_name=f"yes24_goods_{m.group(1)}.html")
            if g:
                parse_goods(g, it)
    return it


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
    """한 건 처리: 새로 발견했거나 진행 중이면 상세 페이지를 읽음."""
    prev = known.get(it["id"])
    if prev is None or it["status"] != "종료":
        d = fetch(it["url"], encoding=ENC, debug_name=f"yes24_{it['id']}.html")
        if d:
            parse_detail(d, it)
    if it["amount"] and it["price"] and not it["count"]:
        it["count_est"] = round(it["amount"] / it["price"])
