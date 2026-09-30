"""Docket-only pipeline mode skips Calendar/Drafts steps entirely."""

from app.us_pto.jobs import UsPtoJob, run_pipeline


def _make_job() -> UsPtoJob:
    return UsPtoJob(job_id="test-job", name="Test")


def test_docket_only_mode_runs_only_step_1(monkeypatch):
    calls: list[str] = []

    def fake_fetch(job):
        calls.append("fetch")
        return {"status": "success", "message": "fetched"}

    def fake_calendar(*args, **kwargs):
        calls.append("calendar")
        return {"status": "success", "message": "calendar"}

    def fake_drafts(job):
        calls.append("drafts")
        return {"status": "success", "message": "drafts"}

    monkeypatch.setattr("app.us_pto.steps.fetch_email.run_fetch_for_ui", fake_fetch)
    monkeypatch.setattr("app.us_pto.steps.calendar_events.create_events_for_ui", fake_calendar)
    monkeypatch.setattr("app.us_pto.steps.email_drafts.create_drafts_for_ui", fake_drafts)

    result = run_pipeline(_make_job(), mode="docket_only")

    assert calls == ["fetch"]
    assert result["status"] == "success"
    assert [s["step_key"] for s in result["steps"]] == ["1"]


def test_complete_mode_runs_all_three_steps(monkeypatch):
    calls: list[str] = []

    def fake_fetch(job):
        calls.append("fetch")
        return {"status": "success", "message": "fetched"}

    def fake_calendar(*args, **kwargs):
        calls.append("calendar")
        return {"status": "success", "message": "calendar"}

    def fake_drafts(job):
        calls.append("drafts")
        return {"status": "success", "message": "drafts"}

    monkeypatch.setattr("app.us_pto.steps.fetch_email.run_fetch_for_ui", fake_fetch)
    monkeypatch.setattr("app.us_pto.steps.calendar_events.create_events_for_ui", fake_calendar)
    monkeypatch.setattr("app.us_pto.steps.email_drafts.create_drafts_for_ui", fake_drafts)

    result = run_pipeline(_make_job(), mode="complete")

    assert calls == ["fetch", "calendar", "drafts"]
    assert [s["step_key"] for s in result["steps"]] == ["1", "2", "3"]
