"""
Gemini API 블로그 글 생성
- JSON 스키마 기반 구조화 출력 (텍스트 파싱 제거)
- SEO 인텔리전스 + 경쟁사 분석 + 5가지 글 구조 반영
- 5가지 페르소나 멀티 블로그 생성
"""
import re
import random
from utils.logger import get_logger
from utils.gemini_call import call_gemini
from config import STRUCTURE_TYPES, STRUCTURE_LABELS

log = get_logger('blog_content')

# ══════════════════════════════════════
#  Gemini JSON 응답 스키마
# ══════════════════════════════════════

BLOG_RESPONSE_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'titles': {
            'type': 'ARRAY',
            'items': {'type': 'STRING'},
            'description': '제목 후보 3개 (25~40자, 핵심 키워드 앞쪽 배치)',
        },
        'body_html': {
            'type': 'STRING',
            'description': '네이버 에디터 호환 HTML 본문 (div/span 금지, 인라인 style만)',
        },
        'tags': {
            'type': 'ARRAY',
            'items': {'type': 'STRING'},
            'description': '블로그 태그 8~10개 (# 붙이지 말 것)',
        },
        'image_guide': {
            'type': 'STRING',
            'description': '이미지 배치 가이드 (이미지1: 위치설명, 이미지2: ...)',
        },
    },
    'required': ['titles', 'body_html', 'tags', 'image_guide'],
}

# ══════════════════════════════════════
#  5가지 글 구조 프롬프트
# ══════════════════════════════════════

STRUCTURE_PROMPTS = {
    'A': """[리뷰형 구조]
- 도입부: "직접 써보고 알려드립니다" 식의 개인 경험 시작
- 본문: 사용 경험 → 장점 3가지 → 단점 1가지(솔직함) → 추천 이유
- CTA: 본문 중간과 마지막에 자연스러운 구매 유도
- 문단 수: 7~9개
- 이미지 위치: 도입부 뒤(1), 장점마다(3), 마무리(1) = 총 5장""",

    'B': """[비교형 구조]
- 도입부: "이런 제품들과 비교해봤습니다" 식의 비교 프레임
- 본문: 비교 기준 설명 → 3개 제품 비교 → 이 제품의 차별점 → 결론
- CTA: 비교 결론 직후 1회
- 문단 수: 8~10개
- 이미지 위치: 비교표 전(1), 각 제품(3), 결론(1) = 총 5장""",

    'C': """[Q&A형 구조]
- 도입부: "이런 고민이셨죠?" 식의 질문으로 시작
- 본문: 질문 4~5개 → 각 질문에 대한 답변 형식으로 전개
- CTA: 마지막 질문 답변 후 1회
- 문단 수: 8~10개
- 이미지 위치: 첫 질문 뒤(1), 중간 질문(2), 마무리(1) = 총 4장""",

    'D': """[스토리형 구조]
- 도입부: "어머니가 이걸 써보신 후" 식의 인물 중심 서사
- 본문: 문제 상황 → 발견 계기 → 사용 과정 → 변화/결과 → 추천
- CTA: 스토리 클라이맥스 직후 1회, 마무리 1회
- 문단 수: 6~8개
- 이미지 위치: 도입(1), 사용 과정(2), 결과(1), 마무리(1) = 총 5장""",

    'E': """[전문가형 구조]
- 도입부: "전문가가 추천하는" 식의 권위 있는 톤
- 본문: 원리 설명 → 핵심 기능 분석 → 사양 비교 → 전문가 평가 → 추천
- CTA: 전문가 평가 직후 1회
- 문단 수: 8~11개
- 이미지 위치: 원리 설명(1), 기능별(3), 마무리(1) = 총 5장""",
}


# ══════════════════════════════════════
#  5가지 페르소나 (멀티 블로그용)
# ══════════════════════════════════════

