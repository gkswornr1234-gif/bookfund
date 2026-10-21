"""공통 유틸 — 요청, 텍스트 추출, 숫자/날짜 파싱."""
import os
import re
import time
import random
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
DEBUG_DIR = os.environ.get("DEBUG_DIR")  # 지정하면 받은 HTML을 저장 (셀렉터 점검용)

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})


def today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def fetch(url: str, encoding: str | None = None, debug_name: str | None = None) -> str | None:
    """GET 후 텍스트 반환. 실패 시 None. 서버 부담을 줄이려고 요청 사이 0.8~1.6초 쉼."""
    time.sleep(random.uniform(0.8, 1.6))
    try:
        r = _session.get(url, timeout=20)
    except requests.RequestException as e:
        print(f"  ! 요청 실패 {url}: {e}")
        return None
    if r.status_code != 200:
        print(f"  ! HTTP {r.status_code} {url}")
        return None
    if encoding:
        r.encoding = encoding
    elif not r.encoding or r.encoding.lower() in ("iso-8859-1", "ks_c_5601-1987"):
        r.encoding = r.apparent_encoding or "utf-8"
    html = r.text
    if DEBUG_DIR and debug_name:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        with open(os.path.join(DEBUG_DIR, debug_name), "w", encoding="utf-8") as f:
            f.write(html)
    return html


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def lines_of(node) -> list[str]:
    """노드의 텍스트를 줄 단위로, 공백 줄 제거."""
    text = node.get_text("\n")
    return [re.sub(r"\s+", " ", s).strip() for s in text.split("\n") if s.strip()]


def text_of(node) -> str:
    return "\n".join(lines_of(node))


def meta(soup: BeautifulSoup, key: str) -> str | None:
    tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
    return tag.get("content").strip() if tag and tag.get("content") else None


def to_int(s) -> int | None:
    if s is None:
        return None
    digits = re.sub(r"[^\d]", "", str(s))
    return int(digits) if digits else None


DATE_RE = r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"


def norm_date(s: str | None) -> str | None:
    if not s:
        return None
    m = re.search(DATE_RE, s)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def find_date_range(text: str) -> tuple[str | None, str | None]:
    """'2026.10.01 ~ 2026.10.20' 같은 기간 표기에서 시작/종료일 추출."""
    m = re.search(DATE_RE + r"[^\d]{0,20}?~\s*" + DATE_RE, text)
    if not m:
        return None, None
    g = m.groups()
    return norm_date("-".join(g[:3])), norm_date("-".join(g[3:]))


def days_later(n: int) -> str:
    return (datetime.now(KST) + timedelta(days=n)).strftime("%Y-%m-%d")


BENEFIT_WORDS = ("증정", "사은품", "굿즈", "적립", "할인", "특별판", "한정", "에디션", "사인", "면지", "부록", "포토카드", "엽서", "책갈피")


def benefit_lines(lines: list[str], limit: int = 6) -> list[str]:
    """혜택으로 보이는 짧은 줄만 추림 (구조를 모르는 페이지용 보조 수단)."""
    out = []
    for s in lines:
        if 4 <= len(s) <= 70 and any(w in s for w in BENEFIT_WORDS) and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def label_value(text: str, labels: tuple[str, ...]) -> str | None:
    """'출판사 : 마름모' / '출판사\\n마름모' 형태에서 값 추출."""
    for lb in labels:
        m = re.search(rf"{lb}\s*[:：]?\s*\n?\s*([^\n|]{{1,40}})", text)
        if m:
            v = m.group(1).strip(" :：")
            if v and v not in labels:
                return v
    return None


def new_item(store: str, item_id: str, url: str) -> dict:
    return {
        "store": store,
        "id": str(item_id),
        "url": url,
        "title": None,
        "publisher": None,
        "category_raw": None,
        "status": None,
        "start_date": None,
        "end_date": None,
        "release_date": None,
        "price": None,
        "goal": None,
        "amount": None,
        "count": None,
        "rate": None,
        "benefits": [],
        "image": None,
    }
