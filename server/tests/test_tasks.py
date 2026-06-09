import time
from pathlib import Path

from fastapi.testclient import TestClient

from patchrelay.app import create_app
from patchrelay.config import LimitsConfig, RepoConfig, ServerConfig, Settings, TestProfile as ConfigTestProfile
from helpers import init_git_repo


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
    assert payload["branch"].startswith("patchrelay/")
    assert payload["worktreePath"]


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


def test_task_uses_git_worktree_and_real_diff(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        response = local_client.post("/message:send", json=task_request("write diff"), headers=headers)
        task_id = response.json()["taskId"]
        payload = wait_for_status(local_client, headers, task_id, "completed")

    assert payload["branch"].startswith("patchrelay/")
    assert Path(payload["worktreePath"]).exists()
    assert payload["artifacts"]["patchrelay.summary"]["content"]["changedFiles"] == ["fake-change.txt"]
    assert "fake-change.txt" in payload["artifacts"]["patchrelay.diff"]["content"]
    assert payload["artifacts"]["patchrelay.tests"]["content"]["status"] == "passed"


def test_task_fails_when_test_profile_fails(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        tests={"default": ConfigTestProfile(command=["python", "-c", "import sys; sys.exit(7)"])},
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        response = local_client.post("/message:send", json=task_request("write diff"), headers=headers)
        task_id = response.json()["taskId"]
        payload = wait_for_status(local_client, headers, task_id, "failed")

    assert payload["artifacts"]["patchrelay.tests"]["content"]["exitCode"] == 7
    assert "failed with exit code 7" in payload["error"]
