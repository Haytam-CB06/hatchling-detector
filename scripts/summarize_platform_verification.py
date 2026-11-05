"""Consolidate executed evidence and check the running local platform."""
import hashlib
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'artifacts/platform/implementation'


def read(name):
    return json.loads((folder/name).read_text(encoding='utf-8-sig'))


def browser(name):
    lines=(folder/name).read_text(encoding='utf-8-sig').splitlines()
    index=lines.index('### Result')
    return json.loads(lines[index+1])


def get(path):
    response=requests.get('http://127.0.0.1:5050/api'+path,timeout=30)
    response.raise_for_status()
    return response.json()


tests={}
for name in ('final_regression_tests.xml','integrity_gate_tests.xml','report_metadata_test.xml','smoke_test.xml'):
    suites=ET.parse(folder/name).getroot().findall('testsuite')
    tests[name]={key:sum(float(suite.get(key,0)) for suite in suites)
                 for key in ('tests','failures','errors','skipped','time')}
    assert tests[name]['failures']==tests[name]['errors']==0
health=get('/health')
overview=get('/platform/overview')
assert health['status']=='ok' and health['model_state']=='ready' and health['video_encoding_ready']
worker_id=read('final_worker_check_job.json')['id']
deadline=time.monotonic()+30
while True:
    worker=get('/platform/jobs/'+worker_id)
    if worker['status'] not in {'queued','running'}:break
    if time.monotonic()>deadline:raise AssertionError('Final worker check timed out')
    time.sleep(.2)
assert worker['status']=='completed' and worker['result']['registered_models']==5,worker
history=[json.loads(path.read_text(encoding='utf-8')) for path in (ROOT/'artifacts/inference_history').glob('*.json')]
history=sorted(history,key=lambda row:row['created_at'],reverse=True)[:200]
speeds=[row['stats']['model_call_ms'] for row in history if row.get('model_sha256')==overview['active_model']['sha256'] and row.get('stats') and 'model_call_ms' in row['stats']]
assert len(speeds)==overview['inference_sample_count']
if speeds:
    assert abs(sum(speeds)/len(speeds)-overview['inference_average_ms'])<1e-6
dist=ROOT/'frontend/dist'
assets=[{'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,
         'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in dist.rglob('*') if path.is_file()]
assert assets and (dist/'index.html').is_file()
result={'verified_at':datetime.now(timezone.utc).isoformat(),'url':'http://127.0.0.1:5050/',
        'test_runs':tests,'browser_navigation':browser('browser_platform_test.log'),
        'browser_review_preparation':browser('browser_review_test.log'),
        'stop_resume':read('stop_resume_test.json'),'preservation':read('preservation_check.json'),
        'live_service':{'health':health,'active_model':overview['active_model']['name'],
                        'active_model_sha256':overview['active_model']['sha256'],
                        'active_model_timing_verified':True,'worker':worker,
                        'catalog_images':overview['images'],'approved_objects':overview['approved_objects'],
                        'review_status':overview['review_status'],'pending_reviews':overview['pending_reviews'],
                        'free_storage_bytes':overview['hardware']['disk_free']},
        'frontend_build_assets':assets,'final_project_report':read('final_report_job.json')['result']['report_id']}
assert result['preservation']['passed']
assert result['browser_navigation']['browserErrors']==[]
assert result['browser_review_preparation']['browser_errors']==[]
(folder/'verification_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'url':result['url'],'tests':tests,'live_service':result['live_service'],
                  'preservation_passed':result['preservation']['passed']},indent=2))