PERSONAS = {
    'brand': {
        'name': '브랜드 담당자',
        'icon': '🏢',
        'color': '#1565c0',
        'description': '인포벨 담당자가 이웃에게 말하듯 친근하게 소개하는 글',
        'prompt': """당신은 "인포벨"에서 이 상품을 담당하는 직원입니다.
블로그 이웃에게 좋은 상품을 소개해주는 느낌으로 글을 씁니다.

[화자 설정]
- 회사 직원이지만 딱딱한 공식 홍보가 아니라, 블로그 이웃에게 편하게 추천하는 느낌
- "저희 회사 제품이라 이렇게 말하면 좀 그렇지만... 진짜 괜찮거든요ㅎㅎ" 식의 솔직함
- 내부자니까 아는 숨은 장점, 사용 팁, 개발 뒷이야기를 자연스럽게 공유
- 고객 입장에서 "이건 꼭 알려드리고 싶었어요" 하는 진심이 느껴지게

[문체]
- 부드러운 구어체 존댓말 ("~예요", "~거든요", "~드릴게요", "~했답니다")
- 친구 언니/오빠가 추천해주는 따뜻한 톤
- 이모티콘은 쓰지 않되, "ㅎㅎ", "~요!" 정도의 가벼운 표현 OK
- "혹시 이런 고민 있으셨어요?", "이 부분이 제일 좋은 포인트인데요" 식의 대화형

[구조]
- 도입: "안녕하세요~ 오늘은 정말 소개해드리고 싶은 제품이 있어서 왔어요"
- 본문: 이 상품을 추천하는 이유 3가지 + 직접 써본 소감 + 고객 반응 + 활용 팁
- CTA: "한번 써보시면 아실 거예요~" (자연스럽게 1회)
- 문단 7~9개, 이미지 5장""",
    },

    'buyer': {
        'name': '구매 고민러',
        'icon': '🤔',
        'color': '#e65100',
        'description': 'TV에서 보고 살까 말까 고민하다 직접 알아본 후기',
        'prompt': """당신은 TV홈쇼핑/SNS 광고를 보고 이 상품에 관심이 생긴 40대 직장인입니다.

[화자 설정]
- "TV에서 보고 혹해서 찾아봤는데요" 식의 솔직한 소비자
- 구매 전 꼼꼼하게 비교하고 따져보는 신중한 성격
- 가격 대비 가치(가성비)를 중요하게 생각
- "나만 몰랐나?" 하는 발견의 느낌

[문체]
- 구어체 존댓말 ("~거든요", "~더라고요", "~잖아요")
- 친구에게 말하듯 편안한 톤
- 감정 표현 자유 ("솔직히 반신반의했는데...", "이건 진짜 놀랐어요")

[구조]
- 도입: 광고를 보게 된 상황 + 첫인상
- 본문: 가격 비교 → 다른 구매자 후기 분석 → 장단점 정리 → 최종 판단
- CTA: "결국 저는 이걸로 결정했습니다" (자연스러운 마무리)
- 문단 6~8개, 이미지 4장""",
    },

    'expert': {
        'name': '상품 분석가',
        'icon': '🔬',
        'color': '#6a1b9a',
        'description': '성분/스펙을 깊이 분석하는 전문 리뷰어 관점',
        'prompt': """당신은 10년 경력의 상품 리뷰 전문 블로거입니다.

[화자 설정]
- 해당 카테고리 제품을 수십 개 테스트해본 전문가
- 스펙 시트를 읽을 줄 알고, 성분/소재의 차이를 설명할 수 있음
- 객관적 데이터 기반 평가, 감정보다 근거 중시
- "이 가격대에서 이 스펙은..." 식의 시장 맥락 제공

[문체]
- 분석적 존댓말 ("~인 것으로 확인됩니다", "~라고 볼 수 있습니다")
- 수치/데이터 적극 인용
- 비교 대상 언급하되 특정 브랜드 비방 금지

[구조]
- 도입: 이 제품이 주목받는 이유 (시장 트렌드)
- 본문: 핵심 스펙 분석 → 경쟁 제품 비교표 → 사용감 테스트 → 가성비 평가
- CTA: "스펙이 궁금하신 분은 직접 확인해보세요" (1회)
- 문단 8~11개, 이미지 5장""",
    },

    'family': {
        'name': '살림 경험자',
        'icon': '👩‍👧‍👦',
        'color': '#2e7d32',
        'description': '가족을 위해 꼼꼼히 따지는 50대 주부의 생생 체험기',
        'prompt': """당신은 3인 가족을 돌보는 52세 주부입니다.

[화자 설정]
- 건강과 살림에 관심이 많고, 가족 건강을 최우선으로 생각
- "우리 남편이 허리가 안 좋아서..." 식의 구체적 가족 상황 언급
- 2주 이상 직접 사용한 뒤 쓰는 생생한 체험기
- 실생활 활용 팁을 곁들이는 스타일

[문체]
- 따뜻한 구어체 ("~예요", "~거든요", "~했어요")
- 주부 커뮤니티에서 쓰는 일상적 표현
- 가격/실용성 관련 솔직한 언급 ("솔직히 좀 비싸다 싶었는데...")

[구조]
- 도입: 구매 계기 (가족의 필요)
- 본문: 개봉기 → 첫 사용 소감 → 2주 사용 변화 → 가족 반응 → 재구매 의사
- CTA: "관심 있으신 분들은 한번 보세요~" (친근한 톤)
- 문단 7~9개, 이미지 5장""",
    },

    'gift': {
        'name': '선물 추천러',
        'icon': '🎁',
        'color': '#c62828',
        'description': '부모님/지인 선물로 고르며 비교 분석한 기록',
        'prompt': """당신은 부모님 선물을 찾고 있는 35세 직장인 자녀입니다.

[화자 설정]
- 부모님(60대) 또는 시부모님 선물로 이 상품을 검토 중
- "어버이날 선물 뭐가 좋을까 한참 찾았는데요" 식의 도입
- 선물용으로서의 가치 (포장, 만족도, 실용성)에 집중
- 실제로 드린 후 반응까지 포함

[문체]
- 밝고 정성스러운 톤 ("~드렸더니", "~좋아하시더라고요")
- 선물 고르는 과정의 고민을 공유
- 예산 대비 만족도 강조

[구조]
- 도입: 선물 고르게 된 계기 (기념일/효도)
- 본문: 후보 3개 비교 → 이 상품을 고른 이유 → 선물 후 반응 → 포장/배송 평가
- CTA: "부모님 선물 고민이시면 추천드려요" (1회)
- 문단 6~8개, 이미지 4장""",
    },
}

