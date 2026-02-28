import os
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception


AI_INTEGRATIONS_GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY")
AI_INTEGRATIONS_GEMINI_BASE_URL = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL")

client = genai.Client(
    api_key=AI_INTEGRATIONS_GEMINI_API_KEY,
    http_options={
        'api_version': '',
        'base_url': AI_INTEGRATIONS_GEMINI_BASE_URL
    }
)

MODEL = "gemini-2.5-flash"


def is_rate_limit_error(exception):
    error_msg = str(exception)
    return (
        "429" in error_msg
        or "RATELIMIT_EXCEEDED" in error_msg
        or "quota" in error_msg.lower()
        or "rate limit" in error_msg.lower()
        or (hasattr(exception, 'status') and exception.status == 429)
    )


def estimate_tokens(text):
    return len(text) // 4


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(is_rate_limit_error),
    reraise=True
)
def summarize_judgments(judgment_texts, prompt_template):
    combined = prompt_template + "\n\n---\n\n"
    for i, jt in enumerate(judgment_texts):
        combined += f"## Judgment {i+1}\n\n{jt}\n\n---\n\n"

    response = client.models.generate_content(
        model=MODEL,
        contents=combined,
        config=types.GenerateContentConfig(max_output_tokens=8192)
    )
    return response.text or ""
