import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from patchrelay.app import create_app
from patchrelay.config import (
    LimitsConfig,
    RepoConfig,
    ServerConfig,
    Settings,
    TestProfile as ConfigTestProfile,
    WorkerConfig,
)
from helpers import init_git_repo


def task_request(
    instruction: str,
    worker: str = "auto",
    test_profile: str = "default",
    parent_task_id: str | None = None,
    worktree_strategy: str | None = None,
) -> dict:
    patchrelay: dict = {
        "worker": worker,
        "testProfile": test_profile,
    }
    if parent_task_id is not None:
        patchrelay["parentTaskId"] = parent_task_id
    if worktree_strategy is not None:
        patchrelay["worktreeStrategy"] = worktree_strategy
    return {
        "message": {
            "role": "ROLE_USER",
            "parts": [{"text": instruction}],
        },
        "metadata": {"patchrelay": patchrelay},
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


def test_child_task_records_parent_and_depth(client: TestClient, auth_headers: dict[str, str]) -> None:
    parent = client.post("/message:send", json=task_request("parent work"), headers=auth_headers)
    parent_id = parent.json()["taskId"]
    wait_for_status(client, auth_headers, parent_id, "completed")

    child = client.post(
        "/message:send",
        json=task_request("child work", parent_task_id=parent_id),
        headers=auth_headers,
    )
    child_payload = wait_for_status(client, auth_headers, child.json()["taskId"], "completed")

    assert child_payload["parentTaskId"] == parent_id
    assert child_payload["handoffDepth"] == 1
    assert child_payload["worktreeStrategy"] == "shared"


def test_submit_rejects_unknown_parent_task(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/message:send",
        json=task_request("orphan", parent_task_id="does-not-exist"),
        headers=auth_headers,
    )

    assert response.status_code == 400


def test_shared_child_reuses_parent_worktree(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        parent = local_client.post("/message:send", json=task_request("parent"), headers=headers)
        parent_id = parent.json()["taskId"]
        parent_payload = wait_for_status(local_client, headers, parent_id, "completed")

        child = local_client.post(
            "/message:send",
            json=task_request("child", parent_task_id=parent_id, worktree_strategy="shared"),
            headers=headers,
        )
        child_payload = wait_for_status(local_client, headers, child.json()["taskId"], "completed")

    # Shared handoff continues on the parent's branch/worktree so edits accumulate.
    assert child_payload["branch"] == parent_payload["branch"]
    assert child_payload["worktreePath"] == parent_payload["worktreePath"]


def test_fresh_child_gets_new_worktree(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        parent = local_client.post("/message:send", json=task_request("parent"), headers=headers)
        parent_id = parent.json()["taskId"]
        parent_payload = wait_for_status(local_client, headers, parent_id, "completed")

        child = local_client.post(
            "/message:send",
            json=task_request("child", parent_task_id=parent_id, worktree_strategy="fresh"),
            headers=headers,
        )
        child_payload = wait_for_status(local_client, headers, child.json()["taskId"], "completed")

    assert child_payload["branch"] != parent_payload["branch"]
    assert child_payload["worktreePath"] != parent_payload["worktreePath"]


def _write_handoff_worker(tmp_path: Path, *, target: str, marker_prefix: str) -> Path:
    """A python worker that leaves a handoff sentinel pointing at ``target``.

    It also drops a per-depth marker file so a test can count how many hops ran
    on the (shared) worktree.
    """
    script = tmp_path / f"handoff_worker_{marker_prefix}.py"
    script.write_text(
        "import json, os, pathlib\n"
        "root = pathlib.Path.cwd()\n"
        "depth = os.environ.get('PATCHRELAY_HANDOFF_DEPTH', '0')\n"
        f"(root / f'{marker_prefix}-ran-' + depth + '.txt').write_text('ran', encoding='utf-8')\n"
        "sentinel_dir = root / '.patchrelay'\n"
        "sentinel_dir.mkdir(exist_ok=True)\n"
        "(sentinel_dir / 'handoff.json').write_text(\n"
        f"    json.dumps({{'worker': {target!r}, 'instruction': 'continue the work please'}}),\n"
        "    encoding='utf-8',\n"
        ")\n"
        "print('handoff written')\n",
        encoding="utf-8",
    )
    return script


def _write_handoff_worker(tmp_path: Path, *, target: str, marker_prefix: str) -> Path:
    """Create a fake worker that edits the worktree then requests a handoff.

    It writes a depth-keyed marker file (so the accumulated diff has content and
    each hop is distinguishable) and drops a ``.patchrelay/handoff.json`` sentinel
    pointing at ``target``. The worker's cwd is the task's worktree.
    """
    script = tmp_path / f"handoff_worker_{marker_prefix}.py"
    script.write_text(
        "import json, os, pathlib\n"
        "depth = os.environ.get('PATCHRELAY_HANDOFF_DEPTH', '0')\n"
        f"pathlib.Path(f'{marker_prefix}-hop-{{depth}}.txt').write_text('hop ' + depth, encoding='utf-8')\n"
        "sentinel_dir = pathlib.Path('.patchrelay')\n"
        "sentinel_dir.mkdir(exist_ok=True)\n"
        "(sentinel_dir / 'handoff.json').write_text(\n"
        f"    json.dumps({{'worker': {target!r}, 'instruction': 'continue the chain'}}),\n"
        "    encoding='utf-8',\n"
        ")\n"
        "print('handoff worker done at depth', depth)\n",
        encoding="utf-8",
    )
    return script


def _find_child(client: TestClient, headers: dict[str, str], parent_id: str) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        tasks = client.get("/tasks", headers=headers).json()["tasks"]
        for task in tasks:
            if task.get("parentTaskId") == parent_id:
                return task
        time.sleep(0.02)
    raise AssertionError(f"No child task appeared for parent {parent_id}")


def test_worker_sentinel_triggers_handoff_to_next_worker(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    worker = _write_handoff_worker(tmp_path, target="fake", marker_prefix="codex")
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        worker=WorkerConfig(codex_command=[sys.executable, str(worker)]),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        parent = local_client.post(
            "/message:send", json=task_request("scaffold it", worker="codex"), headers=headers
        )
        parent_id = parent.json()["taskId"]
        parent_payload = wait_for_status(local_client, headers, parent_id, "handed_off")

        child = _find_child(local_client, headers, parent_id)
        child_payload = wait_for_status(local_client, headers, child["taskId"], "completed")

    # Parent completed its hop by handing off; the child continued the chain.
    assert parent_payload["status"] == "handed_off"
    assert child_payload["worker"] == "fake"
    assert child_payload["parentTaskId"] == parent_id
    assert child_payload["handoffDepth"] == 1
    # Shared worktree: the child ran where the parent left off (same branch).
    assert child_payload["branch"] == parent_payload["branch"]
    assert child_payload["worktreePath"] == parent_payload["worktreePath"]
    # The consumed sentinel must not leak into the parent's diff.
    assert ".patchrelay/handoff.json" not in parent_payload["artifacts"]["patchrelay.diff"]["content"]


def test_handoff_depth_guard_stops_pingpong(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    # A worker that always hands back to itself would loop forever without a guard.
    worker = _write_handoff_worker(tmp_path, target="codex", marker_prefix="pingpong")
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        worker=WorkerConfig(codex_command=[sys.executable, str(worker)]),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
        limits=LimitsConfig(max_handoff_depth=2),
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        root = local_client.post(
            "/message:send", json=task_request("start pingpong", worker="codex"), headers=headers
        )
        root_id = root.json()["taskId"]
        wait_for_status(local_client, headers, root_id, "handed_off")

        # Follow the chain until a task completes instead of handing off.
        deadline = time.monotonic() + 15
        terminal = None
        while time.monotonic() < deadline:
            tasks = local_client.get("/tasks", headers=headers).json()["tasks"]
            terminal = next((t for t in tasks if t["status"] == "completed"), None)
            if terminal is not None:
                break
            time.sleep(0.05)
        assert terminal is not None, "chain never terminated"
        all_tasks = local_client.get("/tasks", headers=headers).json()["tasks"]

    # Depth is bounded: no task exceeds the configured max, and the deepest one
    # completed normally rather than handing off again.
    depths = [t["handoffDepth"] for t in all_tasks]
    assert max(depths) == 2
    assert terminal["handoffDepth"] == 2


def test_build_worker_instruction_injects_protocol_when_enabled() -> None:
    from patchrelay.tasks import build_worker_instruction

    result = build_worker_instruction("do the work", enabled=True, depth=0, max_depth=4)

    assert "do the work" in result
    assert ".patchrelay/handoff.json" in result
    assert "budget remaining: 4 hop(s)" in result


def test_build_worker_instruction_omits_protocol_when_disabled() -> None:
    from patchrelay.tasks import build_worker_instruction

    result = build_worker_instruction("do the work", enabled=False, depth=0, max_depth=4)

    assert result == "do the work"


def test_build_worker_instruction_omits_protocol_at_max_depth() -> None:
    from patchrelay.tasks import build_worker_instruction

    # The last worker in the chain has no budget to delegate; it just finishes.
    result = build_worker_instruction("finish it", enabled=True, depth=4, max_depth=4)

    assert result == "finish it"


def test_process_worker_receives_staged_brief_file_not_raw_argv(tmp_path: Path) -> None:
    # Real workers run through a Windows .CMD shim that truncates argv at the
    # first newline. So the multi-line brief must be staged to a file and the
    # worker handed only a short pointer. This worker records both what it got
    # on argv and what the staged file contained.
    repo = init_git_repo(tmp_path / "repo")
    argv_dump = tmp_path / "argv.txt"
    brief_dump = tmp_path / "brief.txt"
    worker = tmp_path / "recording_worker.py"
    worker.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path({str(argv_dump)!r}).write_text(' '.join(sys.argv[1:]), encoding='utf-8')\n"
        "brief = pathlib.Path('.patchrelay/task.md')\n"
        f"pathlib.Path({str(brief_dump)!r}).write_text(\n"
        "    brief.read_text(encoding='utf-8') if brief.exists() else '<<MISSING>>',\n"
        "    encoding='utf-8',\n"
        ")\n"
        "print('recorded')\n",
        encoding="utf-8",
    )
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        worker=WorkerConfig(codex_command=[sys.executable, str(worker)], enable_handoff=True),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        response = local_client.post(
            "/message:send", json=task_request("implement the feature", worker="codex"), headers=headers
        )
        task_id = response.json()["taskId"]
        payload = wait_for_status(local_client, headers, task_id, "completed")

    argv_received = argv_dump.read_text(encoding="utf-8")
    staged_brief = brief_dump.read_text(encoding="utf-8")
    # The worker got a short single-line pointer, not the multi-line brief.
    assert "task.md" in argv_received
    assert "\n" not in argv_received
    # The staged file held the real instruction plus the handoff protocol.
    assert "implement the feature" in staged_brief
    assert "handoff protocol" in staged_brief.lower()
    # The staged file was cleaned up and never leaked into the diff.
    assert ".patchrelay/task.md" not in payload["artifacts"]["patchrelay.diff"]["content"]


def test_timed_out_worker_with_changes_preserves_diff(tmp_path: Path) -> None:
    repo = init_git_repo(tmp_path / "repo")
    # A worker that writes a file, then hangs past the worker timeout.
    worker = tmp_path / "slow_edit_worker.py"
    worker.write_text(
        "import pathlib, time\n"
        "pathlib.Path('slow.txt').write_text('partial work', encoding='utf-8')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    settings = Settings(
        server=ServerConfig(token="test-token"),
        repo=RepoConfig(path=repo, base_branch="main", state_dir=Path(".patchrelay-test")),
        worker=WorkerConfig(default="codex", codex_command=[sys.executable, str(worker), "exec"]),
        tests={"default": ConfigTestProfile(command=["python", "-c", "print('tests ok')"])},
        limits=LimitsConfig(worker_timeout_seconds=1),
    )
    headers = {"Authorization": "Bearer test-token"}

    with TestClient(create_app(settings)) as local_client:
        response = local_client.post("/message:send", json=task_request("slow edit", worker="codex"), headers=headers)
        task_id = response.json()["taskId"]
        payload = wait_for_status(local_client, headers, task_id, "timed_out")

    # The worker stalled, but its partial change is not thrown away.
    assert payload["status"] == "timed_out"
    assert payload["artifacts"]["patchrelay.summary"]["content"]["changedFiles"] == ["slow.txt"]
    assert "slow.txt" in payload["artifacts"]["patchrelay.diff"]["content"]
    assert "diff preserved" in payload["error"]


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
