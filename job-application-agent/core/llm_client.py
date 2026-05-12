"""
Shared LLM client — uses Google Gemini API directly.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def build_llm(temperature: float = 0):
    """Returns a LangChain ChatGoogleGenerativeAI model using GOOGLE_API_KEY."""
    google_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not google_key:
        raise RuntimeError("GOOGLE_API_KEY not set in .env")

    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=temperature,
        google_api_key=google_key,
    )
