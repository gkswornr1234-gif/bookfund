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

YES24_LIST = """<html><body><ul>
<li><div class="info"><p>봄 내음보다 너를</p><p>노래를 그림책으로 만나다</p><p>48%달성 483,840원</p>
<p><em>펀딩 진행중</em> 12일 남음</p></div>
<a href="https://www.yes24.com/campaign/01_Book/yesFunding/yesFundingBook.aspx?EventNo=277354"><em>3</em><span>'봄 내음보다 너를' 펀딩 바로가기</span></a></li>
<li><div><p>갖고 싶어요</p><p>118%달성 1,177,240원</p><p><em>펀딩 진행중</em> 마감임박</p></div>
<a href="https://www.yes24.com/campaign/01_Book/yesFunding/yesFundingBook.aspx?EventNo=276961"><span>'갖고 싶어요' 펀딩 바로가기</span></a></li>
</ul></body></html>"""

YES24_DETAIL = """<html><body><dl><dt>출판사</dt><dd>북스토리</dd><dt>펀딩 기간</dt>
<dd>2026.10.05 ~ 2026.11.01</dd><dt>목표 금액</dt><dd>1,000,000원</dd></dl>
<p>펀딩가 18,000원</p><p>참여자 전원 친필 사인본 증정</p><p>한정판 엽서 세트 증정</p></body></html>"""

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


def test_yes24_list_and_detail():
    items = yes24.parse_list(YES24_LIST)
    assert [i["id"] for i in items] == ["277354", "276961"]
    a = items[0]
    assert (a["title"], a["rate"], a["amount"], a["status"]) == ("봄 내음보다 너를", 48, 483840, "진행중")
    assert items[1]["status"] == "마감임박"
    yes24.parse_detail(YES24_DETAIL, a)
    assert a["publisher"] == "북스토리"
    assert (a["start_date"], a["end_date"], a["goal"], a["price"]) == ("2026-10-05", "2026-11-01", 1000000, 18000)
    assert "참여자 전원 친필 사인본 증정" in a["benefits"]


def test_kyobo():
    assert kyobo.ids_on_main(KYOBO_MAIN) == {662, 672}
    it = kyobo.parse_detail(KYOBO_DETAIL, kyobo.new_item("kyobo", 672, "u"))
    assert it["title"] == "반복되는 허리 통증의 진짜 원인"
    assert (it["rate"], it["amount"], it["status"], it["publisher"]) == (554, 5540000, "진행중", "비타북스")
    assert (it["start_date"], it["end_date"]) == ("2026-10-10", "2026-10-31")
    assert kyobo.parse_detail("<html><title>바로펀딩 - 교보문고</title></html>", kyobo.new_item("kyobo", 1, "u")) is None


def test_yes24_split_tags():
    html = """<li><p>책</p><span class="per"><em>48</em>%달성</span><span><em>483,840</em>원</span>
    <p>12일 남음</p><a href="/campaign/01_Book/yesFunding/yesFundingBook.aspx?EventNo=1"><span>'책' 펀딩 바로가기</span></a></li>"""
    it = yes24.parse_list(html)[0]
    assert (it["rate"], it["amount"]) == (48, 483840)


def test_label_value_skips_headings():
    it = yes24.new_item("yes24", "1", "u")
    yes24.parse_detail("<html><body><h3>출판사 리뷰</h3><p>좋은 책입니다</p></body></html>", it)
    assert it["publisher"] is None


def test_kyobo_generic_page_is_miss():
    html = '<html><head><meta property="og:title" content="교보문고"></head><body>바로펀딩 안내</body></html>'
    assert kyobo.parse_detail(html, kyobo.new_item("kyobo", 9999, "u")) is None


def test_aladin_split_tags():
    html = """<ul><li><a href="view.aspx?pid=1"><img alt="책 북펀드"></a><span>펀딩 중</span>
    <p><em>6,433,020</em>원 <em>361</em>권 펀딩</p><p>목표금액 <em>1,000,000</em>원</p></li></ul>"""
    it = aladin.parse_list(html)[0]
    assert (it["amount"], it["count"], it["goal"]) == (6433020, 361, 1000000)


def test_kyobo_title_brand_and_period():
    html = """<html><head><meta property="og:title" content="바로펀딩 | 무한 스크롤"></head><body>
    <a>브랜드관</a><p>113% 달성</p><p>567,000 원</p><p>발송 2026.11.15 ~</p>
    <dl><dt>펀딩 기간</dt><dd>2026.10.15 ~ 2026.11.14</dd><dt>출판사</dt><dd>비타북스</dd></dl></body></html>"""
    it = kyobo.parse_detail(html, kyobo.new_item("kyobo", 1, "u"))
    assert it["title"] == "무한 스크롤"
    assert it["publisher"] == "비타북스"
    assert (it["start_date"], it["end_date"]) == ("2026-10-15", "2026-11-14")
