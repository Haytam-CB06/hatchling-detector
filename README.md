# Hatchling Detector Model Workspace

This repository contains a local React/TypeScript and FastAPI workbench for the hatchling detector model: dataset curation, human review, reproducible dataset preparation, training, checkpoint management, evaluation, inference, and experiment history. The detector is intended to be the brain behind Nazar Vision. This is the model development workspace, not the full Nazar Vision product.

## Walkthroughs

- [Illustrated workspace guide (PDF)](output/pdf/Hatchling_Detector_Model_Workspace_Guide.pdf) - screenshots, purpose, and best practices for all 12 sections.
- [Screen-recording walkthrough](docs/Hatchling_Detector_Model_Workspace_Recording_Guide.md) - suggested narration and a complete section-by-section outline.

The screenshots show a populated local workspace. Counts, jobs, and model metrics reflect that capture and can differ in a fresh installation. Read each metric with its recorded dataset and evaluation scope.

## Quick start

Use PowerShell from this repository root. The documented Conda environment is `nazar-vision`.

```powershell
conda env create -f environment.yml
conda activate nazar-vision
python -m pip install -r requirements.txt
python -m pip install -r backend/requirements.txt
```

Start the API in one terminal:

```powershell
python -s -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Start the web interface in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5050/>. API health and interactive documentation are available at <http://127.0.0.1:8000/api/health> and <http://127.0.0.1:8000/docs>.

## Model checkpoint

This repository does not include trained model weights or the research datasets. The backend can start without a checkpoint, but inference stays unavailable until a compatible one-class `hatchling` detector is supplied. Set its path before starting the API:

```powershell
$env:NAZAR_MODEL_PATH = 'C:\absolute\path\to\best.pt'
$env:NAZAR_DEVICE = 'cpu'
python -s -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

The application is a research prototype. Review model outputs; screenshot metrics are not an independent accuracy claim. Video detections are frame-level and do not identify unique animals. The current platform inspects uploaded recordings; a live-camera integration is not configured.

## Included sample media

`data/video/real_leatherback_demo.mp4` is an attributed, three-second browser demo clip derived from real wildlife footage. Its creator and CC BY 2.0 license are documented in [data/video/README.md](data/video/README.md). The image fixture under `backend/tests/fixtures/` is credited to the U.S. National Park Service and marked public domain.

The application runs locally and has no user accounts or public-server hardening. Raw datasets, generated job artifacts, local databases, and checkpoints are excluded from this repository.
