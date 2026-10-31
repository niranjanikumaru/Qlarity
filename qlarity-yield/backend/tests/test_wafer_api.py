"""Regression checks for a blank wafer overview after a clean installation."""
import builtins
import pytest
from fastapi.testclient import TestClient
from backend.serve import app, WAFER_CACHES

@pytest.mark.parametrize('condition', ['nominal', 'equipment_drift', 'localized_defect', 'high_variance'])
def test_wafer_condition_returns_population(condition):
    with TestClient(app) as client:
        response = client.get('/api/wafer/summary', params={'wafer_type': condition})
    assert response.status_code == 200
    data = response.json()
    assert data['wafer_type'] == condition
    assert data['total_dies'] == data['passed_dies'] + data['failed_dies']
    assert data['sampled_dies']
    assert data['overall_yield_pct'] == round(100 * data['passed_dies'] / data['total_dies'], 2)


def test_missing_pandas_has_actionable_error(monkeypatch):
    WAFER_CACHES.clear()
    original_import = builtins.__import__
    def without_pandas(name, *args, **kwargs):
        if name == 'pandas':
            raise ModuleNotFoundError('pandas')
        return original_import(name, *args, **kwargs)
    with TestClient(app) as client:
        monkeypatch.setattr(builtins, '__import__', without_pandas)
        response = client.get('/api/wafer/summary')
    assert response.status_code == 503
    assert 'requirements-lock.txt' in response.json()['detail']
