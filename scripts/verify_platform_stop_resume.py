"""Bounded CPU stop/resume check against the isolated browser-test server only.

Requires verify_platform_review_browser.js to have created its three-image fixture.
This is software verification, never a model-quality experiment.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.platform_db import PlatformDB
from backend.app.platform_jobs import register_model

BASE = 'http://127.0.0.1:8001'
directory = ROOT / 'artifacts/platform/test_runs/ui'
db = PlatformDB(directory/'reviews.sqlite3', directory/'platform')
version = db.one('SELECT * FROM platform_versions ORDER BY created_at DESC LIMIT 1')
if not version or not Path(version['path']).resolve().is_relative_to(directory.resolve()):
    raise SystemExit('An isolated browser software-test version is required')
remote = requests.get(BASE+'/api/platform/versions', timeout=15)
remote.raise_for_status()
if version['id'] not in {row['id'] for row in remote.json()}:
    raise SystemExit('The API does not serve the expected isolated test database')
model_id = register_model(db, ROOT/'yolo26n.pt', pretrained=True)


def post(path, body=None):
    response = requests.post(BASE+path, json=body, timeout=30)
    response.raise_for_status()
    return response.json()


def job(identifier):
    response = requests.get(BASE+'/api/platform/jobs/'+identifier, timeout=15)
    response.raise_for_status()
    return response.json()


def finished(identifier):
    deadline = time.monotonic()+240
    while time.monotonic()<deadline:
        row = job(identifier)
        if row['status'] in {'completed','stopped','failed','interrupted'}:
            return row
        time.sleep(.3)
    raise AssertionError('Bounded software test exceeded 240 seconds')


def hashes(folder):
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*.pt')}


settings = {'version_id':version['id'],'model_id':model_id,'epochs':3,'imgsz':128,
            'batch':1,'patience':3,'device':'cpu','max_hours':.01,'confirm_resources':True}
original = post('/api/platform/training/start', settings)
run = db.root/'experiments'/original['id']
deadline = time.monotonic()+120
while not (run/'args.yaml').is_file():
    state = job(original['id'])
    assert state['status'] not in {'failed','stopped','interrupted'}, state
    if time.monotonic()>deadline:
        raise AssertionError('Training did not initialize within 120 seconds')
    time.sleep(.1)
post('/api/platform/jobs/'+original['id']+'/stop')
stopped = finished(original['id'])
assert stopped['status']=='stopped' and stopped['resumable'], stopped
assert (run/'weights/resume.pt').is_file()
import torch
checkpoint = torch.load(run/'weights/resume.pt', map_location='cpu', weights_only=False)
assert checkpoint['epoch']==0, 'Final evaluation overwrote the stopped epoch checkpoint'
preserved = hashes(run)
resuming = post('/api/platform/jobs/'+original['id']+'/resume')
resumed = finished(resuming['id'])
assert resumed['status']=='completed', resumed
assert preserved==hashes(run), 'Resuming changed the original run checkpoints'
assert resumed['result']['models'], resumed
metrics = requests.get(BASE+'/api/platform/jobs/'+resuming['id'],timeout=15).json()['metrics']
assert [row['epoch'] for row in metrics]==[1,2,3], metrics
result = {'scope':'isolated software fixture; no accuracy or independence claim',
          'stopped_job':original['id'],'resumed_job':resuming['id'],
          'stopped_status':stopped['status'],'resumed_status':resumed['status'],
          'logged_epochs':[row['epoch'] for row in metrics],
          'last_logged_epoch':metrics[-1]['epoch'],'original_checkpoints_unchanged':True,
          'baseline_sha256':hashlib.sha256((ROOT/'artifacts/training/hatchling_n_640/weights/best.pt').read_bytes()).hexdigest()}
output=ROOT/'artifacts/platform/implementation/stop_resume_test.json'
output.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