PERSONA_KEYS = list(PERSONAS.keys())


def select_structure(used_history: list = None) -> str:
    """5가지 글 구조 중 하나를 선택 (최근 사용 이력 고려)"""
    available = list(STRUCTURE_TYPES)
    if used_history:
        recent = used_history[-3:]
        available = [t for t in available if t not in recent]
        if not available:
            available = list(STRUCTURE_TYPES)
    choice = random.choice(available)
    log.info('글 구조 선택: %s (%s)', choice, STRUCTURE_LABELS[choice])
    return choice


def generate(
    product: dict,
    seo_data: dict,
    structure_type: str,
    purchase_url: str = '',
    spec_text: str = '',
    review_text: str = '',
    youtube_text: str = '',
    persona_key: str = '',
) -> dict:
    """
    블로그 글 생성 (JSON 스키마 기반)

    Args:
        persona_key: '' = 기본 생성, 'brand'/'buyer'/'expert'/'family'/'gift' = 페르소나
    """
    persona = PERSONAS.get(persona_key)
    if persona:
        log.info('페르소나 글 생성: %s [%s] (구조 %s)',
                 persona['name'], product.get('name'), structure_type)
    else:
        log.info('글 생성 시작: %s (구조 %s)', product.get('name'), structure_type)

    # ── 참고 자료 구성 ──
    ref_sections = _build_reference_sections(
        product, seo_data, spec_text, review_text, youtube_text)

    keywords = seo_data.get('keywords', [])
    best_kw = seo_data.get('best_keyword', keywords[0] if keywords else '')
    cta_link = purchase_url or product.get('purchase_url', '')

    trend_text = ''
    for kw, score in seo_data.get('search_trends', {}).items():
        vol = seo_data.get('search_volumes', {}).get(kw, {})
        trend_text += f"- {kw}: 월간검색 {vol.get('total', 0):,}회\n"

    longtail = seo_data.get('longtail_keywords', [])
    longtail_text = ''
    if longtail:
        longtail_text = f"\n롱테일 키워드 (본문 중 자연스러운 위치에 각 1회만 포함):\n{', '.join(longtail)}"

    competitor_text = ''
    blogs = seo_data.get('competitor_blogs', [])
    if blogs:
        titles_list = '\n'.join([f"  - {b['title']}" for b in blogs[:5]])
        competitor_text = f"""경쟁 블로그 상위 5개 제목:
{titles_list}

위 경쟁 블로그들이 다루지 않는 각도나 빈틈을 찾아서, 그 부분을 깊이 다뤄주세요."""

    # ── 페르소나 프롬프트 구성 ──
    if persona:
        role_prompt = persona['prompt']
        structure_prompt = ''  # 페르소나 자체에 구조 지시가 있으므로 별도 구조 불필요
    else:
        role_prompt = "당신은 네이버 블로그 SEO 전문가입니다.\n40~50대 독자를 위한 상품 블로그 글을 작성합니다."
        structure_prompt = f"\n═══ 글 구조 ═══\n{STRUCTURE_PROMPTS[structure_type]}\n"

    prompt = f"""{role_prompt}

═══ 상품 ═══
상품명: {product.get('name', '')}
가격: {product.get('price', '')}원
설명: {product.get('description', '')}
{ref_sections}

═══ 키워드 ═══
핵심 키워드: {best_kw}
보조 키워드: {', '.join([k for k in keywords if k != best_kw])}
{trend_text}{longtail_text}

═══ 경쟁 분석 ═══
{competitor_text if competitor_text else '(경쟁 데이터 없음 — 독창적으로 작성)'}
{structure_prompt}
═══ 작성 규칙 ═══

[제목] 25~40자, 핵심 키워드를 앞쪽에 배치. 특수문자(★▶●) 금지.

[본문 HTML]
- 허용 태그: <p>, <br>, <strong>, <b>, <em>, <h3>, <ul>, <ol>, <li>, <a>, <table>
- 금지 태그: <div>, <span> — 네이버 에디터가 제거함
- 첫 문장에 핵심 키워드 "{best_kw}" 자연스럽게 포함 (검색 인덱싱 핵심)
- <h3> 소제목에 키워드 또는 연관어 포함
- 키워드 밀도 2~3%, 같은 단어 연속 반복 금지 — 유사어로 변형
- 문단마다 3~5문장, 문단 사이 <br><br>
- 본문 2000~3000자
- 이미지 위치에 <!--IMAGE_N--> 삽입 (N=1,2,3...)
- CTA 1~2회, 자연스럽게: <a href="{cta_link}">자세한 내용 보기</a>

[태그] 8~10개, # 붙이지 말 것. 핵심+롱테일+연관어 조합.
[금지] 허위 과장, 의료 효능, 최상급(최고/1등/100%), 광고 표기 문구.

★ 중요: 이 글은 다른 블로그에 올릴 완전히 독립적인 글입니다.
같은 상품이라도 이전에 생성된 글과 제목, 도입부, 소제목, 문장 표현이 모두 달라야 합니다.
화자의 관점과 경험에 충실하게, 이 페르소나만의 고유한 글을 작성하세요.
"""

    try:
        result = call_gemini(prompt, response_schema=BLOG_RESPONSE_SCHEMA)
    except Exception as e:
        log.error('JSON 모드 실패, 텍스트 모드로 재시도: %s', e)
        result = _fallback_generate(prompt)

    parsed = _postprocess(result)
    parsed['structure_type'] = structure_type
    parsed['persona_key'] = persona_key
    parsed['persona_name'] = persona['name'] if persona else '기본'

    log.info('글 생성 완료: [%s] 제목 %d개, 본문 %d자',
             parsed['persona_name'], len(parsed['titles']), len(parsed['body_text']))
    return parsed


