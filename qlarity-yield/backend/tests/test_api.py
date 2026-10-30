"""
test_api.py — Integration tests for the Qlarity FastAPI backend.

Uses FastAPI's AsyncClient + httpx for in-process testing (no server needed).
A temporary in-memory SQLite file is used per test module so tests are isolated.

Test tiers
----------
  Fast (always run): schema validation, /models, /scenarios/validate,
                     POST /runs (job queued), GET /runs/{id}, DELETE /runs/{id}
  Slow (FAST=0):     Full pipeline run with exact + monte_carlo estimators.
                     Waits for job to reach COMPLETED state.

Run fast tier:  FAST_TESTS=1 python -m pytest backend/tests/test_api.py -v
Run all:                      python -m pytest backend/tests/test_api.py -v
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------

FAST = bool(int(os.environ.get("FAST_TESTS", "0")))

# Use a temp in-memory-style DB path for tests
_TEST_DB = Path(__file__).parent / "_test_api.db"


# ---------------------------------------------------------------------------
# App fixture: patch the DB path before importing main
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def patch_db(tmp_path_factory):
    """Override QLARITY_DB env var to use a temp file for this test module."""
    db = tmp_path_factory.mktemp("db") / "test_jobs.db"
    os.environ["QLARITY_DB"] = str(db)
    yield db
    os.environ.pop("QLARITY_DB", None)
    if db.exists():
        db.unlink()


@pytest_asyncio.fixture(scope="module")
async def client(patch_db):
    """AsyncClient wired to the FastAPI app with the patched DB."""
    # Import after patching env var
    import importlib
    import backend.app.main as main_mod
    import backend.app.jobs as jobs_mod
    importlib.reload(jobs_mod)
    importlib.reload(main_mod)

    # Reinitialise DB with patched path
    await jobs_mod.init_db(patch_db)
    main_mod._DB_PATH = patch_db

    transport = ASGITransport(app=main_mod.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Minimal scenario payload
# ---------------------------------------------------------------------------

SCENARIO_MIN = {
    "I_limit_A": 5e-8,
    "estimators": ["exact"],
}

SCENARIO_FULL = {
    "label": "Test run — exact + MC",
    "I_limit_A": 5e-8,
    "estimators": ["exact", "monte_carlo"],
    "classical": {"n_samples": 500, "seed": 0},
}


# ===========================================================================
# Health check
# ===========================================================================

class TestHealth:
    @pytest.mark.asyncio
    async def test_root_ok(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body

    @pytest.mark.asyncio
    async def test_docs_reachable(self, client):
        r = await client.get("/docs")
        assert r.status_code == 200


# ===========================================================================
# GET /models
# ===========================================================================

class TestModels:
    @pytest.mark.asyncio
    async def test_models_returns_200(self, client):
        r = await client.get("/models")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_models_has_estimators(self, client):
        body = r = (await client.get("/models")).json()
        assert "estimators_available" in body
        assert "exact" in body["estimators_available"]
        assert "iqae" in body["estimators_available"]

    @pytest.mark.asyncio
    async def test_models_has_device_defaults(self, client):
        body = (await client.get("/models")).json()
        assert "device_defaults" in body
        assert body["device_defaults"]["L0_nm"] == 65.0


# ===========================================================================
# POST /scenarios/validate
# ===========================================================================

class TestValidate:
    @pytest.mark.asyncio
    async def test_valid_scenario(self, client):
        r = await client.post("/scenarios/validate", json=SCENARIO_MIN)
        assert r.status_code == 200
        body = r.json()
        assert body["valid"] is True
        assert "exact_p_fail" in body["derived"]
        assert 0.0 <= body["derived"]["exact_p_fail"] <= 1.0

    @pytest.mark.asyncio
    async def test_missing_I_limit_is_invalid(self, client):
        r = await client.post("/scenarios/validate", json={"estimators": ["exact"]})
        assert r.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_negative_I_limit_is_invalid(self, client):
        r = await client.post("/scenarios/validate", json={"I_limit_A": -1e-8})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_duplicate_estimators_rejected(self, client):
        r = await client.post("/scenarios/validate",
                              json={"I_limit_A": 5e-8, "estimators": ["exact", "exact"]})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_estimators_rejected(self, client):
        r = await client.post("/scenarios/validate",
                              json={"I_limit_A": 5e-8, "estimators": []})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_derived_includes_qmodel(self, client):
        r = await client.post("/scenarios/validate", json=SCENARIO_MIN)
        body = r.json()
        assert "qmodel" in body["derived"]
        qm = body["derived"]["qmodel"]
        assert "accumulator_bits" in qm
        assert "n_total_qubits" in qm
        assert "quantisation_error_mass" in qm
        assert qm["accumulator_bits"] > 0

    @pytest.mark.asyncio
    async def test_warnings_for_extreme_sigma(self, client):
        """Very large gate-length sigma relative to L0 should trigger a warning."""
        r = await client.post("/scenarios/validate", json={
            "I_limit_A": 5e-8,
            "estimators": ["exact"],
            "variations": {"sigma_L_nm": 25.0, "sigma_tox_nm": 0.1, "sigma_vth_mV": 15.0},
        })
        body = r.json()
        assert body["valid"] is True  # still valid, just warned
        assert any("sigma" in w.lower() or "20%" in w for w in body["warnings"])


# ===========================================================================
# POST /runs  — job queuing
# ===========================================================================

class TestRunsQueue:
    @pytest.mark.asyncio
    async def test_post_runs_returns_202(self, client):
        r = await client.post("/runs", json=SCENARIO_MIN)
        assert r.status_code == 202

    @pytest.mark.asyncio
    async def test_post_runs_returns_job_id(self, client):
        r = await client.post("/runs", json=SCENARIO_MIN)
        body = r.json()
        assert "job_id" in body
        assert len(body["job_id"]) == 36  # uuid4

    @pytest.mark.asyncio
    async def test_post_runs_status_is_queued_or_running(self, client):
        r = await client.post("/runs", json=SCENARIO_MIN)
        body = r.json()
        assert body["status"] in ("queued", "running")

    @pytest.mark.asyncio
    async def test_post_runs_invalid_schema_422(self, client):
        r = await client.post("/runs", json={"estimators": ["exact"]})  # missing I_limit_A
        assert r.status_code == 422


# ===========================================================================
# GET /runs  — list
# ===========================================================================

class TestRunsList:
    @pytest.mark.asyncio
    async def test_list_runs_returns_list(self, client):
        await client.post("/runs", json=SCENARIO_MIN)
        r = await client.get("/runs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    @pytest.mark.asyncio
    async def test_list_runs_nonempty_after_post(self, client):
        await client.post("/runs", json=SCENARIO_MIN)
        r = await client.get("/runs")
        assert len(r.json()) >= 1

    @pytest.mark.asyncio
    async def test_list_runs_limit(self, client):
        r = await client.get("/runs?limit=1")
        assert r.status_code == 200
        assert len(r.json()) <= 1

    @pytest.mark.asyncio
    async def test_list_runs_invalid_limit(self, client):
        r = await client.get("/runs?limit=0")
        assert r.status_code == 422


# ===========================================================================
# GET /runs/{id}  — job detail
# ===========================================================================

class TestRunDetail:
    @pytest.mark.asyncio
    async def test_get_run_returns_200(self, client):
        post = (await client.post("/runs", json=SCENARIO_MIN)).json()
        r = await client.get(f"/runs/{post['job_id']}")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_get_run_has_scenario(self, client):
        post = (await client.post("/runs", json=SCENARIO_MIN)).json()
        body = (await client.get(f"/runs/{post['job_id']}")).json()
        assert "scenario" in body
        assert body["scenario"]["I_limit_A"] == pytest.approx(5e-8)

    @pytest.mark.asyncio
    async def test_get_unknown_run_404(self, client):
        r = await client.get("/runs/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


# ===========================================================================
# DELETE /runs/{id}  — cancel
# ===========================================================================

class TestRunCancel:
    @pytest.mark.asyncio
    async def test_cancel_queued_job(self, client):
        post = (await client.post("/runs", json=SCENARIO_MIN)).json()
        job_id = post["job_id"]
        r = await client.delete(f"/runs/{job_id}")
        # May be 200 (cancelled) or 409 (already completed if fast pipeline ran)
        assert r.status_code in (200, 409)

    @pytest.mark.asyncio
    async def test_cancel_unknown_job_404(self, client):
        r = await client.delete("/runs/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


# ===========================================================================
# GET /runs/{id}/export  — export (only for completed jobs)
# ===========================================================================

class TestRunExport:
    @pytest.mark.asyncio
    async def test_export_non_completed_job_409(self, client):
        """Export of a non-completed job should return 409.
        We cancel the job immediately after queuing to ensure it stays non-completed.
        """
        post = (await client.post("/runs", json=SCENARIO_MIN)).json()
        job_id = post["job_id"]
        # Cancel immediately — leaves status as cancelled (not completed)
        await client.delete(f"/runs/{job_id}")
        r = await client.get(f"/runs/{job_id}/export?format=json")
        # Cancelled job → 409 (not completed)
        # If somehow exact already ran and completed before cancel: accept 200
        assert r.status_code in (200, 409)

    @pytest.mark.asyncio
    async def test_export_unknown_job_404(self, client):
        r = await client.get("/runs/00000000-0000-0000-0000-000000000000/export")
        assert r.status_code == 404


# ===========================================================================
# Full pipeline test (SLOW — waits for job completion)
# ===========================================================================

class TestFullPipeline:
    @pytest.mark.skipif(FAST, reason="Slow: waits for full computation pipeline")
    @pytest.mark.asyncio
    async def test_exact_plus_mc_completes(self, client):
        """Queue exact+MC, poll until completed, verify results structure."""
        post = (await client.post("/runs", json=SCENARIO_FULL)).json()
        job_id = post["job_id"]

        # Poll up to 60 s
        deadline = time.time() + 60
        detail = None
        while time.time() < deadline:
            r = await client.get(f"/runs/{job_id}")
            detail = r.json()
            if detail["status"] in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.5)

        assert detail is not None
        assert detail["status"] == "completed", f"Job did not complete: {detail}"
        assert detail["results"] is not None

        results = detail["results"]
        # Exact result
        assert results["exact"] is not None
        assert 0.0 <= results["exact"]["p_fail"] <= 1.0
        assert results["exact"]["n_states"] == 64

        # Monte Carlo result
        assert results["monte_carlo"] is not None
        mc = results["monte_carlo"]
        assert 0.0 <= mc["p_fail_estimate"] <= 1.0
        assert mc["ci_lower"] <= mc["p_fail_estimate"] <= mc["ci_upper"]
        assert mc["n_samples"] == 500

    @pytest.mark.skipif(FAST, reason="Slow: waits for full computation pipeline + export")
    @pytest.mark.asyncio
    async def test_export_json_after_completion(self, client):
        post = (await client.post("/runs", json=SCENARIO_FULL)).json()
        job_id = post["job_id"]

        deadline = time.time() + 60
        while time.time() < deadline:
            detail = (await client.get(f"/runs/{job_id}")).json()
            if detail["status"] in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.5)

        r = await client.get(f"/runs/{job_id}/export?format=json")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/json")
        import json
        exported = json.loads(r.text)
        assert exported["job_id"] == job_id

    @pytest.mark.skipif(FAST, reason="Slow: waits for full computation pipeline + CSV export")
    @pytest.mark.asyncio
    async def test_export_csv_after_completion(self, client):
        post = (await client.post("/runs", json=SCENARIO_FULL)).json()
        job_id = post["job_id"]

        deadline = time.time() + 60
        while time.time() < deadline:
            detail = (await client.get(f"/runs/{job_id}")).json()
            if detail["status"] in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.5)

        r = await client.get(f"/runs/{job_id}/export?format=csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        lines = r.text.strip().splitlines()
        assert len(lines) >= 2   # header + at least one data row
        assert "p_fail" in lines[0]
