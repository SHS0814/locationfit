from __future__ import annotations

import re
from typing import Literal


StoreRelation = Literal["competitor", "complementary", "daily_life", "other"]


# Seoul's service-industry taxonomy and the Small Enterprise and Market Service
# taxonomy do not share codes. Keep the matching terms explicit so a taxonomy
# change is reviewable and never delegated to the LLM.
COMPETITOR_TERMS: dict[str, tuple[str, ...]] = {
    "CS100001": ("한식", "한식음식점"),
    "CS100002": ("중식", "중국음식", "중화요리"),
    "CS100003": ("일식", "일본음식", "초밥", "스시"),
    "CS100004": ("양식", "서양식", "이탈리안", "프랑스음식"),
    "CS100005": ("제과점", "제과제빵", "빵", "베이커리"),
    "CS100006": ("패스트푸드", "햄버거", "피자"),
    "CS100007": ("치킨", "닭강정"),
    "CS100008": ("분식", "김밥", "떡볶이"),
    "CS100009": ("호프", "맥주", "간이주점", "주점"),
    "CS100010": ("커피", "카페", "음료", "차전문점"),
    "CS200001": ("일반교습학원", "입시학원", "보습학원"),
    "CS200002": ("외국어학원", "영어학원", "어학원"),
    "CS200003": ("예술학원", "음악학원", "미술학원", "무용학원"),
    "CS200005": ("스포츠강습", "체육학원", "태권도", "요가", "필라테스"),
    "CS200006": ("일반의원", "내과의원", "외과의원", "소아청소년과", "이비인후과"),
    "CS200007": ("치과",),
    "CS200008": ("한의원", "한방병원"),
    "CS200016": ("당구장", "당구"),
    "CS200017": ("골프연습장", "스크린골프"),
    "CS200019": ("PC방", "피시방", "컴퓨터게임방"),
    "CS200024": ("스포츠클럽", "헬스장", "체력단련장", "피트니스"),
    "CS200025": ("자동차수리", "카센터", "자동차정비"),
    "CS200026": ("자동차미용", "세차", "광택"),
    "CS200028": ("미용실", "헤어", "두발미용"),
    "CS200029": ("네일", "손톱미용"),
    "CS200030": ("피부관리", "피부미용", "마사지"),
    "CS200031": ("세탁소", "세탁"),
    "CS200032": ("가전제품수리", "가전수리"),
    "CS200033": ("부동산중개", "공인중개"),
    "CS200034": ("여관", "모텔", "숙박"),
    "CS200036": ("고시원", "고시텔"),
    "CS200037": ("노래방", "노래연습장"),
    "CS300001": ("슈퍼마켓", "슈퍼", "식료품종합소매"),
    "CS300002": ("편의점",),
    "CS300003": ("컴퓨터", "컴퓨터주변장치"),
    "CS300004": ("핸드폰", "휴대폰", "통신기기"),
    "CS300006": ("미곡", "곡물", "쌀"),
    "CS300007": ("육류", "정육", "식육"),
    "CS300008": ("수산물", "생선", "해산물"),
    "CS300009": ("청과", "과일", "채소"),
    "CS300010": ("반찬",),
    "CS300011": ("일반의류", "의류", "옷"),
    "CS300014": ("신발", "구두"),
    "CS300015": ("가방", "핸드백"),
    "CS300016": ("안경", "콘택트렌즈"),
    "CS300017": ("시계", "귀금속", "주얼리"),
    "CS300018": ("의약품", "약국"),
    "CS300019": ("의료기기", "의료용품"),
    "CS300020": ("서적", "서점"),
    "CS300021": ("문구", "사무용품"),
    "CS300022": ("화장품",),
    "CS300024": ("운동용품", "스포츠용품", "경기용품"),
    "CS300025": ("자전거", "전동킥보드", "운송장비"),
    "CS300026": ("완구", "장난감"),
    "CS300027": ("섬유제품", "침구", "수예"),
    "CS300028": ("화초", "꽃", "화훼"),
    "CS300029": ("애완동물", "반려동물", "펫"),
    "CS300031": ("가구",),
    "CS300032": ("가전제품", "전자제품"),
    "CS300033": ("철물", "건축자재"),
    "CS300035": ("인테리어", "실내장식"),
    "CS300036": ("조명", "전구"),
    "CS300043": ("전자상거래", "통신판매"),
}

FOOD_CODES = {code for code in COMPETITOR_TERMS if code.startswith("CS100")}
EDUCATION_CODES = {"CS200001", "CS200002", "CS200003", "CS200005"}
MEDICAL_CODES = {"CS200006", "CS200007", "CS200008", "CS300018", "CS300019"}
SPORT_CODES = {"CS200005", "CS200016", "CS200017", "CS200024", "CS300024"}
AUTO_CODES = {"CS200025", "CS200026", "CS300025"}
BEAUTY_CODES = {"CS200028", "CS200029", "CS200030", "CS300022"}
LODGING_CODES = {"CS200034", "CS200036"}

DAILY_LIFE_TERMS = (
    "편의점", "슈퍼마켓", "약국", "의원", "병원", "은행", "우체국",
    "세탁", "학원", "보육", "어린이집", "부동산중개", "문구",
)


def _normalise(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).lower()


def _contains_any(haystack: str, terms: tuple[str, ...] | list[str]) -> bool:
    return any(_normalise(term) in haystack for term in terms if term)


def complementary_terms(industry_code: str) -> tuple[str, ...]:
    if industry_code in FOOD_CODES:
        return ("커피", "카페", "음료", "제과", "빵", "편의점", "주점", "음식점")
    if industry_code in EDUCATION_CODES:
        return ("문구", "서점", "서적", "카페", "편의점", "독서실")
    if industry_code in MEDICAL_CODES:
        return ("약국", "의료기기", "건강용품", "안경")
    if industry_code in SPORT_CODES:
        return ("운동용품", "스포츠용품", "건강식품", "음료", "마사지")
    if industry_code in AUTO_CODES:
        return ("자동차부품", "주유소", "타이어", "세차", "자동차정비")
    if industry_code in BEAUTY_CODES:
        return ("화장품", "미용", "네일", "피부", "의류")
    if industry_code in LODGING_CODES:
        return ("편의점", "음식점", "카페", "세탁")
    if industry_code.startswith("CS300"):
        return ("편의점", "카페", "음식점", "택배", "수리")
    return ()


def classify_store(industry_code: str, *category_names: str) -> StoreRelation:
    if industry_code not in COMPETITOR_TERMS:
        raise ValueError(f"지원하지 않는 추천 업종 코드입니다: {industry_code}")
    text = _normalise(" ".join(value for value in category_names if value))
    if _contains_any(text, COMPETITOR_TERMS[industry_code]):
        return "competitor"
    if _contains_any(text, complementary_terms(industry_code)):
        return "complementary"
    if _contains_any(text, DAILY_LIFE_TERMS):
        return "daily_life"
    return "other"

