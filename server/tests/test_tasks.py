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
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in statuses:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Task {task_id} did not reach {statuses}")


def wait_for_phase(
    client: TestClient,
    headers: dict[str, str],
    task_id: str,
    *phases: str,
) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        if payload["phase"] in phases:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Task {task_id} did not reach phase {phases}")


def wait_for_artifact(
    client: TestClient,
    headers: dict[str, str],
    task_id: str,
    artifact_name: str,
) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        if artifact_name in payload["artifacts"]:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Task {task_id} did not include artifact {artifact_name}")


def test_submit_and_complete_fake_task(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/message:send", json=task_request("make a fake change"), headers=auth_headers)

    assert response.status_code == 200
    task_id = response.json()["taskId"]

    payload = wait_for_status(client, auth_headers, task_id, "completed")
    assert payload["artifacts"]["patchrelay.summary"]["content"]["changedFiles"] == ["fake-change.txt"]
    assert "patchrelay.diff" in payload["artifacts"]
    assert "patchrelay.tests" in payload["artifacts"]
    assert "patchrelay.log" in payload["artifacts"]
    assert "patchrelay.worker" in payload["artifacts"]
    assert payload["branch"].startswith("patchrelay/")
    assert payload["worktreePath"]
    phases = [event["phase"] for event in payload["events"]]
    assert "queued" in phases
    assert "workspace" in phases
    assert "worker" in phases
    assert payload["eventCount"] == len(payload["events"])
    assert payload["latestEvent"]["phase"] == "completed"


def test_task_events_endpoint_returns_timeline(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/message:send", json=task_request("record events"), headers=auth_headers)
    task_id = response.json()["taskId"]
    wait_for_status(client, auth_headers, task_id, "completed")

    events = client.get(f"/tasks/{task_id}/events", headers=auth_headers)
    payload = events.json()

    assert events.status_code == 200
    assert payload["taskId"] == task_id
    assert payload["events"][0]["sequence"] == 1
    assert payload["events"][0]["phase"] == "queued"
    assert any(event["phase"] == "artifacts" for event in payload["events"])
    assert payload["events"] == sorted(payload["events"], key=lambda event: event["sequence"])


def test_task_events_endpoint_supports_after_cursor(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/message:send", json=task_request("cursor events"), headers=auth_headers)
    task_id = response.json()["taskId"]
    wait_for_status(client, auth_headers, task_id, "completed")

    all_events = client.get(f"/tasks/{task_id}/events", headers=auth_headers).json()["events"]
    filtered = client.get(f"/tasks/{task_id}/events?after=1", headers=auth_headers).json()["events"]

    assert len(filtered) == len(all_events) - 1
    assert all(event["sequence"] > 1 for event in filtered)


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

    assert payload["error"] == "Worker 'fake' failed with exit code 1."
    assert payload["artifacts"]["patchrelay.tests"]["content"]["profile"] == "skipped"


def test_can_cancel_queued_task(client: TestClient, auth_headers: dict[str, str]) -> None:
    first = client.post("/message:send", json=task_request("hold queue"), headers=auth_headers)
    second = client.post("/message:send", json=task_request("cancel me"), headers=auth_headers)
    second_id = second.json()["taskId"]

    cancel = client.post(f"/tasks/{second_id}:cancel", headers=auth_headers)

    assert first.status_code == 200
    assert cancel.status_code == 200
    assert cancel.json()["status"] in {"canceled", "working", "completed"}


def test_can_cancel_working_task(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post("/message:send", json=task_request("sleep before finishing"), headers=auth_headers)
    task_id = response.json()["taskId"]
    wait_for_status(client, auth_headers, task_id, "working")

    cancel = client.post(f"/tasks/{task_id}:cancel", headers=auth_headers)
    wait_for_status(client, auth_headers, task_id, "canceled")
    payload = wait_for_artifact(client, auth_headers, task_id, "patchrelay.worker")

    assert cancel.status_code == 200
    assert payload["status"] == "canceled"
    assert payload["artifacts"]["patchrelay.worker"]["content"]["exitCode"] == 130


def test_cancelled_task_does_not_complete_after_tests_finish(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    marker = tmp_path / "test-marker.txt"
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        tests={
            "default": ConfigTestProfile(
                command=[
                    "python",
                    "-c",
                    f"from pathlib import Path; import time; time.sleep(2); Path({str(marker)!r}).write_text('ran', encoding='utf-8')",
                ]
            )
        },
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        response = local_client.post("/message:send", json=task_request("sleep before finishing"), headers=headers)
        task_id = response.json()["taskId"]
        wait_for_phase(local_client, headers, task_id, "tests")
        cancel = local_client.post(f"/tasks/{task_id}:cancel", headers=headers)
        payload = wait_for_status(local_client, headers, task_id, "canceled")

    assert cancel.status_code == 200
    assert payload["status"] == "canceled"
    assert payload["phase"] == "canceled"
    assert payload["artifacts"]["patchrelay.tests"]["content"]["exitCode"] == 130
    assert not marker.exists()


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
    assert "event: event" in body
    assert "event: done" in body
    assert "Task queued." in body
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


def test_completed_tasks_are_restored_from_sqlite(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        response = local_client.post("/message:send", json=task_request("persist me"), headers=headers)
        task_id = response.json()["taskId"]
        wait_for_status(local_client, headers, task_id, "completed")

    with TestClient(create_app(settings)) as restarted_client:
        restored = restarted_client.get(f"/tasks/{task_id}", headers=headers)

    payload = restored.json()
    assert restored.status_code == 200
    assert payload["status"] == "completed"
    assert payload["artifacts"]["patchrelay.summary"]["content"]["changedFiles"] == ["fake-change.txt"]
    assert any(event["phase"] == "queued" for event in payload["events"])


def test_incomplete_tasks_are_marked_failed_after_restart(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        response = local_client.post("/message:send", json=task_request("sleep before restart"), headers=headers)
        task_id = response.json()["taskId"]
        wait_for_status(local_client, headers, task_id, "working")

    with TestClient(create_app(settings)) as restarted_client:
        restored = restarted_client.get(f"/tasks/{task_id}", headers=headers)

    payload = restored.json()
    assert restored.status_code == 200
    assert payload["status"] == "failed"
    assert payload["error"] == "Task was interrupted by PatchRelay restart."
    assert payload["events"][-1]["severity"] == "error"