def _build_reference_sections(product, seo_data, spec_text, review_text, youtube_text):
    """기술서/리뷰/자막 참고자료 섹션을 합쳐서 반환"""
    sections = ''

    if spec_text:
        trimmed = spec_text[:4000]
        if len(spec_text) > 4000:
            trimmed += '\n... (이하 생략)'
        sections += f"""
═══ 상품 기술서 (핵심 참고 자료) ═══
기술서의 핵심 스펙, 기능, 성분, 특장점을 정확하게 반영하세요.
구체적 수치, 인증, 소재 정보는 신뢰도 근거로 활용하세요.
기술서를 그대로 복붙하지 말고 화자의 말투로 풀어 쓰세요.

{trimmed}
"""

    if review_text:
        sections += f"""
═══ 실사용 리뷰 (구매자 후기) ═══
긍정 리뷰의 핵심 포인트는 "실제 사용자 반응"으로 인용하세요.
부정 리뷰가 있다면 솔직하게 언급하되, 해결책이나 대안을 함께 제시하세요.

{review_text}
"""

    if youtube_text:
        trimmed_yt = youtube_text[:3000]
        if len(youtube_text) > 3000:
            trimmed_yt += ' ... (이하 생략)'
        sections += f"""
═══ YouTube 영상 자막 ═══
영상에서 언급하는 핵심 포인트, 사용법, 장단점을 자연스럽게 반영하세요.

{trimmed_yt}
"""

    return sections


