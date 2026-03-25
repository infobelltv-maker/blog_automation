"""블로그 자동화 설정"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── 환경 감지 ──
# Streamlit Cloud: 환경변수 없이 st.secrets 사용, Windows 기능 불가
IS_CLOUD = not (sys.platform == 'win32' and os.path.exists('.env'))

def get_secret(key: str, default: str = '') -> str:
    """로컬(.env) / 클라우드(st.secrets) 자동 분기"""
    val = os.getenv(key, '')
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default

# ── 경로 ──
BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / 'images' / 'blog'
OUTPUT_DIR = BASE_DIR / 'output' / 'posting_kits'
TEMPLATES_DIR = BASE_DIR / 'templates'

IMAGES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── API 키 ──
GEMINI_API_KEY = get_secret('GEMINI_API_KEY')
NAVER_CLIENT_ID = get_secret('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = get_secret('NAVER_CLIENT_SECRET')

# ── 블로그 글 구조 타입 ──
STRUCTURE_TYPES = ['A', 'B', 'C', 'D', 'E']
STRUCTURE_LABELS = {
    'A': '리뷰형 — "직접 써보고 알려드립니다"',
    'B': '비교형 — "이런 제품들과 비교해봤습니다"',
    'C': 'Q&A형 — "이런 고민이셨죠?"',
    'D': '스토리형 — "어머니가 이걸 써보신 후"',
    'E': '전문가형 — "전문가가 추천하는"',
}

# ── 40~50대 타겟 설정 ──
TARGET_AGE_GROUP = '40~50대'
