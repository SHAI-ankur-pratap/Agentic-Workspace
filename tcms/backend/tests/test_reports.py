import secrets
from datetime import datetime, timedelta


def _make_run(client, admin_token, project):
    headers = {"Authorization": f"Bearer {admin_token}"}
    pid = project["id"]
    tc = client.post(f"/api/projects/{pid}/testcases",
        json={"title": "TC", "steps": "1. step", "expected_result": "done"},
        headers=headers).json()
    run = client.post(f"/api/projects/{pid}/runs", json={"name": "Run"},
                      headers=headers).json()
    return run["run"]


def test_html_report(client, admin_token, project):
    run = _make_run(client, admin_token, project)
    resp = client.get(
        f"/api/projects/{project['id']}/runs/{run['id']}/report.html",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert run["name"] in resp.text


def test_pdf_report_fallback_on_weasyprint_unavailable(client, admin_token, project, mocker):
    mocker.patch("pdf.render_pdf", return_value=None)
    run = _make_run(client, admin_token, project)
    resp = client.get(
        f"/api/projects/{project['id']}/runs/{run['id']}/report.pdf",
        headers={"Authorization": f"Bearer {admin_token}"})
    # When WeasyPrint fails, should fall back gracefully (503 or HTML fallback)
    assert resp.status_code in (200, 503)


def test_pdf_report_success(client, admin_token, project, mocker):
    mocker.patch("pdf.render_pdf", return_value=b"%PDF-MOCK")
    run = _make_run(client, admin_token, project)
    resp = client.get(
        f"/api/projects/{project['id']}/runs/{run['id']}/report.pdf",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_create_share_link(client, admin_token, project):
    run = _make_run(client, admin_token, project)
    resp = client.post(
        f"/api/projects/{project['id']}/runs/{run['id']}/share",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert "url" in data
    assert "expires_at" in data


def test_public_report_valid_token(client, admin_token, project, db):
    from models import ExecutionRun, ShareToken
    run = _make_run(client, admin_token, project)

    # Create a valid share token
    token = secrets.token_urlsafe(32)
    st = ShareToken(run_id=run["id"], token=token,
                    expires_at=datetime.utcnow() + timedelta(days=30))
    db.add(st)
    db.commit()

    resp = client.get(f"/reports/{token}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_public_report_expired_token(client, db):
    from models import ExecutionRun, Project, ShareToken, User
    # Need a user and project to attach run to
    u = db.query(User).first()
    if not u:
        from auth import hash_password
        u = User(email="e@e.com", password_hash=hash_password("x"), full_name="E", role="admin")
        db.add(u)
        db.flush()
    p = Project(name="P", created_by=u.id)
    db.add(p)
    db.flush()
    run = ExecutionRun(project_id=p.id, name="Run", status="completed", created_by=u.id)
    db.add(run)
    db.flush()
    token = secrets.token_urlsafe(32)
    st = ShareToken(run_id=run.id, token=token,
                    expires_at=datetime.utcnow() - timedelta(days=1))
    db.add(st)
    db.commit()

    resp = client.get(f"/reports/{token}")
    assert resp.status_code == 410


def test_public_report_unknown_token(client):
    resp = client.get("/reports/totally-fake-token-xyz")
    assert resp.status_code == 404
