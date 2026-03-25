"""
발행 로그 + 성과 추적
Google Sheets 또는 로컬 SQLite에 발행 이력 기록
"""
from datetime import datetime
from utils.logger import get_logger
from utils.sheets_io import get_sheet, get_data_rows, upsert_row

log = get_logger('sheets_logger')

# 시트 인덱스
SHEET_PRODUCTS = 0
SHEET_PUBLISH_LOG = 1
SHEET_SEO_DATA = 2

PRODUCTS_HEADER = [
    '상품코드', '상품명', '가격', '상품URL', '상품설명',
]

PUBLISH_LOG_HEADER = [
    '발행일', '상품코드', '상품명', '사용키워드', '글구조타입',
    '제목', '글길이', '태그수', '이미지수', '상태',
    'URL', '조회수', '검색순위', '메모',
]

SEO_DATA_HEADER = [
    '상품코드', '상품명', '키워드', '검색트렌드', '쇼핑트렌드',
    '월간검색수', 'PC검색수', '모바일검색수',
    '경쟁블로그1', '경쟁블로그2', '경쟁블로그3',
    '조회일',
]


def init_sheets():
    """시트 헤더 초기화"""
    sheets_config = [
        (SHEET_PRODUCTS, '📦 상품 목록 | 블로그 자동화', PRODUCTS_HEADER),
        (SHEET_PUBLISH_LOG, '📝 발행 로그 | 성과 추적', PUBLISH_LOG_HEADER),
        (SHEET_SEO_DATA, '📊 SEO 데이터 | 트렌드 분석', SEO_DATA_HEADER),
    ]
    for idx, guide_text, header in sheets_config:
        ws = get_sheet(idx)
        try:
            all_vals = ws.get_all_values()
            if len(all_vals) < 2 or not all_vals[1]:
                ws.update([[guide_text]], 'A1')
                ws.update([header], 'A2')
                log.info('시트%d 헤더 초기화 완료', idx)
        except Exception as e:
            log.error('시트%d 초기화 오류: %s', idx, e)


def save_product(product: dict):
    """상품 정보를 시트1에 저장"""
    ws = get_sheet(SHEET_PRODUCTS)
    row = [
        product.get('pcode', ''),
        product.get('name', ''),
        product.get('price', ''),
        product.get('purchase_url', ''),
        product.get('description', '')[:200],
    ]
    upsert_row(ws, 0, product.get('pcode', ''), row)
    log.info('상품 저장: %s', product.get('name'))


def log_publish(
    pcode: str,
    product_name: str,
    keywords: list,
    structure_type: str,
    title: str,
    body_length: int,
    tag_count: int,
    image_count: int,
):
    """발행 로그 기록"""
    ws = get_sheet(SHEET_PUBLISH_LOG)
    row = [
        datetime.now().strftime('%Y-%m-%d %H:%M'),
        pcode,
        product_name,
        ', '.join(keywords) if keywords else '',
        structure_type,
        title,
        str(body_length),
        str(tag_count),
        str(image_count),
        '생성완료',
        '', '', '', '',  # URL, 조회수, 검색순위, 메모 (나중에 수동 입력)
    ]
    ws.append_row(row)
    log.info('발행 로그 기록: %s [%s]', pcode, structure_type)


def save_seo_data(pcode: str, product_name: str, seo_result: dict):
    """SEO 분석 결과를 시트3에 저장"""
    ws = get_sheet(SHEET_SEO_DATA)
    today = datetime.now().strftime('%Y-%m-%d')

    for kw in seo_result.get('keywords', []):
        trend = seo_result.get('search_trends', {}).get(kw, 0)
        vol = seo_result.get('search_volumes', {}).get(kw, {})
        blogs = seo_result.get('competitor_blogs', [])

        row = [
            pcode, product_name, kw,
            str(trend),
            str(seo_result.get('shopping_trend', 0)),
            str(vol.get('total', 0)),
            str(vol.get('pc', 0)),
            str(vol.get('mobile', 0)),
            blogs[0]['title'] if len(blogs) > 0 else '',
            blogs[1]['title'] if len(blogs) > 1 else '',
            blogs[2]['title'] if len(blogs) > 2 else '',
            today,
        ]
        ws.append_row(row)

    log.info('SEO 데이터 저장: %s (%d키워드)', pcode, len(seo_result.get('keywords', [])))


def get_used_structures() -> list:
    """최근 발행에 사용된 글 구조 타입 이력 조회"""
    ws = get_sheet(SHEET_PUBLISH_LOG)
    _, _, data, _ = get_data_rows(ws)
    types = []
    for row in data:
        if len(row) > 4 and row[4].strip():
            types.append(row[4].strip())
    return types