def _postprocess(data: dict) -> dict:
    """Gemini 응답 후처리"""
    titles = data.get('titles', [])
    clean_titles = []
    for t in titles:
        t = re.sub(r'^[\d]+[.)]\s*', '', str(t))
        t = re.sub(r'^[-*]\s*', '', t)
        t = t.strip('"\'').strip()
        if t:
            clean_titles.append(t)

    body_html = data.get('body_html', '')
    body_html = re.sub(r'^```(?:html)?\s*\n?', '', body_html)
    body_html = re.sub(r'\n?```\s*$', '', body_html)
    body_html = body_html.strip()

    tags = [str(t).lstrip('#').strip() for t in data.get('tags', []) if str(t).strip()]

    return {
        'titles': clean_titles[:3],
        'body_html': body_html,
        'body_text': re.sub(r'<[^>]+>', '', body_html),
        'tags': tags[:10],
        'image_guide': data.get('image_guide', ''),
    }


def _fallback_generate(prompt: str) -> dict:
    """JSON 스키마 실패 시 텍스트 파싱 폴백"""
    text = call_gemini(prompt)

    sections = {}
    current_key = None
    current_lines = []

    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('===') and stripped.endswith('==='):
            if current_key:
                sections[current_key] = '\n'.join(current_lines).strip()
            current_key = stripped.replace('===', '').strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_key:
        sections[current_key] = '\n'.join(current_lines).strip()

    titles = []
    if '제목' in sections:
        titles = [t.strip() for t in sections['제목'].split('\n') if t.strip()]

    tags = []
    if '태그' in sections:
        tags = [t.strip() for t in sections['태그'].split(',') if t.strip()]

    return {
        'titles': titles[:3],
        'body_html': sections.get('본문HTML', sections.get('본문', '')),
        'tags': tags,
        'image_guide': sections.get('이미지가이드', ''),
    }
