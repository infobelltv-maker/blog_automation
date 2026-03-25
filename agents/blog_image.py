"""
YouTube 프레임 캡쳐 + 자막 추출 + 이미지 리사이즈
yt-dlp + ffmpeg + PIL
"""
import os
import json
import subprocess
import shutil
from pathlib import Path
from PIL import Image
from utils.logger import get_logger
from config import IMAGES_DIR

log = get_logger('blog_image')

# 네이버 블로그 이미지 최적 크기
# 네이버 블로그 본문 최대 폭 860px, 권장 비율 3:2
BLOG_IMAGE_WIDTH = 860
BLOG_IMAGE_MAX_HEIGHT = 700


def capture_youtube_frames(
    youtube_url: str,
    pcode: str,
    count: int = 5,
    interval: int = 10,
) -> list:
    """
    YouTube 영상에서 프레임 캡쳐

    Args:
        youtube_url: YouTube URL
        pcode: 상품코드
        count: 캡쳐 수
        interval: 캡쳐 간격 (초)

    Returns:
        저장된 이미지 파일 경로 리스트
    """
    save_dir = IMAGES_DIR / pcode
    save_dir.mkdir(parents=True, exist_ok=True)

    log.info('YouTube 캡쳐 시작: %s (%d프레임, %d초 간격)', youtube_url, count, interval)

    # yt-dlp로 영상 다운로드 (최저 화질 - 캡쳐용)
    temp_video = save_dir / f'{pcode}_temp.mp4'
    try:
        cmd = [
            'yt-dlp',
            '-f', 'worst[ext=mp4]',
            '-o', str(temp_video),
            '--no-playlist',
            '--quiet',
            youtube_url,
        ]
        subprocess.run(cmd, check=True, timeout=120)
    except FileNotFoundError:
        log.error('yt-dlp가 설치되지 않았습니다. pip install yt-dlp')
        return []
    except Exception as e:
        log.error('영상 다운로드 실패: %s', e)
        return []

    if not temp_video.exists():
        log.error('다운로드된 영상 파일 없음')
        return []

    # ffmpeg로 프레임 캡쳐
    saved = []
    for i in range(count):
        timestamp = interval * (i + 1)
        output_path = save_dir / f'{pcode}_{i+1:02d}.jpg'
        try:
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(timestamp),
                '-i', str(temp_video),
                '-frames:v', '1',
                '-q:v', '2',
                str(output_path),
            ]
            subprocess.run(cmd, check=True, timeout=30,
                           capture_output=True)
            if output_path.exists() and output_path.stat().st_size > 1024:
                saved.append(str(output_path))
                log.info('캡쳐 저장: %s (%ds)', output_path.name, timestamp)
        except FileNotFoundError:
            log.error('ffmpeg가 설치되지 않았습니다')
            break
        except Exception as e:
            log.error('프레임 캡쳐 실패 [%ds]: %s', timestamp, e)

    # 임시 영상 삭제
    try:
        temp_video.unlink(missing_ok=True)
    except Exception:
        pass

    log.info('YouTube 캡쳐 완료: %d/%d', len(saved), count)
    return saved


# ══════════════════════════════════════
#  상세페이지 스크린샷 캡쳐
# ══════════════════════════════════════

CAPTURE_WIDTH = 1280
CAPTURE_HEIGHT = 720


