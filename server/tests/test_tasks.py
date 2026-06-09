import time

from fastapi.testclient import TestClient


def task_request(instruction: str, worker: str = "auto", test_profile: str = "default") -> dict:
    return {
        "message": {
            "role": "ROLE_USER",
            "parts": [{"text": instruction}],
        },
        "metadata": {
            "patchrelay": {
                "worker": worker,
                "testProfile": test_profile,
            }
        },
    }


def wait_for_status(
    client: TestClient,
    headers: dict[str, str],
    task_id: str,
    *statuses: str,
) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in statuses:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Task {task_id} did not reach {statuses}")


def test_submit_and_complete_fake_task(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/message:send", json=task_request("make a fake change"), headers=auth_headers)

    assert response.status_code == 200
    task_id = response.json()["taskId"]

    payload = wait_for_status(client, auth_headers, task_id, "completed")
    assert payload["artifacts"]["patchrelay.summary"]["content"]["changedFiles"] == ["fake-change.txt"]
    assert "patchrelay.diff" in payload["artifacts"]
    assert "patchrelay.tests" in payload["artifacts"]
    assert "patchrelay.log" in payload["artifacts"]


def test_submit_rejects_empty_instruction(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/message:send", json=task_request("   "), headers=auth_headers)

    assert response.status_code == 400


def test_submit_rejects_unknown_test_profile(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/message:send",
        json=task_request("run with missing profile", test_profile="missing"),
        headers=auth_headers,
    )

    assert response.status_code == 400


def test_fake_worker_can_fail(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/message:send", json=task_request("please fail"), headers=auth_headers)
    task_id = response.json()["taskId"]

    payload = wait_for_status(client, auth_headers, task_id, "failed")

    assert payload["error"] == "Fake worker failure requested by instruction."


def test_can_cancel_queued_task(client: TestClient, auth_headers: dict[str, str]) -> None:
    first = client.post("/message:send", json=task_request("hold queue"), headers=auth_headers)
    second = client.post("/message:send", json=task_request("cancel me"), headers=auth_headers)
    second_id = second.json()["taskId"]

    cancel = client.post(f"/tasks/{second_id}:cancel", headers=auth_headers)

    assert first.status_code == 200
    assert cancel.status_code == 200
    assert cancel.json()["status"] in {"canceled", "working", "completed"}


def test_list_tasks(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post("/message:send", json=task_request("list me"), headers=auth_headers)

    response = client.get("/tasks", headers=auth_headers)

    assert response.status_code == 200
    assert len(response.json()["tasks"]) == 1


def test_stream_message_returns_sse_events(client: TestClient, auth_headers: dict[str, str]) -> None:
    with client.stream(
        "POST",
        "/message:stream",
        json=task_request("stream me"),
        headers=auth_headers,
    ) as response:
        body = response.read().decode("utf-8")

    assert response.status_code == 200
    assert "event: task" in body
    assert "event: done" in body
    assert "completed" in body
