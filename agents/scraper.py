"""
상품 정보 스크래핑
- Cafe24 상품 페이지
- 네이버 스마트스토어 (상품 정보 + 리뷰 수집)
URL 자동 판별
"""
import re
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from utils.logger import get_logger

log = get_logger('scraper')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def _is_smartstore(url: str) -> bool:
    return 'smartstore.naver.com' in url or 'brand.naver.com' in url


# ══════════════════════════════════════
#  통합 진입점
# ══════════════════════════════════════

def scrape_product(url: str) -> dict:
    """
    URL 자동 판별 → 스마트스토어 or Cafe24 스크래핑
    반환: {pcode, name, price, description, images, purchase_url, reviews}
    """
    if _is_smartstore(url):
        return _scrape_smartstore(url)
    return _scrape_cafe24(url)


# ══════════════════════════════════════
#  네이버 스마트스토어
# ══════════════════════════════════════

def _extract_smartstore_ids(url: str) -> tuple:
    """스마트스토어 URL에서 채널명과 상품번호 추출"""
    # https://smartstore.naver.com/{channel}/products/{productNo}
    m = re.search(r'smartstore\.naver\.com/([^/]+)/products/(\d+)', url)
    if m:
        return m.group(1), m.group(2)
    # brand.naver.com 패턴
    m = re.search(r'brand\.naver\.com/([^/]+)/products/(\d+)', url)
    if m:
        return m.group(1), m.group(2)
    return '', ''


