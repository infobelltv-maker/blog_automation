"""
포스팅 키트 생성 + 클립보드 복사
- HTML + 이미지 폴더 + 가이드를 하나의 키트로 패키징
- 리치텍스트 HTML 클립보드 복사 (pywin32)
- 이미지 폴더 탐색기 자동 오픈
"""
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from utils.logger import get_logger
from config import OUTPUT_DIR

log = get_logger('publisher')


def create_posting_kit(
    pcode: str,
    title: str,
    body_html: str,
    tags: list,
    image_paths: list,
    image_guide: str = '',
) -> dict:
    """
    포스팅 키트 생성

    Returns:
        {
            'kit_dir': 키트 폴더 경로,
            'html_path': HTML 파일 경로,
            'images_dir': 이미지 폴더 경로,
            'guide_path': 가이드 파일 경로,
            'tags_path': 태그 파일 경로,
        }
    """
    date_str = datetime.now().strftime('%Y%m%d')
    kit_name = f'{pcode}_{date_str}'
    kit_dir = OUTPUT_DIR / kit_name
    kit_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. HTML 파일 ──
    html_path = kit_dir / 'blog_post.html'
    # 네이버 에디터 호환 HTML (div/span/class 사용 금지, 인라인 스타일만)
    tags_html = ' '.join([f'<b style="color:#888; font-size:13px;">#{t}</b>' for t in tags])
    full_html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><title>{title}</title></head>
<body style="font-family:'Noto Sans KR',sans-serif; max-width:860px; margin:0 auto; padding:20px; line-height:1.8; color:#333;">
<h2 style="color:#1a1a1a; border-bottom:2px solid #2db400; padding-bottom:8px;">{title}</h2>
{body_html}
<p style="margin-top:30px; padding-top:20px; border-top:1px solid #eee;">
{tags_html}
</p>
</body>
</html>"""
    html_path.write_text(full_html, encoding='utf-8')
    log.info('HTML 저장: %s', html_path)

    # ── 2. 이미지 폴더 ──
    images_dir = kit_dir / 'images'
    images_dir.mkdir(exist_ok=True)
    for i, img_path in enumerate(image_paths):
        if os.path.exists(img_path):
            dest = images_dir / f'{i+1:02d}.jpg'
            shutil.copy2(img_path, dest)
    log.info('이미지 복사: %d개 → %s', len(image_paths), images_dir)

    # ── 3. 이미지 배치 가이드 ──
    guide_path = kit_dir / 'guide.txt'
    guide_content = f"""[포스팅 가이드 — {title}]
생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}
구조: {pcode}

{image_guide if image_guide else '이미지를 본문의 <!--IMAGE_N--> 위치에 순서대로 삽입하세요.'}

[발행 방법]
1. 클립보드 복사 버튼 클릭 → 네이버 블로그 에디터에서 Ctrl+V
2. images 폴더에서 이미지를 순서대로 드래그&드롭
3. 태그 복사 후 블로그 태그란에 붙여넣기
4. 발행!
"""
    guide_path.write_text(guide_content, encoding='utf-8')

    # ── 4. 태그 파일 ──
    tags_path = kit_dir / 'tags.txt'
    tags_path.write_text(', '.join(tags), encoding='utf-8')

    log.info('포스팅 키트 생성 완료: %s', kit_dir)

    return {
        'kit_dir': str(kit_dir),
        'html_path': str(html_path),
        'images_dir': str(images_dir),
        'guide_path': str(guide_path),
        'tags_path': str(tags_path),
    }


def _html_to_plain(html: str) -> str:
    """HTML → 줄바꿈/띄어쓰기 유지된 텍스트 변환"""
    import re
    text = html
    # 블록 태그 → 줄바꿈 2개 (문단 간격)
    text = re.sub(r'</(?:p|h[1-6]|li|tr|div)>', '\n\n', text)
    # <br> → 줄바꿈 1개
    text = re.sub(r'<br\s*/?>', '\n', text)
    # 나머지 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    # 연속 줄바꿈 정리 (3개 이상 → 2개)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # HTML 엔티티
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ').replace('&quot;', '"')
    return text.strip()


def copy_html_to_clipboard(html_content: str) -> bool:
    """리치텍스트 HTML을 클립보드에 복사 (Windows pywin32)"""
    try:
        import win32clipboard
        import win32con

        # CF_HTML 포맷 생성
        html_header = (
            "Version:0.9\r\n"
            "StartHTML:{:08d}\r\n"
            "EndHTML:{:08d}\r\n"
            "StartFragment:{:08d}\r\n"
            "EndFragment:{:08d}\r\n"
        )
        prefix = "<!--StartFragment-->"
        suffix = "<!--EndFragment-->"

        # 더미 헤더로 오프셋 계산
        dummy = html_header.format(0, 0, 0, 0)
        start_html = len(dummy.encode('utf-8'))
        start_fragment = start_html + len(prefix.encode('utf-8'))
        end_fragment = start_fragment + len(html_content.encode('utf-8'))
        end_html = end_fragment + len(suffix.encode('utf-8'))

        cf_html = html_header.format(start_html, end_html, start_fragment, end_fragment)
        full_html = cf_html + prefix + html_content + suffix

        # 클립보드에 등록
        CF_HTML = win32clipboard.RegisterClipboardFormat("HTML Format")
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(CF_HTML, full_html.encode('utf-8'))
        # 텍스트도 동시 등록 (줄바꿈/띄어쓰기 유지)
        plain_text = _html_to_plain(html_content)
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, plain_text)
        win32clipboard.CloseClipboard()

        log.info('클립보드 복사 완료 (HTML + 텍스트)')
        return True
    except ImportError:
        log.warning('pywin32 미설치 — 텍스트 모드로 폴백')
        try:
            plain = _html_to_plain(html_content)
            subprocess.run(['clip'], input=plain.encode('utf-8'), check=True)
            log.info('클립보드 복사 완료 (텍스트)')
            return True
        except Exception as e:
            log.error('클립보드 복사 실패: %s', e)
            return False
    except Exception as e:
        log.error('클립보드 복사 실패: %s', e)
        return False


def open_folder(folder_path: str) -> bool:
    """Windows 탐색기로 폴더 열기"""
    try:
        os.startfile(folder_path)
        log.info('탐색기 오픈: %s', folder_path)
        return True
    except Exception as e:
        log.error('폴더 열기 실패: %s', e)
        return False
