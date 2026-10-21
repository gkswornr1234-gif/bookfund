"""알라딘 북펀드 — 목록은 서버 렌더링, 상세에 펴낸곳·주제 분류·상품구성이 있음."""
import re

from .common import SiteDown, fetch, soup_of, lines_of, text_of, flat_of, meta, to_int, norm_date, new_item

BASE = "https://www.aladin.co.kr"
LIST_URL = f"{BASE}/m/BookFund/Main.aspx"
DETAIL_URL = f"{BASE}/m/bookfund/view.aspx?pid={{}}"

STATUS_MAP = {"펀딩 중": "진행중", "펀딩중": "진행중", "오늘마감": "마감임박", "오픈예정": "오픈예정",
              "펀딩종료": "종료", "펀딩 종료": "종료", "출간": "종료"}


def _status(lines):
    for s in lines:
        if s in STATUS_MAP:
            return STATUS_MAP[s]
    return None


def parse_list(html: str) -> list[dict]:
    soup = soup_of(html)
    items, seen = [], set()
    for a in soup.select('a[href*="view.aspx?pid="]'):
        m = re.search(r"pid=(\d+)", a["href"])
        if not m or m.group(1) in seen:
            continue
        pid = m.group(1)
        li = a.find_parent("li")
        if li is None:
            continue
        seen.add(pid)
        it = new_item("aladin", pid, DETAIL_URL.format(pid))
        img = a.find("img")
        if img and img.get("alt"):
            it["title"] = re.sub(r"\s*(독자\s*)?북펀드$", "", img["alt"]).strip() or None
            it["image"] = img.get("src")
        lines = text_of(li).split("\n")
        txt = flat_of(li)
        it["status"] = _status(lines)
        if m2 := re.search(r"([\d,]+)\s*원\s*([\d,]+)\s*권\s*펀딩", txt):
            it["amount"], it["count"] = to_int(m2.group(1)), to_int(m2.group(2))
        if m2 := re.search(r"펀딩마감\s*(\d{4}-\d{2}-\d{2})", txt):
            it["end_date"] = m2.group(1)
        if m2 := re.search(r"출간예정\s*(\d{4}-\d{2}-\d{2})", txt):
            it["release_date"] = m2.group(1)
        if m2 := re.search(r"목표\s*금액\s*([\d,]+)\s*원", txt):
            it["goal"] = to_int(m2.group(1))
        items.append(it)
    return items


def parse_detail(html: str, it: dict) -> dict:
    soup = soup_of(html)
    lines = lines_of(soup.body or soup)
    txt = "\n".join(lines)

    if m := re.search(r"도서명\s*:\s*<?(.+?)>?\s*$", txt, re.M):
        it["title"] = m.group(1).strip("<> ")
    elif not it["title"] and (t := meta(soup, "og:title")):
        it["title"] = t.split(" - ")[0].strip()
    it["image"] = it["image"] or meta(soup, "og:image")
    it["price"] = to_int(meta(soup, "og:price")) or it["price"]
    it["isbn"] = meta(soup, "books:isbn")

    # 출판사: '펴낸곳: X' / '- 펴낸 곳: X' / '출판사: X' 등 출판사가 직접 쓴 표기가 제각각
    if m := re.search(r"(?:펴낸\s*곳|출판사)\s*[:：]\s*([^\n]+)", txt):
        it["publisher"] = m.group(1).replace("\xa0", " ").strip(" -:")[:30] or None
    # 분류: '주제 분류:' 다음 줄, '- 분류: 유아>그림책'처럼 같은 줄, 둘 다 처리
    for k, s_ in enumerate(lines):
        if m := re.search(r"분류\s*[:：]\s*(.*)$", s_):
            cands = [m.group(1)] + lines[k + 1:k + 4]
            path = next((c for c in cands if ">" in c), None) or (m.group(1).strip(" -") or None)
            if path:
                it["category_raw"] = re.sub(r"\s*>\s*", " > ", path.strip(" -"))
                break

    flat = " ".join(lines)
    if m := re.search(r"([\d,]+)\s*원\s*,?\s*([\d,]+)\s*권\s*펀딩\s*/?\s*목표\s*금액\s*([\d,]+)\s*원", flat):
        it["amount"], it["count"], it["goal"] = (to_int(x) for x in m.groups())
    if m := re.search(r"(펀딩\s*중|펀딩종료|오픈예정)\s*\(마감\s*([\d-]+),\s*출간예정\s*([\d-]+)\)", txt):
        it["status"] = it["status"] or {"펀딩종료": "종료", "오픈예정": "오픈예정"}.get(m.group(1), "진행중")
        it["end_date"], it["release_date"] = norm_date(m.group(2)), norm_date(m.group(3))

    # 상품구성: 마지막 '상품구성' 제목 ~ '펀딩 달성 단계별' 사이
    benefits = []
    idx = [k for k, s in enumerate(lines) if s.strip("# ").startswith("상품구성")]
    if idx:
        for s in lines[idx[-1] + 1: idx[-1] + 25]:
            if s.startswith("펀딩 달성 단계별") or s.startswith("※"):
                break
            if "상세 보러가기" in s or re.fullmatch(r"[\d.\s]+", s):
                continue
            if benefits and re.fullmatch(r"[\d,]+", benefits[-1]) and s.startswith("원"):
                benefits[-1] += s  # '17,820' + '원 펀딩' → '17,820원 펀딩'
                continue
            benefits.append(s)
    pcts = [int(x) for x in re.findall(r"펀딩한 금액의\s*(\d+)%\s*추가 마일리지", txt)]
    if pcts:
        benefits.append(f"달성 단계별 추가 마일리지 최대 {max(pcts)}%")
    it["benefits"] = benefits[:10]
    if it["goal"] and it["amount"]:
        it["rate"] = round(it["amount"] / it["goal"] * 100)
    return it


def crawl(known: dict) -> list[dict]:
    """known: 이미 저장된 {id: item}. 진행 중이거나 새로 발견한 건만 상세를 다시 읽음."""
    html = fetch(LIST_URL, debug_name="aladin_list.html", retries=2)
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
    print(f"[알라딘] {len(out)}건")
    return out


def _one(it: dict, known: dict) -> None:
    """한 건 처리: 새로 발견했거나 진행 중이면 상세 페이지를 읽음."""
    prev = known.get(it["id"])
    need_detail = prev is None or it["status"] in ("진행중", "마감임박", "오픈예정")
    if need_detail:
        d = fetch(DETAIL_URL.format(it["id"]), debug_name=f"aladin_{it['id']}.html")
        if d:
            parse_detail(d, it)
    elif it["goal"] and it["amount"]:
        it["rate"] = round(it["amount"] / it["goal"] * 100)
