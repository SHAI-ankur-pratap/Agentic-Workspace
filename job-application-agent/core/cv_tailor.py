import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
import markdown2
from core.llm_helper import extract_text
from core.llm_client import build_llm

load_dotenv()


class CVTailor:
    def __init__(self, base_cv_path="base_resume.md"):
        self.base_cv_path = base_cv_path
        self.llm = build_llm(temperature=0.3)

    def rewrite_cv(self, job_description: str) -> str:
        with open(self.base_cv_path, "r") as f:
            base_md = f.read()

        prompt = f"""You are a professional resume writer. Tailor the resume below for the job description.

RULES:
- Reorder bullets to lead with most-relevant experience
- Naturally weave in keywords from the JD
- Adjust the SUMMARY line for this specific role
- Do NOT fabricate experience, skills, titles, or dates
- Output ONLY the complete resume in Markdown, no extra commentary

JOB DESCRIPTION:
{job_description[:2000]}

RESUME:
{base_md}"""

        for attempt in range(3):
            try:
                response = self.llm.invoke([HumanMessage(content=prompt)])
                tailored = extract_text(response.content).strip()
                if tailored.startswith("```"):
                    tailored = tailored.split("```")[1]
                    if tailored.startswith(("markdown", "md")):
                        tailored = tailored.split("\n", 1)[1]
                if len(tailored) > 300:
                    return tailored
            except Exception as e:
                print(f"⚠️ [CV Tailor] Attempt {attempt + 1} failed: {e}")

        print("⚠️ [CV Tailor] LLM failed, using base resume.")
        return base_md

    async def generate_pdf(self, md_content: str, output_path: str = "tailored_cv.pdf") -> str:
        print(f"📄 [CV Tailor] Rendering PDF → {output_path}...")
        html_body = markdown2.markdown(md_content, extras=["tables", "fenced-code-blocks"])
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 15mm 20mm; line-height: 1.45; color: #222; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  h2 {{ font-size: 13px; border-bottom: 1px solid #555; margin: 14px 0 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
  h3 {{ font-size: 11px; font-weight: bold; margin: 8px 0 2px; }}
  ul {{ margin: 3px 0 6px; padding-left: 16px; }}
  li {{ margin-bottom: 2px; }}
  p {{ margin: 3px 0; }}
  a {{ color: #222; text-decoration: none; }}
</style>
</head><body>{html_body}</body></html>"""

        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            await page.pdf(
                path=output_path,
                format="A4",
                margin={"top": "15mm", "bottom": "15mm", "left": "20mm", "right": "20mm"},
            )
            await browser.close()

        print("✅ [CV Tailor] PDF generated.")
        return output_path
