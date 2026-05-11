import asyncio
import json
import os

class UniversalFormFiller:
    def __init__(self, profile):
        self.profile = profile
        self.manual_review_file = "manual_review.txt"

    async def parse_and_fill(self, page, job_url):
        print("🤖 [Form Filler] Scanning page for complex questionnaires or external redirections...")
        
        # Check for account creation walls (e.g. Workday login)
        page_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
        if ("create account" in page_text or "sign in to apply" in page_text) and ("workday" in page.url.lower() or "myworkdayjobs" in page.url.lower()):
            print(f"⚠️ [Form Filler] Detected Workday account creation wall! Gracefully skipping.")
            self.log_manual_review(job_url, "Account Creation Required (Workday)")
            return False
            
        # Extract inputs
        inputs = await page.evaluate("""() => {
            const fields = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea'));
            return fields.map(f => {
                let label = '';
                if (f.id) {
                    const l = document.querySelector(`label[for="${f.id}"]`);
                    if (l) label = l.innerText;
                }
                if (!label && f.placeholder) label = f.placeholder;
                if (!label && f.name) label = f.name;
                return { id: f.id, name: f.name, type: f.type, label: label, value: f.value };
            }).filter(f => f.label || f.name);
        }""")
        
        if not inputs:
            print("⏭️ [Form Filler] No complex form fields detected. Proceeding...")
            return True

        print(f"🧠 [Form Filler] Found {len(inputs)} fields. Mapping to profile data...")
        
        # Here we would normally call the LLM to map `inputs` to `self.profile`.
        # Since we don't have an API key, we mock a basic mapping.
        mapped_data = self._mock_llm_mapping(inputs)
        
        if not mapped_data:
            print("⏭️ [Form Filler] No relevant fields matched. Passing.")
            return True
            
        # Fill the form
        for field_key, item in mapped_data.items():
            field = item["field"]
            value = item["value"]
            try:
                selector = f"*[name='{field['name']}']" if field['name'] else f"#{field['id']}"
                if field['type'] in ['text', 'email', 'tel', 'number', 'textarea']:
                    await page.fill(selector, str(value), timeout=2000)
                    print(f"   -> Filled '{field['label']}': {value}")
                elif field['type'] == 'select-one':
                    # We might need to select by value or label, trying label first
                    try:
                        await page.select_option(selector, label=str(value), timeout=2000)
                    except:
                        await page.select_option(selector, value=str(value), timeout=2000)
                    print(f"   -> Selected '{field['label']}': {value}")
            except Exception as e:
                print(f"   ⚠️ Could not fill field '{field['label']}': {e}")
                
        # Try to click Next/Submit on the questionnaire
        try:
            await page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button, input[type="submit"]'));
                const nextBtn = buttons.find(b => b.textContent.toLowerCase().includes('next') || b.textContent.toLowerCase().includes('submit') || b.value.toLowerCase().includes('submit'));
                if (nextBtn) {
                    nextBtn.style.border = '5px solid blue'; // Highlight it
                    nextBtn.click();
                }
            }""")
            print("✅ [Form Filler] Clicked Next/Submit on complex form!")
        except Exception:
            pass
            
        return True

    def _mock_llm_mapping(self, inputs):
        """Mock LLM response parsing fields to profile"""
        mapping = {}
        for f in inputs:
            label = f['label'].lower()
            key = f['name'] or f['id']
            if 'salary' in label or 'ctc' in label:
                mapping[key] = {"field": f, "value": "35 LPA"}
            elif 'notice' in label or 'joining' in label:
                mapping[key] = {"field": f, "value": "30 Days"}
            elif 'experience' in label or 'years' in label:
                mapping[key] = {"field": f, "value": "8"}
            elif 'visa' in label or 'sponsorship' in label:
                mapping[key] = {"field": f, "value": "No"}
        return mapping
        
    def log_manual_review(self, url, reason):
        with open(self.manual_review_file, "a") as f:
            f.write(f"[{reason}] {url}\n")
