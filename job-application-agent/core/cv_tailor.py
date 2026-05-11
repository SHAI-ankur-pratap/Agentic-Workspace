import os
from fpdf import FPDF
from dotenv import load_dotenv

load_dotenv()

class CVTailor:
    def __init__(self, base_cv_path="base_resume.md"):
        self.base_cv_path = base_cv_path

    def rewrite_cv(self, job_description: str) -> str:
        # Mock LLM rewriting
        print("🤖 [CV Tailor] Analyzing JD and prioritizing matching skills in resume...")
        with open(self.base_cv_path, "r") as f:
            base_md = f.read()
        
        # In a real scenario, LLM would rewrite `base_md` here.
        tailored_md = base_md.replace("## SUMMARY", "## SUMMARY\n*Tailored specifically for this role.*")
        return tailored_md

    def generate_pdf(self, md_content: str, output_path="tailored_cv.pdf"):
        print(f"📄 [CV Tailor] Compiling tailored CV to {output_path}...")
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)
        
        # Very crude Markdown stripping for MVP PDF generation
        clean_text = md_content.replace("#", "").replace("**", "")
        for line in clean_text.split('\n'):
            # Simple encoding handling for PDF
            safe_line = line.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(0, 5, txt=safe_line, ln=1)
            
        pdf.output(output_path)
        print("✅ Tailored CV generated successfully.")
        return output_path
