"""
Shared LLM client — routes through LiteLLM proxy if configured,
falls back to direct Gemini API key. Prevents hitting the 20 req/day
free-tier quota on the direct Gemini endpoint.
"""
import os
from dotenv import load_dotenv

# Load from both project .env and parent .env so daemon picks up LITELLM_* vars
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"), override=False)


def build_llm(temperature: float = 0):
    """
    Returns a LangChain chat model, preferring the LiteLLM proxy.
    Priority:
      1. LITELLM_BASE_URL + LITELLM_API_KEY  → ChatOpenAI (OpenAI-compat endpoint)
      2. GOOGLE_API_KEY                       → ChatGoogleGenerativeAI (direct, quota-limited)
    """
    litellm_url = os.getenv("LITELLM_BASE_URL", "").strip().rstrip("/")
    litellm_key = os.getenv("LITELLM_API_KEY", "").strip()
    litellm_model = os.getenv("LITELLM_MODEL", "gemini-pro").strip()
    google_key = os.getenv("GOOGLE_API_KEY", "").strip()

    if litellm_url and litellm_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=litellm_model,
            temperature=temperature,
            openai_api_key=litellm_key,
            openai_api_base=f"{litellm_url}",
        )

    if google_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",   # more generous quota than gemini-flash-latest
            temperature=temperature,
            google_api_key=google_key,
        )

    raise RuntimeError(
        "No LLM credentials found. Set LITELLM_BASE_URL+LITELLM_API_KEY "
        "or GOOGLE_API_KEY in .env"
    )
