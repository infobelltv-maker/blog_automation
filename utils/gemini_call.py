import os, time, json
from google import genai
from google.genai import types
from utils.logger import get_logger

log = get_logger('gemini')
_client = None


def _get_client():
    global _client
    if _client is None:
        from config import get_secret
        _client = genai.Client(api_key=get_secret('GEMINI_API_KEY'))
    return _client


def call_gemini(
    prompt: str,
    response_schema=None,
    max_retries: int = 3,
    temperature: float = 0.3,
) -> str | dict:
    """
    Gemini API 호출 래퍼
    - temperature 기본값 0.3 (SEO 콘텐츠용: 일관성 높게)
    - response_schema 제공 시 JSON 모드
    """
    client = _get_client()
    config = types.GenerateContentConfig(
        temperature=temperature, max_output_tokens=8192)
    if response_schema:
        config.response_mime_type = 'application/json'
        config.response_schema = response_schema
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt, config=config)
            if not resp.text:
                raise ValueError('Gemini 응답이 비어있습니다')
            if response_schema:
                return json.loads(resp.text)
            return resp.text
        except Exception as e:
            wait = 2 ** (attempt + 1)
            if attempt < max_retries - 1:
                log.warning('재시도 %ds: %s', wait, e)
                time.sleep(wait)
            else:
                log.error('3회 실패: %s', e)
                raise
