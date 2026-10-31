# ⚛️ Qlarity-Yield: Semiconductor Leakage-Yield Workbench

This directory contains the core implementation of the **Qlarity Yield Intelligence Engine**, featuring the physics models, reversible quantum oracle, iterative quantum amplitude estimation (IQAE), and interactive web dashboard.

> For the comprehensive project overview, problem statement breakdown, classical algorithm failure analysis, empirical benchmark charts, and architecture diagrams, please see the root [**README.md**](../README.md).

---

## 🚀 Quickstart

```bash
# 1. Activate environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# 2. Install locked dependencies
pip install -r requirements-lock.txt

# 3. Launch the server
python -m uvicorn backend.serve:app --host 127.0.0.1 --port 8000 --reload
```

* **Landing Page:** [http://127.0.0.1:8000/landing.html](http://127.0.0.1:8000/landing.html)
* **Yield Studio:** [http://127.0.0.1:8000/index.html](http://127.0.0.1:8000/index.html)

---

## 📁 Directory Structure

```
qlarity-yield/
├── backend/
│   ├── app/
│   │   ├── quantum/             # Reversible arithmetic oracle & IQAE circuits
│   │   └── workbench.py         # Subthreshold leakage physics model & estimators
│   ├── tests/                   # Pytest suite (physics, api, oracle unitariness)
│   ├── requirements.txt         # Development requirements
│   └── serve.py                 # FastAPI service with remote host support & async runner
├── web/
│   ├── landing.html             # Three.js 3D glassmorphic landing page
│   ├── index.html               # 35,000-die spatial wafer map & parameter studio
│   ├── app.js                   # Interactive canvas controller & chart engine
│   └── style.css                # High-contrast visual theme
├── Dockerfile                   # Subfolder-root production container
├── .dockerignore                # Build exclusions
└── requirements-lock.txt        # Locked production dependencies (including pandas & qiskit)
```

---

## 🧪 Testing

```bash
# Run backend test suite
pytest backend/tests/ -v
```
