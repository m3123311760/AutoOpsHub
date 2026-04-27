import os
from pathlib import Path

TEST_HOME = Path(__file__).parent / ".tmp-home-tests"
TEST_HOME.mkdir(parents=True, exist_ok=True)
os.environ["AUTOOPSHUB_HOME"] = str(TEST_HOME)

from main import (
    JobRecord,
    LogLevel,
    LogRecord,
    ManifestVariable,
    ManifestVariableDirection,
    RunbookRecord,
    RunbookType,
    TaskRecord,
    TaskSource,
    TaskStatus,
    _ensure_workpiece_structure,
    _load_job,
    _load_manifest,
    _load_runbook,
    _load_task,
    _save_job,
    _save_log_record,
    _save_manifest,
    _save_runbook,
    _save_task,
)


def test_entity_storage_roundtrip():
    _ensure_workpiece_structure("demo")

    runbook = RunbookRecord(
        name="rb1",
        type=RunbookType.SCRIPT,
        description="desc",
        content="echo {{ name }}",
        runtime="python",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    _save_runbook("demo", runbook)
    loaded_runbook = _load_runbook("demo", "rb1")
    assert loaded_runbook.name == "rb1"
    assert loaded_runbook.runtime == "python"

    manifest = [
        ManifestVariable(
            name="name",
            display_name="name",
            direction=ManifestVariableDirection.INPUT,
            required=True,
        )
    ]
    _save_manifest("demo", "rb1", manifest)
    loaded_manifest = _load_manifest("demo", "rb1")
    assert loaded_manifest[0].name == "name"
    assert loaded_manifest[0].required is True

    task = TaskRecord(
        task_id="t1",
        source=TaskSource.MANUAL,
        runbook_name="rb1",
        variables={"name": "alice"},
        status=TaskStatus.PENDING,
        error_summary="",
        schedule={},
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    _save_task("demo", task)
    loaded_task = _load_task("demo", "t1")
    assert loaded_task.runbook_name == "rb1"
    assert loaded_task.variables["name"] == "alice"

    job = JobRecord(
        job_name="nightly",
        description="nightly run",
        cron="0 0 * * *",
        runbook_name="rb1",
        variables={"name": "bob"},
        enabled=True,
        next_run_at=None,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    _save_job("demo", job)
    loaded_job = _load_job("demo", "nightly")
    assert loaded_job.cron == "0 0 * * *"


def test_log_record_append_and_seq_growth():
    _ensure_workpiece_structure("demo2")
    seq1 = _save_log_record(
        "demo2",
        "task-a",
        LogRecord(
            task_id="task-a",
            log_seq=0,
            ts="2026-01-01T00:00:00+00:00",
            level=LogLevel.INFO,
            message="start",
        ),
    )
    seq2 = _save_log_record(
        "demo2",
        "task-a",
        LogRecord(
            task_id="task-a",
            log_seq=0,
            ts="2026-01-01T00:00:01+00:00",
            level=LogLevel.ERROR,
            message="fail",
        ),
    )
    assert seq1 == 1
    assert seq2 == 2
