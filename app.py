"""
INFOBELL 네이버 블로그 포스팅 자동화 v3
AI-Powered Blog Content Factory
Streamlit 메인 앱
"""
import os
import sys
import re
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    STRUCTURE_TYPES, STRUCTURE_LABELS, IMAGES_DIR, OUTPUT_DIR, IS_CLOUD,
)
from agents import scraper, seo_engine, blog_content, blog_image, blog_publisher
from agents.blog_content import PERSONAS
from agents.sheets_logger import (
    init_sheets, save_product, log_publish, save_seo_data, get_used_structures,
)
from utils.doc_parser import extract_text

# ══════════════════════════════════════
#  페이지 설정
# ══════════════════════════════════════

st.set_page_config(
    page_title='블로그 자동화 v3',
    page_icon='📝',
    layout='wide',
    initial_sidebar_state='expanded',
)


def _html(html_str):
    """!important 자동 삽입 + unsafe HTML 렌더링"""
    result = re.sub(r'color:([^;"]+)', r'color:\1 !important', html_str)
    st.markdown(result, unsafe_allow_html=True)


# ══════════════════════════════════════
#  CSS
# ══════════════════════════════════════

st.markdown("""<style>
.stApp { background: #fafbfc; }
.metric-card { background: #f8f9fa; border-radius: 12px; padding: 16px; text-align: center; border: 1px solid #e9ecef; }
.metric-value { font-size: 24px; font-weight: bold; color: #1a1a1a; }
.metric-label { font-size: 12px; color: #888; margin-top: 4px; }
.seo-card { background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 16px; padding: 20px; color: white; margin-bottom: 16px; }
.seo-card h3 { color: white !important; margin: 0 0 8px 0; font-size: 16px; }
.seo-card .value { font-size: 28px; font-weight: bold; }
.kw-tag { display: inline-block; background: rgba(255,255,255,0.2); padding: 4px 12px; border-radius: 16px; margin: 3px; font-size: 13px; }
.blog-tag { display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 4px 12px; border-radius: 16px; margin: 3px; font-size: 13px; }
.structure-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 14px; }
.st-badge-A { background: #e3f2fd; color: #1565c0; }
.st-badge-B { background: #fff3e0; color: #e65100; }
.st-badge-C { background: #e8f5e9; color: #2e7d32; }
.st-badge-D { background: #fce4ec; color: #c62828; }
.st-badge-E { background: #f3e5f5; color: #6a1b9a; }
</style>""", unsafe_allow_html=True)


# ══════════════════════════════════════
#  세션 초기화
# ══════════════════════════════════════

if 'product' not in st.session_state:
    st.session_state.product = None
if 'seo_data' not in st.session_state:
    st.session_state.seo_data = None
if 'blog_result' not in st.session_state:
    st.session_state.blog_result = None
if 'images' not in st.session_state:
    st.session_state.images = []
if 'kit' not in st.session_state:
    st.session_state.kit = None
if 'selected_title_idx' not in st.session_state:
    st.session_state.selected_title_idx = 0
if 'spec_text' not in st.session_state:
    st.session_state.spec_text = ''
if 'youtube_subtitle' not in st.session_state:
    st.session_state.youtube_subtitle = ''
if 'persona_results' not in st.session_state:
    st.session_state.persona_results = {}  # {persona_key: result_dict}

# 시트 초기화
init_sheets()


# ══════════════════════════════════════
#  사이드바
# ══════════════════════════════════════

