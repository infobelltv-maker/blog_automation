"""
네이버 데이터랩 SEO 엔진
- 검색어 트렌드 API (40~50대 필터)
- 쇼핑인사이트 API
- 네이버 검색 API (경쟁 블로그 Top 5)
- 키워드 추출 (Gemini)
"""
import os
import hmac
import hashlib
import base64
import time
import re
import requests
from datetime import datetime, timedelta
from utils.logger import get_logger
from utils.gemini_call import call_gemini
from config import get_secret

log = get_logger('seo_engine')

CATEGORY_MAP = {
    '식품':       '50000008',
    '건강식품':   '50000009',
    '생활주방':   '50000006',
    '가전디지털': '50000002',
    '패션의류':   '50000000',
    '스포츠레저': '50000012',
    '출산육아':   '50000003',
    '반려동물':   '50000015',
    '뷰티':       '50000001',
    '홈인테리어': '50000005',
}


# ══════════════════════════════════════
#  API 헤더
# ══════════════════════════════════════

def _datalab_headers():
    return {
        'X-Naver-Client-Id':     get_secret('NAVER_CLIENT_ID'),
        'X-Naver-Client-Secret': get_secret('NAVER_CLIENT_SECRET'),
        'Content-Type':          'application/json',
    }

def _search_headers():
    return {
        'X-Naver-Client-Id':     get_secret('NAVER_CLIENT_ID'),
        'X-Naver-Client-Secret': get_secret('NAVER_CLIENT_SECRET'),
    }

def _ad_signature(timestamp: str, method: str, path: str) -> str:
    secret_key = get_secret('NAVER_AD_SECRET_KEY')
    message = f'{timestamp}.{method}.{path}'
    signature = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode('utf-8')

