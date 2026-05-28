import os
import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class DashboardClient:
    def __init__(self, base_url: str, token: str, worker_name: str = "Local Playwright Worker"):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.worker_name = worker_name
        self.headers = {
            "x-worker-token": self.token,
            "Content-Type": "application/json"
        }

    def get_state(self) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/api/public/agent-state"
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                print(f"❌ Dashboard authentication failed (401). Check WORKER_TOKEN.")
            else:
                print(f"⚠️ Failed to fetch agent state from dashboard: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Error connecting to dashboard GET {url}: {e}")
        return None

    def send_heartbeat(self, status: str = "running", platform: Optional[str] = None, 
                       log_msg: Optional[str] = None, log_level: str = "info", 
                       metadata: Optional[Dict[str, Any]] = None) -> bool:
        url = f"{self.base_url}/api/public/heartbeat"
        payload = {
            "worker_name": self.worker_name,
            "status": status,
        }
        if platform:
            payload["platform"] = platform
        if metadata:
            payload["metadata"] = metadata
            
        if log_msg:
            payload["log"] = {
                "level": log_level,
                "source": "worker",
                "message": log_msg[:2000]
            }
            if metadata:
                payload["log"]["metadata"] = metadata

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=15)
            if response.status_code == 200:
                return True
            else:
                print(f"⚠️ Heartbeat rejected by dashboard: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Error sending heartbeat to dashboard POST {url}: {e}")
        return False

    def update_application(self, job_id: str, status: str, platform: str, 
                           resume_id: Optional[str] = None, response_text: Optional[str] = None, 
                           screenshot_url: Optional[str] = None, error: Optional[str] = None) -> bool:
        url = f"{self.base_url}/api/public/application-update"
        
        # Map status to valid database schema enum if needed
        # Expected: queued, pending, submitted, interview, rejected, offer, withdrawn, error, needs_human
        db_status = status
        if status == "applied" or status == "submitted":
            db_status = "submitted"
        elif status == "failed":
            db_status = "error"
        elif status == "skipped" or status == "skipped_hard_stop" or status == "skipped_account_wall":
            db_status = "needs_human"
            
        # Map platform to valid database enum (linkedin, naukri, other)
        db_platform = platform.lower()
        if db_platform not in ["linkedin", "naukri"]:
            db_platform = "other"

        payload = {
            "job_id": job_id,
            "status": db_status,
            "platform": db_platform
        }
        
        if resume_id:
            payload["resume_id"] = resume_id
        if response_text:
            payload["response_text"] = response_text[:5000]
        if screenshot_url:
            payload["screenshot_url"] = screenshot_url[:1000]
        if error:
            payload["error"] = error[:2000]

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=15)
            if response.status_code == 200:
                print(f"✅ Dashboard updated application status to '{db_status}' for job {job_id}")
                return True
            else:
                print(f"⚠️ Failed to update application on dashboard: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Error sending application update to dashboard POST {url}: {e}")
        return False
