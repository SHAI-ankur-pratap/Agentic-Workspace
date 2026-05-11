import json
import os
import hashlib
from datetime import datetime, timezone


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
        raw_id = f"{company_name.lower().strip()}_{job_title.lower().strip()}"
        return hashlib.md5(raw_id.encode()).hexdigest()

    def is_processed(self, job_id):
        return job_id in self.data

    def mark_processed(self, job_id, platform, status, title="", company="", url="", score=None):
        existing_pinned = self.data.get(job_id, {}).get("pinned", False)
        self.data[job_id] = {
            "platform": platform,
            "status": status,
            "title": title,
            "company": company,
            "url": url,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "score": score,
            "pinned": existing_pinned,
        }
        self._save()

    def get_all(self):
        result = {}
        for job_id, job in self.data.items():
            result[job_id] = {
                "platform": job.get("platform", ""),
                "status": job.get("status", ""),
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
                "applied_at": job.get("applied_at", ""),
                "score": job.get("score"),
                "pinned": job.get("pinned", False),
            }
        return result

    def toggle_pin(self, job_id, pinned: bool) -> bool:
        if job_id not in self.data:
            return False
        self.data[job_id]["pinned"] = pinned
        self._save()
        return True
