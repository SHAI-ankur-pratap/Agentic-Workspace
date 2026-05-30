def test_generate_test_cases(client, admin_token, project, mocker):
    mocker.patch("llm.generate_test_cases", return_value=[
        {"title": "TC 1", "steps": "1. step", "expected_result": "done", "priority": "P1"},
        {"title": "TC 2", "steps": "1. step", "expected_result": "done", "priority": "P2"},
        {"title": "TC 3", "steps": "1. step", "expected_result": "done", "priority": "P3"},
    ])
    resp = client.post("/api/ai/generate",
        json={"project_id": project["id"], "user_story": "As a user I want to log in", "count": 3},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["test_cases"]) == 3
    assert data["test_cases"][0]["title"] == "TC 1"


def test_generate_returns_503_on_llm_failure(client, admin_token, project, mocker):
    mocker.patch("llm.generate_test_cases", side_effect=Exception("LiteLLM timeout"))
    resp = client.post("/api/ai/generate",
        json={"project_id": project["id"], "user_story": "something", "count": 5},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 503


def test_criticize_test_case(client, admin_token, project, test_case, mocker):
    mocker.patch("llm.criticize_test_case", return_value=[
        {"type": "missing_edge_case", "description": "Missing empty input test", "rewrite": None},
        {"type": "ambiguous_step", "description": "Step 2 is vague", "rewrite": "2. Click the blue Sign In button"},
    ])
    resp = client.post("/api/ai/criticize",
        json={"test_case_id": test_case["id"]},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 2
    assert suggestions[0]["type"] == "missing_edge_case"


def test_criticize_returns_503_on_llm_failure(client, admin_token, project, test_case, mocker):
    mocker.patch("llm.criticize_test_case", side_effect=Exception("LiteLLM down"))
    resp = client.post("/api/ai/criticize",
        json={"test_case_id": test_case["id"]},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 503


def test_criticize_test_case_not_found(client, admin_token):
    resp = client.post("/api/ai/criticize",
        json={"test_case_id": "nonexistent-id"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 404


def test_generate_count_clamped(client, admin_token, project, mocker):
    mock = mocker.patch("llm.generate_test_cases", return_value=[])
    client.post("/api/ai/generate",
        json={"project_id": project["id"], "user_story": "test", "count": 999},
        headers={"Authorization": f"Bearer {admin_token}"})
    _, kwargs = mock.call_args
    assert kwargs.get("count", mock.call_args[0][1] if mock.call_args[0] else 999) <= 20
