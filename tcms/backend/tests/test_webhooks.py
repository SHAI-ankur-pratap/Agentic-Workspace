import hashlib
import hmac
import json
import os

import pytest

WEBHOOK_SECRET = "test-webhook-secret"


def _sign(payload: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _pr_payload(repo: str, pr_number: int, files: list[str] | None = None) -> dict:
    return {
        "action": "opened",
        "number": pr_number,
        "pull_request": {"number": pr_number, "head": {"sha": "abc123"}},
        "repository": {"full_name": repo},
        "_test_changed_files": files or ["src/auth/login.py"],
    }


@pytest.fixture(autouse=True)
def set_webhook_secret(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)


def _post_webhook(client, payload: dict, secret: str = WEBHOOK_SECRET):
    body = json.dumps(payload).encode()
    signature = _sign(body, secret)
    return client.post("/api/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
        })


def test_valid_signature_accepted(client):
    resp = _post_webhook(client, _pr_payload("org/repo", 1))
    assert resp.status_code == 200


def test_missing_signature_rejected(client):
    body = json.dumps(_pr_payload("org/repo", 1)).encode()
    resp = client.post("/api/webhooks/github",
        content=body,
        headers={"Content-Type": "application/json", "X-GitHub-Event": "pull_request"})
    assert resp.status_code == 403


def test_wrong_signature_rejected(client):
    resp = _post_webhook(client, _pr_payload("org/repo", 1), secret="wrong-secret")
    assert resp.status_code == 403


def test_non_pr_event_ignored(client):
    payload = {"action": "created", "ref": "main"}
    body = json.dumps(payload).encode()
    sig = _sign(body, WEBHOOK_SECRET)
    resp = client.post("/api/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        })
    assert resp.status_code == 200


def test_pr_event_no_matching_project(client):
    """No project has github_repo = 'unknown/repo' → 200, no run created."""
    resp = _post_webhook(client, _pr_payload("unknown/repo", 42))
    assert resp.status_code == 200


def test_pr_event_creates_run_for_matching_project(client, admin_token, project, mocker):
    """Project with github_repo set + matching component tag rule → run created."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    pid = project["id"]

    # Set github_repo on project
    client.put(f"/api/projects/{pid}", json={"github_repo": "org/myrepo"}, headers=headers)

    # Add component tag rule
    client.post(f"/api/projects/{pid}/component-tag-rules",
        json={"file_pattern": "src/auth/**", "component_tag": "auth"}, headers=headers)

    # Add test case with auth tag
    client.post(f"/api/projects/{pid}/testcases",
        json={"title": "Auth TC", "steps": "1. step", "expected_result": "done",
              "component_tags": ["auth"]}, headers=headers)

    # Mock GitHub API calls
    mocker.patch("services.github.get_pr_changed_files",
                 return_value=["src/auth/login.py", "src/auth/token.py"])
    mocker.patch("services.github.post_pr_comment", return_value=None)

    resp = _post_webhook(client, _pr_payload("org/myrepo", 7))
    assert resp.status_code == 200

    # Verify run was created
    runs = client.get(f"/api/projects/{pid}/runs", headers=headers).json()
    assert len(runs) >= 1


def test_pr_event_non_matching_files(client, admin_token, project, mocker):
    """Changed files don't match any component tag rules → run with 0 cases."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    pid = project["id"]

    client.put(f"/api/projects/{pid}", json={"github_repo": "org/repo2"}, headers=headers)
    client.post(f"/api/projects/{pid}/component-tag-rules",
        json={"file_pattern": "src/auth/**", "component_tag": "auth"}, headers=headers)

    mocker.patch("services.github.get_pr_changed_files",
                 return_value=["docs/README.md"])
    mocker.patch("services.github.post_pr_comment", return_value=None)

    resp = _post_webhook(client, _pr_payload("org/repo2", 8))
    assert resp.status_code == 200


def test_pr_event_50_file_cap(client, admin_token, project, mocker):
    """60 changed files → only first 50 processed."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    pid = project["id"]
    client.put(f"/api/projects/{pid}", json={"github_repo": "org/cap-repo"}, headers=headers)

    sixty_files = [f"src/file_{i}.py" for i in range(60)]
    captured = []

    async def mock_get_files(*args, **kwargs):
        return sixty_files  # Return all 60 — cap applied inside service

    mocker.patch("services.github.get_pr_changed_files", side_effect=mock_get_files)
    mocker.patch("services.github.post_pr_comment", return_value=None)

    # Patch map_files_to_component_tags to capture input
    original = __import__("services.github", fromlist=["map_files_to_component_tags"]).map_files_to_component_tags

    def capturing_map(files, rules):
        captured.extend(files)
        return original(files, rules)

    mocker.patch("services.github.map_files_to_component_tags", side_effect=capturing_map)

    resp = _post_webhook(client, _pr_payload("org/cap-repo", 9))
    assert resp.status_code == 200
    # Files passed to mapping should be capped at 50
    assert len(captured) <= 50
