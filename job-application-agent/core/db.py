import json
import os
import hashlib

class JobDatabase:
    def __init__(self, db_file="applied_jobs.json"):
        self.db_file = db_file
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(self.db_file, "w") as f:
            json.dump(self.data, f, indent=4)

    def generate_job_id(self, company_name, job_title):
        """Creates a deterministic hash based on company and title to serve as a unique ID."""
        raw_id = f"{company_name.lower().strip()}_{job_title.lower().strip()}"
        return hashlib.md5(raw_id.encode()).hexdigest()

    def is_processed(self, job_id):
        """Check if job has already been processed (applied, skipped, or failed)."""
        return job_id in self.data

    def mark_processed(self, job_id, platform, status, title="", company=""):
        """Record the job to prevent future duplicates across daemon runs."""
        self.data[job_id] = {
            "platform": platform,
            "status": status,
            "title": title,
            "company": company
        }
        self._save()
