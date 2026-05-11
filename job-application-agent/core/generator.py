import os
from dotenv import load_dotenv

load_dotenv()

class ApplicationGenerator:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("Warning: No API key found in .env. Generation features will be mocked.")
            self.llm = None
        else:
            print("✅ LLM generator initialized.")
            # In a real scenario, initialize langchain model here.
            self.llm = True
            
    def generate_cover_letter(self, profile: dict, job_description: str) -> str:
        if not self.llm:
            return "[Mock Cover Letter: Dear Hiring Manager, I am a great fit for this role...]"
            
        print("Generating cover letter using LLM...")
        # Mocking for MVP until actual keys are available
        first_name = profile.get('personal_info', {}).get('first_name', 'Applicant')
        return f"Dear Hiring Manager,\n\nBased on my extensive background and the requirements in the job description, I am thrilled to apply for this role.\n\nSincerely,\n{first_name}"