def capture_product_page(
    url: str,
    pcode: str,
    count: int = 10,
) -> list:
    """
    자사몰 상세페이지를 Playwright로 렌더링하고,
    시각적 콘텐츠가 풍부한 영역을 1280x720 비율로 캡쳐한다.

    1) 전체 페이지를 스크롤하며 720px 간격으로 스크린샷
    2) 각 스크린샷의 "콘텐츠 밀도" 측정 (빈 영역 제외)
    3) 밀도 높은 상위 N개를 선별
    """
    save_dir = IMAGES_DIR / pcode / 'page_captures'
    save_dir.mkdir(parents=True, exist_ok=True)
    log.info('상세페이지 캡쳐 시작: %s', url)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error('playwright 미설치 — pip install playwright && python -m playwright install chromium')
        return []

    candidates = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': CAPTURE_WIDTH, 'height': CAPTURE_HEIGHT})
            page.goto(url, wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(2000)  # JS 렌더링 대기

            # 전체 페이지 높이
            total_height = page.evaluate('document.body.scrollHeight')
            scroll_step = CAPTURE_HEIGHT  # 720px씩 스크롤
            positions = list(range(0, total_height, scroll_step))

            log.info('페이지 높이: %dpx, 캡쳐 위치: %d개', total_height, len(positions))

            for i, y in enumerate(positions):
                page.evaluate(f'window.scrollTo(0, {y})')
                page.wait_for_timeout(300)

                tmp_path = save_dir / f'_tmp_{i:03d}.png'
                page.screenshot(path=str(tmp_path), clip={
                    'x': 0, 'y': 0,
                    'width': CAPTURE_WIDTH,
                    'height': CAPTURE_HEIGHT,
                })

                # 콘텐츠 밀도 측정
                score = _content_density(str(tmp_path))
                candidates.append((str(tmp_path), score, y))

            browser.close()

    except Exception as e:
        log.error('페이지 캡쳐 실패: %s', e)
        return []

    # 밀도 높은 순으로 정렬 → 상위 count개 선별
    candidates.sort(key=lambda x: x[1], reverse=True)
    selected = candidates[:count]
    # 페이지 순서대로 재정렬
    selected.sort(key=lambda x: x[2])

    saved = []
    for i, (tmp_path, score, y) in enumerate(selected):
        # 최종 파일로 JPEG 변환
        final_path = save_dir / f'{pcode}_page_{i+1:02d}.jpg'
        try:
            img = Image.open(tmp_path).convert('RGB')
            img.save(str(final_path), 'JPEG', quality=92)
            saved.append(str(final_path))
            log.info('캡쳐 선별: %s (밀도=%.1f, 위치=%dpx)', final_path.name, score, y)
        except Exception as e:
            log.error('이미지 변환 실패: %s', e)

    # 임시 파일 정리
    for tmp in save_dir.glob('_tmp_*.png'):
        tmp.unlink(missing_ok=True)

    log.info('상세페이지 캡쳐 완료: %d/%d', len(saved), count)
    return saved


def _content_density(image_path: str) -> float:
    """
    이미지의 '콘텐츠 밀도'를 측정한다.
    흰/밝은 배경이 적을수록 = 상품 이미지/텍스트가 많을수록 점수가 높다.
    색상 분산이 클수록 시각적으로 풍부한 영역이다.
    """
    try:
        img = Image.open(image_path).convert('RGB')
        img = img.resize((320, 180))  # 축소하여 빠르게 분석

        pixels = list(img.getdata())
        total = len(pixels)

        # 1) 비흰색 비율 (R,G,B 모두 240 이상이면 흰색으로 간주)
        non_white = sum(1 for r, g, b in pixels if r < 240 or g < 240 or b < 240)
        white_ratio = non_white / total  # 0~1, 높을수록 콘텐츠 많음

        # 2) 색상 분산 (표준편차)
        import statistics
        r_vals = [p[0] for p in pixels]
        g_vals = [p[1] for p in pixels]
        b_vals = [p[2] for p in pixels]
        color_variance = (
            statistics.stdev(r_vals) +
            statistics.stdev(g_vals) +
            statistics.stdev(b_vals)
        ) / 3

        # 종합 점수 (비흰색 비율 70% + 색상 분산 30%)
        score = white_ratio * 70 + (color_variance / 128) * 30
        return score

    except Exception:
        return 0.0


def resize_for_blog(image_path: str, output_path: str = None) -> str:
    """
    블로그용 이미지 리사이즈
    - 가로 860px 맞춤, 세로는 비율 유지 (최대 700px)
    - 흰색 패딩 없이 원본 비율 유지 (네이버 블로그에서 자연스러움)
    """
    if output_path is None:
        p = Path(image_path)
        output_path = str(p.parent / f'{p.stem}_blog{p.suffix}')

    try:
        img = Image.open(image_path)
        img = img.convert('RGB')

        # 원본이 860px보다 작으면 업스케일하지 않음 (화질 보호)
        target_width = min(BLOG_IMAGE_WIDTH, img.width)
        ratio = target_width / img.width
        new_height = int(img.height * ratio)

        # 세로가 너무 길면 크롭
        if new_height > BLOG_IMAGE_MAX_HEIGHT:
            new_height = BLOG_IMAGE_MAX_HEIGHT

        img = img.resize((target_width, new_height), Image.LANCZOS)
        img.save(output_path, 'JPEG', quality=90)
        log.info('리사이즈: %s → %dx%d', Path(image_path).name, BLOG_IMAGE_WIDTH, new_height)
        return output_path
    except Exception as e:
        log.error('리사이즈 실패 [%s]: %s', image_path, e)
        return image_path


def prepare_blog_images(image_paths: list, pcode: str,
                        product_name: str = '') -> list:
    """
    모든 이미지를 블로그용으로 준비
    - 번호 정리 + 리사이즈
    - SEO 친화적 파일명 (키워드 기반)
    """
    output_dir = IMAGES_DIR / pcode / 'blog_ready'
    output_dir.mkdir(parents=True, exist_ok=True)

    # SEO 파일명: 상품명 기반 (네이버 이미지 검색 최적화)
    import re
    safe_name = re.sub(r'[^\w가-힣]', '_', product_name)[:20] if product_name else pcode

    prepared = []
    for i, img_path in enumerate(image_paths):
        output_path = str(output_dir / f'{safe_name}_{i+1:02d}.jpg')
        resized = resize_for_blog(img_path, output_path)
        prepared.append(resized)

    log.info('블로그 이미지 준비 완료: %d개', len(prepared))
    return prepared


# ══════════════════════════════════════
#  YouTube 자막 추출
# ══════════════════════════════════════

def extract_youtube_subtitles(youtube_url: str) -> str:
    """
    YouTube 영상에서 자막(한국어 우선)을 추출한다.
    자동생성 자막도 포함. 자막이 없으면 빈 문자열 반환.

    Returns:
        자막 전체 텍스트 (타임스탬프 제거, 순수 텍스트)
    """
    log.info('YouTube 자막 추출 시작: %s', youtube_url)

    # 임시 디렉토리
    tmp_dir = IMAGES_DIR / '_subtitle_tmp'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_base = str(tmp_dir / 'sub')

    # 기존 임시파일 정리
    for f in tmp_dir.glob('sub*'):
        f.unlink(missing_ok=True)

    try:
        # yt-dlp로 자막 다운로드 (한국어 우선 → 영어 → 자동생성)
        cmd = [
            'yt-dlp',
            '--skip-download',
            '--write-subs',
            '--write-auto-subs',
            '--sub-langs', 'ko,en',
            '--sub-format', 'json3',
            '--no-playlist',
            '--quiet',
            '-o', out_base,
            youtube_url,
        ]
        subprocess.run(cmd, check=True, timeout=60, capture_output=True)
    except FileNotFoundError:
        log.error('yt-dlp 미설치')
        return ''
    except Exception as e:
        log.warning('자막 다운로드 실패: %s', e)
        return ''

    # 다운로드된 자막 파일 찾기 (ko 우선)
    sub_file = None
    for lang in ['ko', 'en']:
        candidates = list(tmp_dir.glob(f'sub*.{lang}*.json3'))
        if candidates:
            sub_file = candidates[0]
            break
    if not sub_file:
        # json3 아닌 다른 형식 시도
        candidates = list(tmp_dir.glob('sub*.vtt')) + list(tmp_dir.glob('sub*.srt'))
        if candidates:
            sub_file = candidates[0]

    if not sub_file:
        log.info('자막 파일 없음')
        return ''

    # 자막 파싱
    text = _parse_subtitle_file(sub_file)

    # 임시파일 정리
    for f in tmp_dir.glob('sub*'):
        f.unlink(missing_ok=True)

    log.info('자막 추출 완료: %d자', len(text))
    return text


def _parse_subtitle_file(filepath: Path) -> str:
    """자막 파일을 순수 텍스트로 변환 (타임스탬프/중복 제거)"""
    ext = filepath.suffix.lower()
    content = filepath.read_text(encoding='utf-8', errors='replace')

    if ext == '.json3':
        return _parse_json3(content)
    else:
        return _parse_vtt_srt(content)


def _parse_json3(content: str) -> str:
    """json3 자막 포맷 파싱"""
    try:
        data = json.loads(content)
        events = data.get('events', [])
        lines = []
        seen = set()
        for event in events:
            segs = event.get('segs', [])
            text = ''.join(s.get('utf8', '') for s in segs).strip()
            text = text.replace('\n', ' ').strip()
            if text and text not in seen:
                seen.add(text)
                lines.append(text)
        return ' '.join(lines)
    except Exception:
        return ''


def _parse_vtt_srt(content: str) -> str:
    """VTT/SRT 자막 포맷 파싱"""
    import re
    # 타임스탬프 라인 제거
    lines = content.split('\n')
    text_lines = []
    seen = set()
    for line in lines:
        line = line.strip()
        # 숫자만, 빈줄, 타임스탬프 스킵
        if not line or line.isdigit():
            continue
        if re.match(r'^\d{2}:\d{2}', line) or '-->' in line:
            continue
        if line.startswith('WEBVTT') or line.startswith('NOTE'):
            continue
        # HTML 태그 제거
        clean = re.sub(r'<[^>]+>', '', line).strip()
        if clean and clean not in seen:
            seen.add(clean)
            text_lines.append(clean)
    return ' '.join(text_lines)