def _ad_headers(method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    signature = _ad_signature(timestamp, method, path)
    return {
        'Content-Type': 'application/json',
        'X-Timestamp':  timestamp,
        'X-API-KEY':    get_secret('NAVER_AD_API_KEY'),
        'X-Customer':   get_secret('NAVER_AD_CUSTOMER_ID'),
        'X-Signature':  signature,
    }


# ══════════════════════════════════════
#  키워드 추출
# ══════════════════════════════════════

def extract_keywords(product_name: str) -> tuple:
    """상품명에서 SEO 키워드 4개 + 카테고리 추출"""
    prompt = f"""다음 상품명을 분석하여 아래 두 가지를 추출하세요.

1. 네이버 쇼핑 카테고리 (아래 중 1개만 선택):
   식품, 건강식품, 생활주방, 가전디지털, 패션의류, 스포츠레저, 출산육아, 반려동물, 뷰티, 홈인테리어

2. 40~50대가 실제로 검색할 핵심 키워드 4개 (쉼표로 구분)
   - 브랜드명, 제조사명, 수량, 수식어 제외
   - 상품의 핵심 용도/종류/기능 위주
   - 반드시 한글 2~6글자 단어

출력 형식:
카테고리: [카테고리명]
키워드: [키워드1], [키워드2], [키워드3], [키워드4]

상품명: {product_name}"""
    try:
        result = call_gemini(prompt)
        lines = result.strip().split('\n')
        category = '생활주방'
        keywords = []
        for line in lines:
            line = line.strip()
            if line.startswith('카테고리:'):
                category = line.replace('카테고리:', '').strip().strip('[]')
            elif line.startswith('키워드:'):
                raw = line.replace('키워드:', '').strip()
                keywords = [k.strip().replace('"', '').replace("'", '') for k in raw.split(',')]
                keywords = [k for k in keywords if k][:4]
        while len(keywords) < 4:
            keywords.append(keywords[0] if keywords else product_name[:4])
        category_id = CATEGORY_MAP.get(category, '50000006')
        log.info('카테고리: %s(%s) 키워드: %s', category, category_id, keywords)
        return keywords, category_id
    except Exception as e:
        log.error('키워드 추출 오류: %s', e)
        words = product_name.split()
        kw = words[0] if words else product_name[:4]
        return [kw, kw, kw, kw], '50000006'


# ══════════════════════════════════════
#  네이버 데이터랩
# ══════════════════════════════════════

def _safe_int(value) -> int:
    if isinstance(value, int):
        return value
    s = str(value).strip().replace(',', '')
    nums = re.findall(r'\d+', s)
    return int(nums[0]) if nums else 0


def get_search_trend(keyword: str, start_date: str, end_date: str,
                     ages: list = None) -> float:
    """검색어 트렌드 (40~50대 연령 필터 지원)"""
    url = 'https://openapi.naver.com/v1/datalab/search'
    body = {
        'startDate': start_date,
        'endDate':   end_date,
        'timeUnit':  'month',
        'keywordGroups': [{'groupName': keyword, 'keywords': [keyword]}],
    }
    if ages:
        body['ages'] = ages  # ["6", "7"] → 40대, 50대
    try:
        resp = requests.post(url, headers=_datalab_headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        if data.get('results'):
            results = data['results'][0].get('data', [])
            recent = results[-3:] if len(results) >= 3 else results
            if recent:
                return round(sum(r.get('ratio', 0) for r in recent) / len(recent), 2)
    except Exception as e:
        log.error('검색어트렌드 오류 [%s]: %s', keyword, e)
    return 0.0


def get_shopping_trend(keyword: str, category_id: str,
                       start_date: str, end_date: str) -> float:
    """쇼핑인사이트 트렌드"""
    url = 'https://openapi.naver.com/v1/datalab/shopping/categories'
    body = {
        'startDate': start_date,
        'endDate':   end_date,
        'timeUnit':  'month',
        'category':  [{'name': keyword, 'param': [category_id]}],
    }
    try:
        resp = requests.post(url, headers=_datalab_headers(), json=body)
        resp.raise_for_status()
        data = resp.json()
        if data.get('results'):
            results = data['results'][0].get('data', [])
            recent = results[-3:] if len(results) >= 3 else results
            if recent:
                return round(sum(r.get('ratio', 0) for r in recent) / len(recent), 2)
    except Exception as e:
        log.error('쇼핑인사이트 오류 [%s]: %s', keyword, e)
    return 0.0


def get_real_search_volume(keyword: str) -> dict:
    """네이버 검색광고 API로 월간 실제 검색량 조회"""
    path = '/keywordstool'
    url  = f'https://api.naver.com{path}'
    params = {'hintKeywords': keyword.strip(), 'showDetail': 1}
    try:
        resp = requests.get(url, headers=_ad_headers('GET', path), params=params)
        resp.raise_for_status()
        data = resp.json()
        keywords = data.get('keywordList', [])
        target = next((k for k in keywords if k.get('relKeyword') == keyword.strip()), None)
        if not target and keywords:
            target = keywords[0]
        if target:
            pc = _safe_int(target.get('monthlyPcQcCnt', 0))
            mobile = _safe_int(target.get('monthlyMobileQcCnt', 0))
            return {'total': pc + mobile, 'pc': pc, 'mobile': mobile}
    except Exception as e:
        log.error('검색광고 오류 [%s]: %s', keyword, e)
    return {'total': 0, 'pc': 0, 'mobile': 0}


# ══════════════════════════════════════
#  경쟁 블로그 분석
# ══════════════════════════════════════

def get_competitor_blogs(keyword: str, display: int = 5) -> list:
    """
    네이버 블로그 검색 API로 상위 블로그 수집
    정확도(sim) + 최신순(date) 병행하여 트렌드까지 파악
    """
    url = 'https://openapi.naver.com/v1/search/blog.json'
    blogs = []
    seen_links = set()

    # 정확도순 (상위 노출 패턴 분석용)
    for sort_type in ['sim', 'date']:
        params = {'query': keyword, 'display': display, 'sort': sort_type}
        try:
            resp = requests.get(url, headers=_search_headers(), params=params)
            resp.raise_for_status()
            items = resp.json().get('items', [])
            for item in items:
                link = item.get('link', '')
                if link in seen_links:
                    continue
                seen_links.add(link)
                title = re.sub(r'<[^>]+>', '', item.get('title', '')).strip()
                desc = re.sub(r'<[^>]+>', '', item.get('description', '')).strip()
                blogs.append({
                    'title': title,
                    'description': desc,
                    'link': link,
                    'bloggername': item.get('bloggername', ''),
                    'postdate': item.get('postdate', ''),
                    'sort': sort_type,
                })
        except Exception as e:
            log.error('블로그 검색 오류 [%s, %s]: %s', keyword, sort_type, e)
        time.sleep(0.2)

    log.info('경쟁블로그 %d개 수집: [%s]', len(blogs), keyword)
    return blogs[:10]


def get_related_keywords(keyword: str) -> list:
    """검색광고 API에서 연관 키워드 확장 (월간검색량 포함)"""
    path = '/keywordstool'
    url  = f'https://api.naver.com{path}'
    params = {'hintKeywords': keyword.strip(), 'showDetail': 1}
    try:
        resp = requests.get(url, headers=_ad_headers('GET', path), params=params)
        resp.raise_for_status()
        data = resp.json()
        keywords = data.get('keywordList', [])
        result = []
        for kw in keywords[:15]:
            total = _safe_int(kw.get('monthlyPcQcCnt', 0)) + \
                    _safe_int(kw.get('monthlyMobileQcCnt', 0))
            comp = kw.get('compIdx', '')
            result.append({
                'keyword': kw.get('relKeyword', ''),
                'total_search': total,
                'competition': comp,  # 높음/중간/낮음
            })
        log.info('연관키워드 %d개: [%s]', len(result), keyword)
        return result
    except Exception as e:
        log.error('연관키워드 오류 [%s]: %s', keyword, e)
        return []


# ══════════════════════════════════════
#  통합 SEO 분석
# ══════════════════════════════════════

def analyze(product_name: str) -> dict:
    """
    상품명 입력 → SEO 인텔리전스 통합 결과 반환

    반환:
    {
        'keywords': [...],
        'category_id': '...',
        'search_trends': {kw: score, ...},
        'shopping_trend': float,
        'search_volumes': {kw: {total, pc, mobile}, ...},
        'age_trend': str,
        'competitor_blogs': [...],
    }
    """
    log.info('SEO 분석 시작: %s', product_name)

    keywords, category_id = extract_keywords(product_name)

    end_date = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=180)).strftime('%Y-%m-%d')

    # 키워드별 분석
    search_trends = {}
    search_volumes = {}
    for kw in keywords:
        # 40~50대 필터 트렌드
        search_trends[kw] = get_search_trend(
            kw, start_date, end_date, ages=["6", "7"])
        # 실제 검색량
        search_volumes[kw] = get_real_search_volume(kw)
        time.sleep(0.3)

    # 쇼핑 트렌드 (대표 키워드)
    shopping_trend = get_shopping_trend(
        keywords[0], category_id, start_date, end_date)

    # 가장 검색량 높은 키워드로 경쟁 블로그 분석
    best_kw = max(keywords, key=lambda k: search_volumes.get(k, {}).get('total', 0))
    competitor_blogs = get_competitor_blogs(best_kw)

    # [문제#1 수정] get_real_search_volume과 get_related_keywords가 동일 API 중복 호출
    # → 연관 키워드는 best_kw 한 번만 호출하되, 이미 조회한 키워드 결과 재활용
    related_keywords = get_related_keywords(best_kw)

    # 연관 키워드 중 경쟁 낮고 검색량 있는 롱테일 키워드 추출
    longtail_keywords = [
        rk['keyword'] for rk in related_keywords
        if rk['total_search'] >= 100
        and rk['competition'] in ('낮음', '중간', '')
        and rk['keyword'] not in keywords
    ][:5]

    # 연령대 트렌드 요약
    total_vol = sum(v.get('total', 0) for v in search_volumes.values())
    age_trend = f'40~50대 타겟 | 총 월간 검색량 {total_vol:,}회'

    result = {
        'keywords': keywords,
        'category_id': category_id,
        'search_trends': search_trends,
        'shopping_trend': shopping_trend,
        'search_volumes': search_volumes,
        'age_trend': age_trend,
        'competitor_blogs': competitor_blogs,
        'best_keyword': best_kw,
        'related_keywords': related_keywords,
        'longtail_keywords': longtail_keywords,
    }

    log.info('SEO 분석 완료: 키워드=%s 최적=%s 경쟁블로그=%d개',
             keywords, best_kw, len(competitor_blogs))
    return result