def _scrape_smartstore(url: str) -> dict:
    """스마트스토어 상품 정보 + 리뷰 수집"""
    log.info('스마트스토어 스크래핑: %s', url)

    result = {
        'pcode': '', 'name': '', 'price': '', 'description': '',
        'images': [], 'purchase_url': url, 'reviews': [],
    }

    channel, product_no = _extract_smartstore_ids(url)
    if not product_no:
        log.warning('스마트스토어 상품번호 추출 실패, HTML 파싱 시도')
        return _scrape_smartstore_html(url)

    result['pcode'] = product_no

    # ── 상품 정보 (내부 API) ──
    try:
        api_url = f'https://smartstore.naver.com/i/v1/stores/{channel}/products/{product_no}'
        resp = requests.get(api_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result['name'] = data.get('name', '')
            result['price'] = str(data.get('salePrice', data.get('price', '')))
            result['description'] = data.get('detailAttribute', {}).get(
                'productInfoProvidedNotice', {}).get('productInfoText', '')

            # 이미지
            images = []
            for img in data.get('productImages', []):
                img_url = img.get('url', '')
                if img_url:
                    images.append(img_url)
            result['images'] = images[:10]

            log.info('스마트스토어 API 성공: %s', result['name'])
    except Exception as e:
        log.warning('스마트스토어 API 실패: %s — HTML 파싱 시도', e)

    # API 실패 시 HTML 폴백
    if not result['name']:
        html_result = _scrape_smartstore_html(url)
        result.update({k: v for k, v in html_result.items() if v})

    # ── 리뷰 수집 ──
    result['reviews'] = fetch_smartstore_reviews(channel, product_no)

    return result


def _scrape_smartstore_html(url: str) -> dict:
    """스마트스토어 HTML 파싱 (API 실패 시 폴백)"""
    result = {
        'pcode': '', 'name': '', 'price': '', 'description': '',
        'images': [], 'purchase_url': url, 'reviews': [],
    }
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # og 태그
        og_title = soup.find('meta', property='og:title')
        if og_title:
            result['name'] = og_title.get('content', '').strip()
        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            result['description'] = og_desc.get('content', '').strip()
        og_img = soup.find('meta', property='og:image')
        if og_img:
            result['images'] = [og_img.get('content', '')]

        # 가격 — JSON 데이터에서 추출
        for script in soup.find_all('script'):
            text = script.string or ''
            m = re.search(r'"salePrice"\s*:\s*(\d+)', text)
            if m:
                result['price'] = m.group(1)
                break

        # 상품코드
        _, product_no = _extract_smartstore_ids(url)
        result['pcode'] = product_no or 'P' + hashlib.md5(
            result['name'].encode('utf-8')).hexdigest()[:8].upper()

    except Exception as e:
        log.error('스마트스토어 HTML 파싱 실패: %s', e)
    return result


def fetch_smartstore_reviews(channel: str, product_no: str,
                              max_pages: int = 3) -> list:
    """
    스마트스토어 리뷰 수집 (최대 60개)
    반환: [{'rating': 5, 'text': '...', 'date': '...'}, ...]
    """
    if not channel or not product_no:
        return []

    reviews = []
    log.info('리뷰 수집 시작: %s/%s', channel, product_no)

    for page in range(1, max_pages + 1):
        try:
            api_url = (
                f'https://smartstore.naver.com/i/v1/stores/{channel}'
                f'/products/{product_no}/reviews'
                f'?page={page}&pageSize=20&sortType=REVIEW_RANKING'
            )
            resp = requests.get(api_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                break

            data = resp.json()
            items = data.get('contents', data.get('reviews', []))
            if not items:
                break

            for item in items:
                review = {
                    'rating': item.get('reviewScore', item.get('rating', 0)),
                    'text': item.get('reviewContent', item.get('content', '')).strip(),
                    'date': item.get('createDate', item.get('createdDate', ''))[:10],
                }
                if review['text']:
                    reviews.append(review)

        except Exception as e:
            log.warning('리뷰 페이지%d 실패: %s', page, e)
            break

    log.info('리뷰 수집 완료: %d개', len(reviews))
    return reviews


def summarize_reviews(reviews: list) -> str:
    """리뷰 목록을 블로그 글 생성용 참고 텍스트로 요약"""
    if not reviews:
        return ''

    total = len(reviews)
    avg_rating = sum(r.get('rating', 0) for r in reviews) / total if total else 0

    # 긍정/부정 키워드 빈도를 위해 텍스트 샘플 수집
    positive = []
    negative = []
    for r in reviews:
        rating = r.get('rating', 0)
        text = r.get('text', '')[:150]  # 리뷰당 150자 제한
        if rating >= 4:
            positive.append(text)
        elif rating <= 2:
            negative.append(text)

    lines = [
        f'총 리뷰 {total}개 | 평균 평점 {avg_rating:.1f}/5',
        '',
        f'[긍정 리뷰 ({len(positive)}개) — 상위 발췌]',
    ]
    for p in positive[:5]:
        lines.append(f'  - "{p}"')

    if negative:
        lines.append(f'\n[부정 리뷰 ({len(negative)}개) — 상위 발췌]')
        for n in negative[:3]:
            lines.append(f'  - "{n}"')

    return '\n'.join(lines)


# ══════════════════════════════════════
#  Cafe24
# ══════════════════════════════════════

def _scrape_cafe24(url: str) -> dict:
    """Cafe24 상품 URL에서 상품 정보를 추출한다."""
    log.info('Cafe24 스크래핑: %s', url)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')

        result = {
            'pcode': '', 'name': '', 'price': '', 'description': '',
            'images': [], 'purchase_url': url, 'reviews': [],
        }

        # ── 상품명 추출 (JSON-LD 우선) ──
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                ld = json.loads(script.string)
                if isinstance(ld, dict) and ld.get('@type') == 'Product':
                    result['name'] = ld.get('name', '')
                    offers = ld.get('offers', {})
                    if isinstance(offers, dict):
                        result['price'] = str(offers.get('price', ''))
                    break
            except Exception:
                pass

        # Fallback: meta / og:title
        if not result['name']:
            og = soup.find('meta', property='og:title')
            if og:
                result['name'] = og.get('content', '').strip()
        if not result['name']:
            title_tag = soup.find('title')
            if title_tag:
                result['name'] = title_tag.get_text(strip=True).split('|')[0].strip()

        # ── 가격 ──
        if not result['price']:
            for sel in ['.prd_price', '#span_product_price_text',
                        '.price strong', '.sale_price']:
                el = soup.select_one(sel)
                if el:
                    nums = re.findall(r'[\d,]+', el.get_text())
                    if nums:
                        result['price'] = nums[0].replace(',', '')
                        break

        # ── 상품코드 ──
        m = re.search(r'/product/(?:[^/]+/)?(\d+)', url)
        if m:
            result['pcode'] = m.group(1)
        else:
            m = re.search(r'product_no=(\d+)', url)
            if m:
                result['pcode'] = m.group(1)
            else:
                result['pcode'] = 'P' + hashlib.md5(
                    result['name'].encode('utf-8')).hexdigest()[:8].upper()

        # ── 설명 ──
        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            result['description'] = og_desc.get('content', '').strip()
        if not result['description']:
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            if desc_tag:
                result['description'] = desc_tag.get('content', '').strip()

        # ── 이미지 ──
        images = []
        for og_img in soup.find_all('meta', property='og:image'):
            img_url = og_img.get('content', '')
            if img_url and img_url not in images:
                images.append(img_url)
        for img in soup.select('.prd_detail img, .cont img, #prd_detail img'):
            src = img.get('src') or img.get('data-src', '')
            if src and not src.endswith(('.gif', '.svg')) and src not in images:
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    src = f'{parsed.scheme}://{parsed.netloc}{src}'
                images.append(src)
        result['images'] = images[:10]

        log.info('Cafe24 스크래핑 완료: %s (이미지 %d개)', result['name'], len(result['images']))
        return result

    except Exception as e:
        log.error('Cafe24 스크래핑 실패: %s', e)
        return {
            'pcode': '', 'name': '', 'price': '', 'description': '',
            'images': [], 'purchase_url': url, 'reviews': [],
        }


# ══════════════════════════════════════
#  이미지 다운로드
# ══════════════════════════════════════

def download_images(images: list, save_dir: str, pcode: str) -> list:
    """이미지 URL 리스트를 다운로드하여 저장."""
    from pathlib import Path
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, img_url in enumerate(images):
        try:
            resp = requests.get(img_url, headers=HEADERS, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 1024:
                fname = f'{pcode}_{i+1:02d}.jpg'
                fpath = save_path / fname
                fpath.write_bytes(resp.content)
                saved.append(str(fpath))
                log.info('이미지 저장: %s', fname)
        except Exception as e:
            log.error('이미지 다운로드 실패 [%d]: %s', i, e)
    return saved