with st.sidebar:
    _html("""<div style="text-align:center; padding:16px 0;">
        <div style="font-size:28px; font-weight:bold; color:#2db400;">INFOBELL</div>
        <div style="font-size:14px; color:#888; margin-top:4px;">블로그 자동화 v3</div>
    </div>""")

    # ── 상품 검색 (찾기용) ──
    from urllib.parse import quote
    search_query = st.text_input('상품명 검색', placeholder='상품명 입력 → 각 채널에서 상품 찾기')

    if search_query:
        q = quote(search_query)
        st.caption('아래 버튼으로 상품을 찾은 뒤, 상품 페이지 URL을 복사해서 아래에 붙여넣으세요.')
        qc1, qc2, qc3 = st.columns(3)
        with qc1:
            st.link_button('자사몰에서 찾기', f'https://www.infobellmall.co.kr/product/search.html?keyword={q}', use_container_width=True)
        with qc2:
            st.link_button('스토어에서 찾기', f'https://smartstore.naver.com/infobell/search?q={q}', use_container_width=True)
        with qc3:
            st.link_button('유튜브에서 찾기', f'https://www.youtube.com/@infobellmall/search?query={q}', use_container_width=True)
    else:
        qc1, qc2, qc3 = st.columns(3)
        with qc1:
            st.link_button('자사몰', 'https://www.infobellmall.co.kr/product/list.html?cate_no=34', use_container_width=True)
        with qc2:
            st.link_button('스마트스토어', 'https://smartstore.naver.com/infobell/category/1cd59d8b9e504be5aae446cbb048b37d?cp=2', use_container_width=True)
        with qc3:
            st.link_button('유튜브', 'https://www.youtube.com/@infobellmall/videos', use_container_width=True)

    st.divider()

    # ── 상품 URL 입력 (실제 상품 페이지 붙여넣기) ──
    product_url = st.text_input(
        '상품 URL (자사몰)',
        placeholder='위에서 찾은 상품 페이지 URL을 붙여넣으세요',
    )

    smartstore_url = st.text_input(
        '스마트스토어 URL (리뷰 수집)',
        placeholder='스마트스토어 상품 페이지 URL을 붙여넣으세요',
    )

    youtube_url = st.text_input(
        'YouTube URL (선택)',
        placeholder='유튜브 영상 URL을 붙여넣으세요',
    )

    # ── 기술서 업로드 ──
    spec_file = st.file_uploader(
        '상품 기술서 (선택)',
        type=['docx', 'pdf', 'txt', 'xlsx', 'xls', 'csv'],
        help='상품 상세 스펙, 기능 설명, 성분표 등을 업로드하면 글에 반영됩니다.',
    )
    if spec_file is not None:
        if spec_file.name != st.session_state.get('_spec_filename', ''):
            with st.spinner('기술서 분석 중...'):
                text = extract_text(spec_file.getvalue(), spec_file.name)
                st.session_state.spec_text = text
                st.session_state._spec_filename = spec_file.name
        if st.session_state.spec_text:
            char_count = len(st.session_state.spec_text)
            st.caption(f'기술서 로드 완료 ({char_count:,}자)')
    else:
        st.session_state.spec_text = ''
        st.session_state._spec_filename = ''

    # ── 캡쳐 설정 ──
    with st.expander('캡쳐 설정', expanded=False):
        capture_source = st.radio(
            '이미지 소스',
            ['상세페이지 캡쳐', 'YouTube 캡쳐', '상품 이미지 다운로드'],
            index=0,
            horizontal=True,
        )
        capture_count = st.slider('캡쳐 수', 3, 10, 10)
        if capture_source == 'YouTube 캡쳐':
            capture_interval = st.slider('캡쳐 간격(초)', 5, 30, 10)
        else:
            capture_interval = 10

    st.divider()

    # ── 실행 버튼 ──
    col1, col2, col3 = st.columns(3)
    with col1:
        btn_analyze = st.button('분석 시작', type='primary', use_container_width=True)
    with col2:
        btn_generate = st.button('글 생성', type='secondary', use_container_width=True)
    with col3:
        btn_capture = st.button('이미지 캡쳐', use_container_width=True)

    st.divider()

    # ── 상품 정보 표시 ──
    if st.session_state.product:
        p = st.session_state.product
        info_lines = [
            f'<strong>{p.get("name", "")}</strong>',
            f'코드: {p.get("pcode", "")} | 가격: {p.get("price", "")}원',
            f'이미지: {len(p.get("images", []))}개',
        ]
        if p.get('reviews'):
            info_lines.append(f'리뷰: {len(p["reviews"])}개 수집됨')
        if st.session_state.youtube_subtitle:
            info_lines.append(f'YouTube 자막: {len(st.session_state.youtube_subtitle):,}자')
        st.markdown(
            f'<p style="background:#f0f7ff; border-radius:10px; padding:12px; font-size:13px; line-height:1.8;">{"<br>".join(info_lines)}</p>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════
#  메인 로직: 분석 시작
# ══════════════════════════════════════

if btn_analyze and product_url:
    # 새 분석 시 이전 상품 데이터 초기화
    st.session_state.seo_data = None
    st.session_state.blog_result = None
    st.session_state.images = []
    st.session_state.kit = None
    st.session_state.selected_title_idx = 0
    st.session_state.youtube_subtitle = ''
    st.session_state.persona_results = {}

    with st.spinner('상품 정보 수집 중...'):
        product = scraper.scrape_product(product_url)
        product['purchase_url'] = product_url  # 자사몰 URL이 곧 구매링크
        st.session_state.product = product
        save_product(product)

        # 스마트스토어 URL이 있으면 리뷰 수집
        if smartstore_url and 'smartstore.naver.com' in smartstore_url:
            from agents.scraper import _extract_smartstore_ids, fetch_smartstore_reviews
            channel, product_no = _extract_smartstore_ids(smartstore_url)
            if channel and product_no:
                reviews = fetch_smartstore_reviews(channel, product_no)
                product['reviews'] = reviews
                st.session_state.product = product

    if product.get('name'):
        progress = st.progress(0, text='SEO 분석 준비 중...')

        progress.progress(20, text='네이버 데이터랩 + 경쟁 블로그 분석 중...')
        seo_data = seo_engine.analyze(product['name'])
        st.session_state.seo_data = seo_data
        save_seo_data(product['pcode'], product['name'], seo_data)

        # YouTube 자막은 URL 있으면 분석 시 추출
        if youtube_url:
            progress.progress(60, text='YouTube 자막 추출 중...')
            subtitle = blog_image.extract_youtube_subtitles(youtube_url)
            st.session_state.youtube_subtitle = subtitle
        else:
            st.session_state.youtube_subtitle = ''

        progress.progress(100, text='분석 완료!')
        st.rerun()
    else:
        st.error('상품 정보를 가져올 수 없습니다. URL을 확인해주세요.')


# ══════════════════════════════════════
#  메인 로직: 이미지 캡쳐
# ══════════════════════════════════════

if btn_capture:
    if not st.session_state.product:
        st.warning('먼저 "분석 시작"을 실행해주세요.')
    else:
        product = st.session_state.product
        with st.spinner(f'이미지 캡쳐 중... ({capture_source})'):
            if capture_source == '상세페이지 캡쳐':
                if IS_CLOUD:
                    st.warning('상세페이지 캡쳐는 로컬에서만 가능합니다. 상품 이미지 다운로드로 대체합니다.')
                    if product.get('images'):
                        img_dir = str(IMAGES_DIR / product['pcode'])
                        images = scraper.download_images(product['images'], img_dir, product['pcode'])
                        st.session_state.images = images
                else:
                    images = blog_image.capture_product_page(
                        product_url, product['pcode'], count=capture_count)
                    st.session_state.images = images

            elif capture_source == 'YouTube 캡쳐' and youtube_url:
                images = blog_image.capture_youtube_frames(
                    youtube_url, product['pcode'],
                    count=capture_count, interval=capture_interval,
                )
                st.session_state.images = images

            elif capture_source == '상품 이미지 다운로드' and product.get('images'):
                img_dir = str(IMAGES_DIR / product['pcode'])
                images = scraper.download_images(product['images'], img_dir, product['pcode'])
                st.session_state.images = images
            else:
                st.warning('캡쳐할 소스가 없습니다. URL을 확인해주세요.')

        st.rerun()


# ══════════════════════════════════════
#  메인 로직: 글 생성
# ══════════════════════════════════════

if btn_generate:
    if not st.session_state.product:
        st.warning('먼저 "분석 시작"을 실행해주세요.')
    elif not st.session_state.seo_data:
        st.warning('SEO 분석 데이터가 없습니다. "분석 시작"을 먼저 실행해주세요.')
    else:
        product = st.session_state.product
        seo_data = st.session_state.seo_data

        # 글 구조 선택 (이력 기반 로테이션)
        used = get_used_structures()
        structure = blog_content.select_structure(used)

        # 리뷰 요약 생성
        review_text = ''
        if product.get('reviews'):
            from agents.scraper import summarize_reviews
            review_text = summarize_reviews(product['reviews'])

        with st.spinner(f'블로그 글 생성 중... (구조: {STRUCTURE_LABELS[structure]})'):
            result = blog_content.generate(
                product=product,
                seo_data=seo_data,
                structure_type=structure,
                purchase_url=product.get('purchase_url', product_url),
                spec_text=st.session_state.spec_text,
                review_text=review_text,
                youtube_text=st.session_state.youtube_subtitle,
                persona_key='brand',
            )
            st.session_state.blog_result = result
            st.session_state.selected_title_idx = 0  # 새 글 생성 시 인덱스 초기화

        # 이미지 블로그용 준비
        if st.session_state.images:
            prepared = blog_image.prepare_blog_images(
                st.session_state.images, product['pcode'],
                product_name=product.get('name', ''))
            st.session_state.images = prepared

        # 포스팅 키트 생성
        title = result['titles'][0] if result['titles'] else product['name']
        kit = blog_publisher.create_posting_kit(
            pcode=product['pcode'],
            title=title,
            body_html=result.get('body_html', ''),
            tags=result.get('tags', []),
            image_paths=st.session_state.images,
            image_guide=result.get('image_guide', ''),
        )
        st.session_state.kit = kit

        # 발행 로그
        log_publish(
            pcode=product['pcode'],
            product_name=product['name'],
            keywords=seo_data.get('keywords', []),
            structure_type=structure,
            title=title,
            body_length=len(result.get('body_text', '')),
            tag_count=len(result.get('tags', [])),
            image_count=len(st.session_state.images),
        )

        st.rerun()


# ══════════════════════════════════════
#  메인 화면
# ══════════════════════════════════════

# ── 헤더 ──
_html("""<div style="text-align:center; padding:20px 0 10px;">
    <h1 style="color:#1a1a1a; margin:0;">네이버 블로그 자동화 v3</h1>
    <p style="color:#888; font-size:14px;">AI-Powered Blog Content Factory</p>
</div>""")


# ══════════════════════════════════════
#  SEO 인사이트 카드
# ══════════════════════════════════════

if st.session_state.seo_data:
    seo = st.session_state.seo_data

    col1, col2, col3 = st.columns(3)

    with col1:
        kw_tags = ''.join([f'<span class="kw-tag">{kw}</span>' for kw in seo.get('keywords', [])])
        _html(f"""<div class="seo-card">
            <h3>트렌드 키워드</h3>
            <div style="margin-top:8px;">{kw_tags}</div>
        </div>""")

    with col2:
        total_vol = sum(v.get('total', 0) for v in seo.get('search_volumes', {}).values())
        _html(f"""<div class="seo-card" style="background:linear-gradient(135deg,#f093fb,#f5576c);">
            <h3>월간 검색량</h3>
            <div class="value">{total_vol:,}회</div>
            <div style="font-size:12px; opacity:0.8;">40~50대 타겟</div>
        </div>""")

    with col3:
        blog_count = len(seo.get('competitor_blogs', []))
        best_kw = seo.get('best_keyword', '')
        _html(f"""<div class="seo-card" style="background:linear-gradient(135deg,#4facfe,#00f2fe);">
            <h3>경쟁 블로그</h3>
            <div class="value">{blog_count}개 분석</div>
            <div style="font-size:12px; opacity:0.8;">최적 키워드: {best_kw}</div>
        </div>""")


# ══════════════════════════════════════
#  캡쳐 이미지 미리보기 (분석 후 바로 표시)
# ══════════════════════════════════════

if st.session_state.images and st.session_state.seo_data:
    with st.expander(f'캡쳐 이미지 ({len(st.session_state.images)}개)', expanded=True):
        img_cols = st.columns(5)
        for i, img_path in enumerate(st.session_state.images):
            if os.path.exists(img_path):
                with img_cols[i % 5]:
                    st.image(img_path, caption=f'{i+1}', use_container_width=True)


# ══════════════════════════════════════
#  메인 탭
# ══════════════════════════════════════

if st.session_state.blog_result:
    result = st.session_state.blog_result
    product = st.session_state.product

    tab1, tab2, tab3, tab4 = st.tabs([
        '미리보기', 'HTML 소스', '텍스트', '포스팅 키트'
    ])

    # ── 탭1: 미리보기 ──
    with tab1:
        # 구조 타입 배지
        stype = result.get('structure_type', 'A')
        _html(f"""<span class="structure-badge st-badge-{stype}">
            구조 {stype}: {STRUCTURE_LABELS.get(stype, '')}
        </span>""")

        st.markdown('---')

        # 제목 선택 (클릭 시 복사)
        titles = result.get('titles', [])
        if titles:
            st.subheader('제목 후보 (클릭하면 복사)')
            for i, t in enumerate(titles):
                if st.button(t, key=f'title_{i}', use_container_width=True):
                    st.session_state.selected_title_idx = i
                    if IS_CLOUD:
                        st.code(t, language=None)
                        st.toast('위 텍스트를 드래그해서 복사하세요')
                    else:
                        try:
                            import subprocess
                            subprocess.run(['clip'], input=t.encode('utf-8'), check=True)
                            st.toast(f'제목 복사됨: {t}')
                        except Exception:
                            pass

            idx = min(st.session_state.selected_title_idx, len(titles) - 1)
            selected_title = titles[idx]
            st.success(f'선택된 제목: {selected_title}')

        # 본문 미리보기 + 복사 버튼
        st.markdown('---')
        body_html = result.get('body_html', '')
        copy_col1, copy_col2 = st.columns([3, 1])
        with copy_col1:
            st.subheader('본문 미리보기')
        with copy_col2:
            if st.button('복사하기', key='copy_body_tags', type='primary', use_container_width=True):
                copy_html = body_html
                if result.get('tags'):
                    copy_html += '<br><br><p>' + ' &nbsp; '.join([f'#{t}' for t in result['tags']]) + '</p>'
                if IS_CLOUD:
                    from agents.blog_publisher import _html_to_plain
                    st.session_state['_copy_text'] = _html_to_plain(copy_html)
                    st.toast('아래에 복사용 텍스트가 표시됩니다.')
                else:
                    blog_publisher.copy_html_to_clipboard(copy_html)
                    st.success('본문 + 태그 복사 완료! 네이버 에디터에서 Ctrl+V 하세요.')

        # 클라우드 복사용 텍스트 (버튼 클릭 후 표시)
        if IS_CLOUD and st.session_state.get('_copy_text'):
            st.text_area('복사용 텍스트 (Ctrl+A → Ctrl+C)', value=st.session_state['_copy_text'], height=300)

        if body_html:
            st.markdown(body_html, unsafe_allow_html=True)

        # 태그
        if result.get('tags'):
            st.markdown('---')
            tags_html = ''.join([f'<span class="blog-tag">#{t}</span>' for t in result['tags']])
            _html(f'<div style="margin:16px 0;">{tags_html}</div>')

    # ── 탭2: HTML 소스 ──
    with tab2:
        st.code(result.get('body_html', ''), language='html')

    # ── 탭3: 텍스트 ──
    with tab3:
        st.text_area(
            '텍스트 복사용',
            value=result.get('body_text', ''),
            height=400,
        )

    # ── 탭4: 포스팅 키트 ──
    with tab4:
        kit = st.session_state.kit

        if kit:
            col1, col2, col3 = st.columns(3)

            with col1:
                _html(f"""<div class="metric-card">
                    <div class="metric-value">{len(st.session_state.images)}</div>
                    <div class="metric-label">이미지 수</div>
                </div>""")
            with col2:
                _html(f"""<div class="metric-card">
                    <div class="metric-value">{len(result.get('tags', []))}</div>
                    <div class="metric-label">태그 수</div>
                </div>""")
            with col3:
                _html(f"""<div class="metric-card">
                    <div class="metric-value">{len(result.get('body_text', '')):,}</div>
                    <div class="metric-label">글자 수</div>
                </div>""")

            st.markdown('---')

            # 액션 버튼
            if IS_CLOUD:
                # 클라우드: 텍스트 복사만
                if st.button('텍스트 복사용 펼치기', type='primary', use_container_width=True):
                    from agents.blog_publisher import _html_to_plain
                    full = result.get('body_html', '')
                    if result.get('tags'):
                        full += '<br><br><p>' + ' &nbsp; '.join([f'#{t}' for t in result['tags']]) + '</p>'
                    st.text_area('Ctrl+A → Ctrl+C로 복사', value=_html_to_plain(full), height=300)
            else:
                bcol1, bcol2, bcol3 = st.columns(3)
                with bcol1:
                    if st.button('클립보드 복사 + 폴더 열기', type='primary', use_container_width=True):
                        body = result.get('body_html', '')
                        blog_publisher.copy_html_to_clipboard(body)
                        if kit.get('images_dir'):
                            blog_publisher.open_folder(kit['images_dir'])
                        st.success('클립보드 복사 완료! 이미지 폴더가 열렸습니다.')

                with bcol2:
                    if st.button('텍스트만 복사', use_container_width=True):
                        text = result.get('body_text', '')
                        try:
                            import subprocess
                            subprocess.run(['clip'], input=text.encode('utf-8'), check=True)
                            st.success('텍스트 복사 완료!')
                        except Exception:
                            st.warning('텍스트를 위 "텍스트" 탭에서 직접 복사해주세요.')

            with bcol3:
                if st.button('포스팅 키트 열기', use_container_width=True):
                    if kit.get('kit_dir'):
                        blog_publisher.open_folder(kit['kit_dir'])

            # 키트 구성 표시
            st.markdown('---')
            st.subheader('키트 구성')
            _html(f"""<div style="background:#f8f9fa; border-radius:10px; padding:16px; font-size:13px; line-height:2;">
                <strong>키트 폴더:</strong> {kit.get('kit_dir', '')}<br>
                <strong>HTML:</strong> blog_post.html<br>
                <strong>이미지:</strong> images/ ({len(st.session_state.images)}개)<br>
                <strong>가이드:</strong> guide.txt<br>
                <strong>태그:</strong> tags.txt
            </div>""")

            # 발행 가이드
            st.markdown('---')
            st.info("""
            **2분 발행 플로우:**
            1. "클립보드 복사 + 폴더 열기" 클릭
            2. 네이버 블로그 에디터에서 Ctrl+V
            3. 열린 이미지 폴더에서 순서대로 드래그&드롭
            4. 태그 복사 후 붙여넣기
            5. 발행!
            """)

        else:
            st.info('글을 생성하면 포스팅 키트가 여기에 표시됩니다.')

    # ══════════════════════════════════════
    #  페르소나 추가 생성
    # ══════════════════════════════════════

    st.markdown('---')
    st.subheader('다른 블로그용 추가 생성')
    st.caption('같은 상품이라도 완전히 다른 관점의 글을 생성합니다. 네이버 중복 감지에 걸리지 않습니다.')

    # 페르소나 버튼 5개
    pcols = st.columns(5)
    for i, (pkey, pdata) in enumerate(PERSONAS.items()):
        with pcols[i]:
            already = pkey in st.session_state.persona_results
            label = f"{pdata['icon']} {pdata['name']}"
            if already:
                label += ' ✓'
            if st.button(label, key=f'persona_{pkey}', use_container_width=True,
                         disabled=False):
                product = st.session_state.product
                seo_data = st.session_state.seo_data
                review_text = ''
                if product.get('reviews'):
                    from agents.scraper import summarize_reviews
                    review_text = summarize_reviews(product['reviews'])

                used = get_used_structures()
                structure = blog_content.select_structure(used)

                with st.spinner(f'{pdata["icon"]} {pdata["name"]} 글 생성 중...'):
                    p_result = blog_content.generate(
                        product=product,
                        seo_data=seo_data,
                        structure_type=structure,
                        purchase_url=product.get('purchase_url', product_url),
                        spec_text=st.session_state.spec_text,
                        review_text=review_text,
                        youtube_text=st.session_state.youtube_subtitle,
                        persona_key=pkey,
                    )
                st.session_state.persona_results[pkey] = p_result

                # 포스팅 키트도 생성
                p_title = p_result['titles'][0] if p_result['titles'] else product['name']
                blog_publisher.create_posting_kit(
                    pcode=f"{product['pcode']}_{pkey}",
                    title=p_title,
                    body_html=p_result.get('body_html', ''),
                    tags=p_result.get('tags', []),
                    image_paths=st.session_state.images,
                    image_guide=p_result.get('image_guide', ''),
                )

                log_publish(
                    pcode=product['pcode'],
                    product_name=product['name'],
                    keywords=seo_data.get('keywords', []),
                    structure_type=structure,
                    title=f"[{pdata['name']}] {p_title}",
                    body_length=len(p_result.get('body_text', '')),
                    tag_count=len(p_result.get('tags', [])),
                    image_count=len(st.session_state.images),
                )
                st.rerun()

    # 생성된 페르소나 글 표시
    if st.session_state.persona_results:
        for pkey, p_result in st.session_state.persona_results.items():
            pdata = PERSONAS[pkey]
            with st.expander(
                f"{pdata['icon']} {pdata['name']} — {p_result['titles'][0] if p_result['titles'] else ''}",
                expanded=False,
            ):
                _html(f"""<p style="color:{pdata['color']}; font-size:13px; margin:0 0 8px;">
                    {pdata['description']}
                </p>""")

                # 제목
                if p_result.get('titles'):
                    for t in p_result['titles']:
                        st.markdown(f"- **{t}**")

                # 본문 미리보기
                st.markdown('---')
                body = p_result.get('body_html', '')
                if body:
                    st.markdown(body, unsafe_allow_html=True)

                # 태그
                if p_result.get('tags'):
                    tags_html = ''.join([f'<span class="blog-tag">#{t}</span>' for t in p_result['tags']])
                    _html(f'<p style="margin-top:12px;">{tags_html}</p>')

                # 복사 버튼
                bcol1, bcol2 = st.columns(2)
                with bcol1:
                    if st.button('본문+태그 복사', key=f'copy_{pkey}', type='primary', use_container_width=True):
                        copy_html = body
                        if p_result.get('tags'):
                            copy_html += '<br><br><p>' + ' &nbsp; '.join([f'#{t}' for t in p_result['tags']]) + '</p>'
                        blog_publisher.copy_html_to_clipboard(copy_html)
                        st.success('본문+태그 복사 완료!')
                with bcol2:
                    kit_dir = str(OUTPUT_DIR / f"{st.session_state.product['pcode']}_{pkey}")
                    if st.button('키트 폴더 열기', key=f'kit_{pkey}', use_container_width=True):
                        blog_publisher.open_folder(kit_dir)


# ══════════════════════════════════════
#  SEO 상세 (하단)
# ══════════════════════════════════════

elif st.session_state.seo_data:
    seo = st.session_state.seo_data

    st.subheader('키워드별 검색량')
    import pandas as pd
    kw_data = []
    for kw in seo.get('keywords', []):
        vol = seo.get('search_volumes', {}).get(kw, {})
        trend = seo.get('search_trends', {}).get(kw, 0)
        kw_data.append({
            '키워드': kw,
            '월간총검색': vol.get('total', 0),
            'PC': vol.get('pc', 0),
            '모바일': vol.get('mobile', 0),
            '트렌드': trend,
        })
    if kw_data:
        st.dataframe(pd.DataFrame(kw_data), use_container_width=True)

    # 롱테일 키워드
    if seo.get('longtail_keywords'):
        st.subheader('롱테일 키워드 (경쟁 낮음)')
        lt_tags = ''.join([f'<b style="display:inline-block; background:#fff3e0; color:#e65100; padding:4px 12px; border-radius:16px; margin:3px; font-size:13px;">{kw}</b>' for kw in seo['longtail_keywords']])
        _html(f'<p>{lt_tags}</p>')

    # 구매자 리뷰 요약
    if st.session_state.product and st.session_state.product.get('reviews'):
        reviews = st.session_state.product['reviews']
        avg = sum(r.get('rating', 0) for r in reviews) / len(reviews) if reviews else 0
        st.subheader(f'구매자 리뷰 ({len(reviews)}개 | 평균 {avg:.1f}점)')
        for r in reviews[:5]:
            stars = int(r.get('rating', 0))
            _html(f"""<p style="background:#f8f9fa; padding:10px; border-radius:8px; margin:4px 0; font-size:13px;">
                <strong style="color:#ff9800;">{'★' * stars}{'☆' * (5 - stars)}</strong>
                <span style="color:#999; font-size:11px; margin-left:8px;">{r.get('date', '')}</span><br>
                {r.get('text', '')[:200]}
            </p>""")

    # 경쟁 블로그
    if seo.get('competitor_blogs'):
        st.subheader('경쟁 블로그 (상위 노출)')
        for i, blog in enumerate(seo['competitor_blogs'][:5]):
            _html(f"""<div style="background:{'#f8f9fa' if i%2==0 else '#fff'}; padding:12px; border-radius:8px; margin:4px 0;">
                <strong>{i+1}. {blog['title']}</strong><br>
                <span style="color:#666; font-size:13px;">{blog['description'][:100]}...</span><br>
                <span style="color:#999; font-size:12px;">{blog.get('bloggername', '')}</span>
            </div>""")

else:
    # 초기 화면
    _html("""<div style="text-align:center; padding:60px 20px; color:#aaa;">
        <div style="font-size:48px; margin-bottom:16px;">📝</div>
        <h3 style="color:#666;">상품 URL을 입력하고 "분석 시작"을 클릭하세요</h3>
        <p style="font-size:14px;">네이버 데이터랩 SEO 분석 → 경쟁 블로그 역설계 → AI 글 생성 → 2분 발행</p>
    </div>""")
