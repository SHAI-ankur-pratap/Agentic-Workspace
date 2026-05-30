"""
Shared LLM client — uses Google Gemini API directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def build_llm(temperature: float = 0):
    """Returns a LangChain model with fallbacks between LiteLLM proxy and direct Google API."""
    litellm_key = os.getenv("LITELLM_API_KEY", "").strip()
    litellm_url = os.getenv("LITELLM_BASE_URL", "").strip()
    litellm_model = os.getenv("LITELLM_MODEL", "hackathon-gemini-2.5-flash").strip()
    google_key = os.getenv("GOOGLE_API_KEY", "").strip()

    models = []

    if litellm_key and litellm_url:
        from langchain_openai import ChatOpenAI
        print(f"🤖 Initializing LangChain model '{litellm_model}' via LiteLLM proxy...")
        models.append(ChatOpenAI(
            model=litellm_model,
            api_key=litellm_key,
            base_url=litellm_url,
            temperature=temperature,
        ))

    if google_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        print("🤖 Initializing LangChain model 'gemini-2.5-flash' directly via Google API...")
        models.append(ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=temperature,
            google_api_key=google_key,
        ))

    if not models:
        raise RuntimeError("Neither LITELLM_API_KEY nor GOOGLE_API_KEY is set in .env")

    # If we have both, use LiteLLM as primary and direct Google API as fallback
    if len(models) == 2:
        return models[0].with_fallbacks([models[1]])
    return models[0]


