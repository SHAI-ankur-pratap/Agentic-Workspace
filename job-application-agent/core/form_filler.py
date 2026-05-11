import json
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

load_dotenv()

ACCOUNT_WALL_PHRASES = ["create account", "sign in to apply", "register to apply", "sign up to apply"]
WORKDAY_HOSTS = ["myworkdayjobs.com", "wd3.myworkdaysite.com", "wd1.myworkdaysite.com"]


class UniversalFormFiller:
    def __init__(self, profile: dict):
        self.profile = profile
        self.manual_review_file = "manual_review.txt"
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    async def parse_and_fill(self, page, job_url: str) -> bool:
        print("🤖 [Form Filler] Scanning page for form fields...")

        try:
            page_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
        except Exception:
            page_text = ""

        url_lower = getattr(page, "url", job_url).lower()
        is_workday = any(h in url_lower for h in WORKDAY_HOSTS)
        has_account_wall = any(phrase in page_text for phrase in ACCOUNT_WALL_PHRASES)

        if is_workday and has_account_wall:
            print("⛔ [Form Filler] Workday account wall detected. Skipping.")
            self._log_manual_review(job_url, "Account Creation Required (Workday)")
            return False

        inputs = await page.evaluate("""() => {
            const fields = Array.from(document.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="file"]), select, textarea'
            ));
            return fields.map(f => {
                let label = '';
                if (f.id) {
                    const l = document.querySelector(`label[for="${f.id}"]`);
                    if (l) label = l.innerText.trim();
                }
                if (!label && f.placeholder) label = f.placeholder;
                if (!label && f.name) label = f.name;
                let options = [];
                if (f.tagName === 'SELECT') {
                    options = Array.from(f.options).map(o => o.text.trim()).filter(Boolean);
                }
                return { id: f.id, name: f.name, type: f.type || f.tagName.toLowerCase(), label, options };
            }).filter(f => f.label || f.name);
        }""")

        if not inputs:
            print("⏭️ [Form Filler] No form fields found.")
            return True

        print(f"🧠 [Form Filler] {len(inputs)} fields detected. Mapping via Gemini...")

        pi = self.profile.get("personal_info", {})
        prefs = self.profile.get("preferences", {})
        qa_bank = self.profile.get("qa_bank", [])
        qa_examples = "\n".join(f"Q: {q['question']} → A: {q['answer']}" for q in qa_bank)

        prompt = f"""Map these HTML form fields to the candidate profile. Return ONLY valid JSON, no markdown.

CANDIDATE:
Name: {pi.get('first_name', '')} {pi.get('last_name', '')}
Email: {pi.get('email', '')}
Phone: {pi.get('phone', '')}
Location: {pi.get('location', '')}
Current Salary: {prefs.get('current_salary', '')}
Expected Salary: {prefs.get('minimum_salary', '')}
Notice Period: 30 days

KNOWN Q&A:
{qa_examples}

FORM FIELDS:
{json.dumps(inputs, indent=2)}

Return a flat JSON object mapping field name/id to fill value.
For fields you cannot confidently answer, set value to "__SKIP__".
ONLY the JSON object, nothing else."""

        mapping = {}
        for attempt in range(3):
            try:
                response = self.llm.invoke([HumanMessage(content=prompt)])
                text = response.content.strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                mapping = json.loads(text.strip())
                break
            except Exception as e:
                if attempt == 2:
                    print(f"⚠️ [Form Filler] LLM failed: {e}. Skipping fill.")
                    return True

        for field_key, value in mapping.items():
            if value == "__SKIP__":
                self._log_manual_review(job_url, f"Low-confidence field: {field_key}")
                continue
            field_info = next(
                (f for f in inputs if f["name"] == field_key or f["id"] == field_key), None
            )
            if not field_info:
                continue
            selector = f"[name='{field_key}']" if field_key else f"#{field_info['id']}"
            try:
                ftype = field_info["type"]
                if ftype in ("text", "email", "tel", "number", "textarea", "search", "url"):
                    await page.fill(selector, str(value), timeout=2000)
                elif ftype in ("select-one", "select"):
                    try:
                        await page.select_option(selector, label=str(value), timeout=2000)
                    except Exception:
                        await page.select_option(selector, value=str(value), timeout=2000)
                elif ftype == "radio":
                    await page.check(f"[name='{field_key}'][value='{value}']", timeout=2000)
                elif ftype == "checkbox":
                    if str(value).lower() in ("yes", "true", "1"):
                        await page.check(selector, timeout=2000)
                print(f"   ✅ '{field_info['label']}' → {value}")
            except Exception as e:
                print(f"   ⚠️ Could not fill '{field_key}': {e}")

        return True

    def _log_manual_review(self, url: str, reason: str):
        with open(self.manual_review_file, "a") as f:
            f.write(f"[{reason}] {url}\n")
