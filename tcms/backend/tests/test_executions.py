def test_create_run_includes_all_active_cases(client, admin_token, project, test_case):
    resp = client.post(f"/api/projects/{project['id']}/runs",
        json={"name": "Sprint 1"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["run"]["name"] == "Sprint 1"
    assert data["total"] == 1  # One test case in fixture
    assert data["pending"] == 1


def test_create_run_with_specific_test_case_ids(client, admin_token, project, test_case):
    resp = client.post(f"/api/projects/{project['id']}/runs",
        json={"name": "Targeted Run", "test_case_ids": [test_case["id"]]},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    assert resp.json()["total"] == 1


def test_mark_result_pass(client, admin_token, project, test_case):
    run = client.post(f"/api/projects/{project['id']}/runs",
        json={"name": "Run"},
        headers={"Authorization": f"Bearer {admin_token}"}).json()

    run_id = run["run"]["id"]
    # Get the result ID
    detail = client.get(f"/api/projects/{project['id']}/runs/{run_id}",
                        headers={"Authorization": f"Bearer {admin_token}"}).json()
    result_id = detail["results"][0]["id"]

    resp = client.put(f"/api/projects/{project['id']}/runs/{run_id}/results/{result_id}",
        json={"status": "pass", "actual_result": "Dashboard loaded"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pass"


def test_mark_result_fail(client, admin_token, project, test_case):
    run = client.post(f"/api/projects/{project['id']}/runs",
        json={"name": "Run"},
        headers={"Authorization": f"Bearer {admin_token}"}).json()
    run_id = run["run"]["id"]
    detail = client.get(f"/api/projects/{project['id']}/runs/{run_id}",
                        headers={"Authorization": f"Bearer {admin_token}"}).json()
    result_id = detail["results"][0]["id"]

    resp = client.put(f"/api/projects/{project['id']}/runs/{run_id}/results/{result_id}",
        json={"status": "fail", "notes": "Login button unresponsive"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "fail"


def test_coverage_pct_calculation(client, admin_token, project):
    headers = {"Authorization": f"Bearer {admin_token}"}
    pid = project["id"]
    # Add 4 test cases
    tcs = []
    for i in range(4):
        tc = client.post(f"/api/projects/{pid}/testcases",
            json={"title": f"TC {i}", "steps": "1. step", "expected_result": "done"},
            headers=headers).json()
        tcs.append(tc)

    run = client.post(f"/api/projects/{pid}/runs", json={"name": "Run"},
                      headers=headers).json()
    run_id = run["run"]["id"]
    detail = client.get(f"/api/projects/{pid}/runs/{run_id}", headers=headers).json()

    # Mark 3 pass, 1 fail
    for i, result in enumerate(detail["results"][:3]):
        client.put(f"/api/projects/{pid}/runs/{run_id}/results/{result['id']}",
                   json={"status": "pass"}, headers=headers)
    client.put(f"/api/projects/{pid}/runs/{run_id}/results/{detail['results'][3]['id']}",
               json={"status": "fail"}, headers=headers)

    # Check summary
    summary = client.get(f"/api/projects/{pid}/runs/{run_id}", headers=headers).json()
    assert summary["passed"] == 3
    assert summary["failed"] == 1
    assert summary["coverage_pct"] == 75.0  # 3/4 passed


def test_complete_run(client, admin_token, project, test_case):
    headers = {"Authorization": f"Bearer {admin_token}"}
    pid = project["id"]
    run = client.post(f"/api/projects/{pid}/runs", json={"name": "Run"},
                      headers=headers).json()
    run_id = run["run"]["id"]

    resp = client.put(f"/api/projects/{pid}/runs/{run_id}/complete", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["run"]["status"] == "completed"


def test_list_runs(client, admin_token, project, test_case):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post(f"/api/projects/{project['id']}/runs", json={"name": "R1"}, headers=headers)
    client.post(f"/api/projects/{project['id']}/runs", json={"name": "R2"}, headers=headers)
    resp = client.get(f"/api/projects/{project['id']}/runs", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2
