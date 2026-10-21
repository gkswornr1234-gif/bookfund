"""2026-10 시점 페이지 구조를 본뜬 픽스처로 파서 동작 확인. python -m pytest tests"""
from crawler import aladin, yes24, kyobo

ALADIN_LIST = """<html><body><ul>
<li><a href="https://www.aladin.co.kr/m/bookfund/view.aspx?pid=3029"><img alt="일은 당신에게 위험하다 북펀드" src="a.jpg"></a>
<div><span>펀딩 중</span><p>6,433,020원 361권 펀딩</p><p>100자평 작성하면 추가 마일리지 4% 적립</p>
<dl><dt>펀딩마감</dt><dd>2026-10-20</dd><dt>출간예정</dt><dd>2026-11-16</dd><dt>목표금액</dt><dd>1,000,000원</dd></dl></div></li>
<li><a href="https://www.aladin.co.kr/m/bookfund/view.aspx?pid=2993"><img alt="의존하지 않는 마음 북펀드" src="b.jpg"></a>
<div><span>펀딩종료</span><p>1,821,600원 92권 펀딩</p><dl><dt>펀딩마감</dt><dd>2026-10-07</dd></dl></div></li>
<li><a href="https://www.aladin.co.kr/m/bookfund/view.aspx?pid=3016"><img alt="명자 북펀드"></a><span>오늘마감</span></li>
</ul></body></html>"""

ALADIN_DETAIL = """<html><head>
<meta property="og:title" content="일은 당신에게 위험하다 - 여성의 몸이 먼저 알아챈 것들">
<meta property="og:price" content="17820"><meta name="books:isbn" content="K112131892"></head><body>
<p>1,193,940원, 67권 펀딩 / 목표 금액 1,000,000원</p>
<p>펀딩 중 (마감 2026-10-20, 출간예정 2026-11-16)</p>
<h2>도서 정보</h2><p><b>도서명: &lt;일은 당신에게 위험하다&gt;</b><br>주제 분류:<br>
국내도서 &gt; 사회과학 &gt; 사회문제 &gt; 노동문제<br>국내도서 &gt; 인문학 &gt; 문화/문화이론<br>
펴낸곳: 마름모<br>정가: 19,800원</p>
<h2>상품구성 <a>상세 보러가기 &gt;</a></h2><b>1. 17,820원 펀딩</b>
<h2>상품구성</h2><ol><li><b>17,820</b>원 펀딩</li></ol>
<ul><li>&lt;일은 당신에게 위험하다&gt; 도서 1부</li><li>후원자명 면지 인쇄</li><li>펀딩 달성 단계별 추가 마일리지 적립</li></ul>
<h2>펀딩 달성 단계별 추가 마일리지</h2>
<ul><li>4,000,000원 이상 펀딩<br>펀딩한 금액의 4% 추가 마일리지 적립</li>
<li>1,000,000원 이상 펀딩 달성 펀딩금액의 1% 추가 마일리지 적립</li></ul></body></html>"""



KYOBO_MAIN = """<a href="https://event.kyobobook.co.kr/funding/detail/662">a</a>
<a href="https://event.kyobobook.co.kr/funding/detail/672">b</a>"""

KYOBO_DETAIL = """<html><head><meta property="og:title" content="반복되는 허리 통증의 진짜 원인 - 바로펀딩"></head>
<body><span>진행 중</span><p>554% 달성</p><p>5,540,000 원</p><dl><dt>펀딩 기간</dt><dd>2026.10.10 ~ 2026.10.31</dd>
<dt>출판사</dt><dd>비타북스</dd></dl><p>교보 단독 사은품 폼롤러 증정</p></body></html>"""


def test_aladin_list():
    items = aladin.parse_list(ALADIN_LIST)
    assert [i["id"] for i in items] == ["3029", "2993", "3016"]
    a = items[0]
    assert a["title"] == "일은 당신에게 위험하다"
    assert (a["amount"], a["count"], a["goal"]) == (6433020, 361, 1000000)
    assert (a["end_date"], a["release_date"], a["status"]) == ("2026-10-20", "2026-11-16", "진행중")
    assert items[1]["status"] == "종료" and items[2]["status"] == "마감임박"


def test_aladin_detail():
    it = aladin.parse_detail(ALADIN_DETAIL, aladin.parse_list(ALADIN_LIST)[0])
    assert it["publisher"] == "마름모"
    assert it["category_raw"].startswith("국내도서 > 사회과학")
    assert it["price"] == 17820 and it["count"] == 67 and it["rate"] == 119
    assert "후원자명 면지 인쇄" in it["benefits"]
    assert it["benefits"][-1] == "달성 단계별 추가 마일리지 최대 4%"





def test_aladin_split_tags():
    html = """<ul><li><a href="view.aspx?pid=1"><img alt="책 북펀드"></a><span>펀딩 중</span>
    <p><em>6,433,020</em>원 <em>361</em>권 펀딩</p><p>목표금액 <em>1,000,000</em>원</p></li></ul>"""
    it = aladin.parse_list(html)[0]
    assert (it["amount"], it["count"], it["goal"]) == (6433020, 361, 1000000)



# ---- 2026-10 실제 페이지 저장본으로 검증 (tests/fixtures)
import os
FX = os.path.join(os.path.dirname(__file__), "fixtures")
read = lambda n: open(os.path.join(FX, n), encoding="utf-8").read()


def test_kyobo_real_detail():
    it = kyobo.parse_detail(read("kyobo_672.html"), kyobo.new_item("kyobo", 672, "u"))
    assert it["title"] == "디스크는 죄가 없다"
    assert it["headline"] == "반복되는 허리 통증의 진짜 원인"
    assert it["publisher"] == "알에이치코리아"
    assert it["category_raw"] == "국내도서 > 건강 > 질병치료/예방 > 디스크/척추"
    assert it["status"] == "마감임박"
    assert (it["rate"], it["amount"], it["goal"], it["price"]) == (766, 11502000, 1500000, 18000)
    assert it["start_date"].endswith("-10-07") and it["end_date"].endswith("-10-22")
    assert any("운동 포스터" in b for b in it["benefits"])


def test_kyobo_missing_number():
    assert kyobo.parse_detail(read("kyobo_684.html"), kyobo.new_item("kyobo", 684, "u")) is None


def test_aladin_real():
    items = aladin.parse_list(read("aladin_list.html"))
    assert len(items) >= 50 and all(i["amount"] is not None for i in items[:10])
    it = next(i for i in items if i["id"] == "3037")
    aladin.parse_detail(read("aladin_3037.html"), it)
    assert it["publisher"] == "도서출판 날"
    assert it["category_raw"] == "에세이 > 한국에세이"
    assert it["benefits"][0] == "15,120원 펀딩"


def test_yes24_real():
    items = yes24.parse_list(read("yes24_list.html"))
    assert len(items) == 21
    a = items[0]
    assert (a["title"], a["rate"], a["amount"], a["status"], a["goods_id"]) == ("나로 걷는 길, 고요하게 단단하게", 101, 1013040, "진행중", "198278278")
    assert len({i["end_date"] for i in items}) > 3  # 카드마다 마감일이 달라야 함
    it = next(i for i in items if i["id"] == "277008")
    yes24.parse_detail(read("yes24_277008.html"), it)
    assert (it["amount"], it["count"], it["goal"], it["price"]) == (1219500, 76, 1000000, 15120)
    assert it["start_date"].endswith("-10-02") and it["end_date"].endswith("-10-25")
    assert it["benefits"][1] == "16,500원: 『불량 로봇 릭스비 1』 1부, 키캡 키링(랜덤 1종)"
