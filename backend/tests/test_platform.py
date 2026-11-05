"""Lifecycle checks using isolated storage and existing human-reviewed source labels."""
import io
import json
import os
import sqlite3
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.main import create_app
from backend.app.platform_jobs import register_model
from backend.app.review import _yolo_axis


def reviewed_fixture():
    with sqlite3.connect(config.REVIEW_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM reviews WHERE image_id IN ('3dc56e3f56a0b819','04d4e569fa2f3371','1ab710002bf4bce2')").fetchall()
    from backend.app.review import ReviewStore
    store = ReviewStore(config.REVIEW_MANIFEST, config.REVIEW_PREDICTIONS, config.REVIEW_DB, config.REVIEW_EXPORTS,
                        config.REVIEW_TRAIN_MANIFEST, config.REVIEW_TRAIN_PREDICTIONS)
    return [(store.get(r['image_id']), [{k:v for k,v in box.items() if k!='prediction_id'} for box in json.loads(r['boxes_json'])]) for r in rows]


def archive_fixture():
    buffer = io.BytesIO()
    originals = {}
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('dataset.yaml', 'names:\n  0: hatchling\n')
        for index, (item, boxes) in enumerate(reviewed_fixture()):
            filename = f'fixture_{index}.jpg'
            archive.writestr(f'images/{filename}', (config.ROOT / item['source_path']).read_bytes())
            lines = []
            for box in boxes:
                x1,y1,x2,y2 = box['xyxy']
                x,w = _yolo_axis(x1,x2,item['width'])
                y,h = _yolo_axis(y1,y2,item['height'])
                lines.append(f'0 {x} {y} {w} {h}')
            archive.writestr(f'labels/fixture_{index}.txt', '\n'.join(lines))
            originals[filename] = boxes
    return buffer.getvalue(), originals


def wait(client, job_id, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f'/api/platform/jobs/{job_id}')
        assert response.status_code == 200, response.text
        row = response.json()
        if row['status'] in {'completed','failed','stopped','interrupted'}:
            assert row['status'] == 'completed', (row, client.get(f'/api/platform/jobs/{job_id}/logs').json())
            return row
        time.sleep(.25)
    pytest.fail(f'Job timeout: {job_id}')


@pytest.fixture
def client(tmp_path):
    app = create_app(review_db=tmp_path/'reviews.sqlite3', review_exports=tmp_path/'exports',
                     job_root=tmp_path/'inference', platform_root=tmp_path/'platform', bootstrap_platform=False)
    with TestClient(app) as client:
        yield client


def import_and_approve(client):
    archive, originals = archive_fixture()
    response = client.post('/api/platform/datasets/upload',
        data={'name':'Software-test fixture', 'source':'Existing approved labels; isolated software check; event independence unverified'},
        files=[('files', ('fixture.zip', archive, 'application/zip'))])
    assert response.status_code == 202, response.text
    wait(client, response.json()['job']['id'])
    dataset_id = response.json()['dataset_id']
    images = client.get(f'/api/platform/datasets/{dataset_id}').json()['images']
    assert len(images) == 3
    assert all(i['status'] == 'unreviewed' for i in images)
    for image in images:
        boxes = originals[image['filename']]
        body = {'status':'verified_positive' if boxes else 'verified_negative', 'boxes':boxes,
                'reviewer':'software-test fixture', 'notes':'Exact existing approved annotation; isolated software fixture', 'revision':0}
        response = client.put(f"/api/review/images/{image['id']}", json={**body, 'reviewer':''})
        assert response.status_code == 422
        response = client.put(f"/api/review/images/{image['id']}", json=body)
        assert response.status_code == 200, response.text
        assert client.get(f"/api/review/images/{image['id']}").json()['status'] == body['status']
    return dataset_id, images


def test_zip_folder_import_review_grouping_preparation_and_export(client):
    _, images = import_and_approve(client)
    dataset_id=images[0]['dataset_id']
    reinspected=client.post(f'/api/platform/datasets/{dataset_id}/inspect')
    wait(client,reinspected.json()['id'])
    same=client.get(f'/api/platform/datasets/{dataset_id}').json()['images']
    assert {i['id'] for i in same}=={i['id'] for i in images}
    assert all(i['status'] in {'verified_positive','verified_negative'} for i in same)
    request = {'name':'Isolated fixture version', 'image_ids':[i['id'] for i in images]}
    assert not client.post('/api/platform/prepare/preflight', json=request).json()['ready']
    positives = [i for i in images if i['original']]
    for image in images:
        split = 'val' if image['id'] == positives[-1]['id'] else 'train'
        group = {'group_id':f"software-fixture:{image['id']}", 'split':split, 'confirmed':True,
                 'independent':False, 'reviewer':'software-test fixture',
                 'evidence':'Isolated software fixture assignment; no event independence claim'}
        response = client.put(f"/api/platform/images/{image['id']}/group", json=group)
        assert response.status_code == 200, response.text
    check = client.post('/api/platform/prepare/preflight', json=request).json()
    assert check['ready'], check
    response = client.post('/api/platform/prepare', json=request)
    assert response.status_code == 202, response.text
    prepared = wait(client, response.json()['id'])
    version = prepared['result']['version_id']
    result = client.get(f'/api/platform/versions/{version}/download')
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert len(manifest) == 3
        negative = next(r for r in manifest if r['status'] == 'verified_negative')
        assert archive.read(negative['label']) == b''
    source = config.ROOT/'backend/tests/fixtures/hatchling_nps.jpg'
    folder = client.post('/api/platform/datasets/upload',
        data={'name':'Folder fixture', 'paths':'["survey/images/sample.jpg"]'},
        files=[('files', ('sample.jpg', source.read_bytes(), 'image/jpeg'))])
    assert folder.status_code == 202, folder.text
    wait(client, folder.json()['job']['id'])
    detail = client.get(f"/api/platform/datasets/{folder.json()['dataset_id']}").json()
    assert detail['images'][0]['status'] == 'unreviewed'
    assert any(issue['code'] == 'missing_label' for issue in detail['images'][0]['issues'])


def test_zip_traversal_is_rejected(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('../escape.txt', 'unsafe')
    response = client.post('/api/platform/datasets/upload', data={'name':'Unsafe archive'},
        files=[('files', ('unsafe.zip', buffer.getvalue(), 'application/zip'))])
    assert response.status_code == 422


def test_preparation_blocks_missing_media_and_later_frozen_matches(client):
    _, images = import_and_approve(client)
    positives = [image for image in images if image['original']]
    for image in images:
        response = client.put(f"/api/platform/images/{image['id']}/group", json={
            'group_id':f"gate-fixture:{image['id']}",
            'split':'val' if image['id']==positives[-1]['id'] else 'train',
            'confirmed':True,'reviewer':'software fixture',
            'evidence':'Isolated software test assignment; independence unverified'})
        assert response.status_code==200, response.text
    payload={'name':'Source integrity fixture','image_ids':[image['id'] for image in images]}
    db=client.app.state.platform.db
    row=db.one('SELECT * FROM platform_images WHERE id=?',(positives[0]['id'],))
    source=(config.ROOT/row['path']).resolve()
    assert source.is_relative_to(db.root.resolve())
    missing=source.with_suffix('.temporarily-unavailable')
    source.rename(missing)
    try:
        check=client.post('/api/platform/prepare/preflight',json=payload)
        assert check.status_code==200 and not check.json()['ready']
        assert any('source image is missing' in error for error in check.json()['errors'])
    finally:
        missing.rename(source)
    frozen=client.post('/api/platform/datasets/upload',data={'name':'Later frozen source','pool':'evaluation'},
                      files=[('files',('frozen.jpg',source.read_bytes(),'image/jpeg'))])
    assert frozen.status_code==202,frozen.text
    wait(client,frozen.json()['job']['id'])
    check=client.post('/api/platform/prepare/preflight',json=payload).json()
    assert not check['ready'] and any('source matches frozen' in error for error in check['errors'])


def test_training_gates_registry_report_and_camera_boundary(client):
    db = client.app.state.platform.db
    model_id = register_model(db, config.ROOT/'yolo26n.pt', pretrained=True)
    response = client.post('/api/platform/training/start',
        json={'version_id':'missing', 'model_id':model_id, 'confirm_resources':True})
    assert response.status_code == 422 and 'Select a prepared' in response.text
    assert client.get('/api/platform/models').json()[0]['sha256']
    report = client.post('/api/platform/reports', json={'kind':'project'})
    assert report.status_code == 202, report.text
    report_id = wait(client, report.json()['id'])['result']['report_id']
    assert client.get(f'/api/platform/reports/{report_id}/pdf').content.startswith(b'%PDF-1.4')
    assert client.get(f'/api/platform/reports/{report_id}/csv').status_code == 200
    snapshot=client.get(f'/api/platform/reports/{report_id}/json').json()
    assert any(model['sha256'] for model in snapshot['context']['model_versions'])
    assert 'dataset_versions' in snapshot['context']
    assert client.get('/api/platform/monitoring').json()['camera_available'] is False


@pytest.mark.skipif(os.environ.get('NAZAR_RUN_TRAIN_SMOKE') != '1',
                    reason='Real one-epoch smoke is explicitly enabled by the operator')
def test_authorized_small_training_evaluation_inference_lifecycle(client):
    _, images = import_and_approve(client)
    positives = [i for i in images if i['original']]
    for image in images:
        body = {'group_id':f"software-fixture:{image['id']}",
                'split':'val' if image['id'] == positives[-1]['id'] else 'train',
                'confirmed':True, 'independent':False, 'reviewer':'software-test fixture',
                'evidence':'Isolated software fixture; image identities distinct; event independence unverified'}
        assert client.put(f"/api/platform/images/{image['id']}/group", json=body).status_code == 200
    preparation = client.post('/api/platform/prepare',
        json={'name':'Smoke fixture only', 'image_ids':[i['id'] for i in images]})
    assert preparation.status_code == 202, preparation.text
    version_id = wait(client, preparation.json()['id'])['result']['version_id']
    db = client.app.state.platform.db
    pretrained = register_model(db, config.ROOT/'yolo26n.pt', pretrained=True)
    settings = {'version_id':version_id, 'model_id':pretrained, 'epochs':1, 'imgsz':128,
                'batch':1, 'patience':1, 'device':'cpu', 'max_hours':.05, 'confirm_resources':True}
    response = client.post('/api/platform/training/start', json=settings)
    assert response.status_code == 202, response.text
    training = wait(client, response.json()['id'], timeout=240)
    assert training['result']['models']
    trained = next(m for m in client.get('/api/platform/models').json()
                   if m['job_id'] == training['id'] and m['checkpoint'].endswith('best.pt'))
    response = client.post('/api/platform/evaluation/start',
        json={'model_id':trained['id'], 'version_id':version_id, 'split':'val', 'imgsz':128})
    assert response.status_code == 202, response.text
    evaluated = wait(client, response.json()['id'], timeout=120)
    assert evaluated['result']['scope'] == 'validation'
    assert client.post(f"/api/platform/models/{trained['id']}/activate").status_code == 200
    with (config.ROOT/'backend/tests/fixtures/hatchling_nps.jpg').open('rb') as stream:
        detected = client.post('/api/detect/image', files={'file':('sample.jpg', stream, 'image/jpeg')})
    assert detected.status_code == 200, detected.text
    assert client.get(detected.json()['download_url']).status_code == 200
    report = client.post('/api/platform/reports', json={'kind':'training'})
    assert wait(client, report.json()['id'])['result']['report_id']


def test_duplicate_detection_split_conflict_and_frozen_protection(client):
    from PIL import Image
    item, boxes = reviewed_fixture()[0]
    source = config.ROOT/item['source_path']
    encoded = io.BytesIO()
    with Image.open(source) as image:
        image.resize((max(1,image.width//2),max(1,image.height//2))).save(encoded,format='JPEG')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('images/a.jpg',source.read_bytes())
        z.writestr('images/b.jpg',source.read_bytes())
        z.writestr('images/c_resized.jpg',encoded.getvalue())
        z.writestr('labels/a.txt','9 0.5 0.5 0.2 0.2')  # Deliberate invalid parser fixture.
    response=client.post('/api/platform/datasets/upload',data={'name':'Duplicate parser fixture'},
                         files=[('files',('duplicates.zip',archive.getvalue(),'application/zip'))])
    wait(client,response.json()['job']['id'])
    images=client.get(f"/api/platform/datasets/{response.json()['dataset_id']}").json()['images']
    assert any(issue['code']=='invalid_label' for image in images for issue in image['issues'])
    assert any(issue['code']=='exact_duplicate' for image in images for issue in image['issues'])
    assert any(issue['code']=='near_duplicate' for image in images for issue in image['issues'])
    exacts=[i for i in images if i['filename'] in {'a.jpg','b.jpg'}]
    for index,image in enumerate(exacts):
        decision={'status':'verified_positive' if boxes else 'verified_negative','boxes':boxes,
                  'revision':0,'reviewer':'software fixture','notes':'Existing approved geometry copied for duplicate gating check'}
        assert client.put(f"/api/review/images/{image['id']}",json=decision).status_code==200
        group={'group_id':f'fixture-group-{index}','split':'train' if index==0 else 'val','confirmed':True,
               'reviewer':'software fixture','evidence':'Intentional conflicting assignment for gate test','independent':False}
        assert client.put(f"/api/platform/images/{image['id']}/group",json=group).status_code==200
    result=client.post('/api/platform/prepare/preflight',json={'name':'Blocked duplicate','image_ids':[i['id'] for i in exacts]}).json()
    assert not result['ready'] and any('Exact duplicate' in e for e in result['errors'])
    frozen=client.post('/api/platform/datasets/upload',data={'name':'Frozen fixture','pool':'evaluation'},
                       files=[('files',('source.jpg',source.read_bytes(),'image/jpeg'))])
    wait(client,frozen.json()['job']['id'])
    repeated=client.post('/api/platform/datasets/upload',data={'name':'Repeated frozen source','pool':'training'},
                       files=[('files',('source.jpg',source.read_bytes(),'image/jpeg'))])
    wait(client,repeated.json()['job']['id'])
    protected=client.get(f"/api/platform/datasets/{repeated.json()['dataset_id']}").json()['images'][0]
    assert protected['pool']=='evaluation'
    assert any(i['code']=='frozen_source_overlap' for i in protected['issues'])
    forbidden=client.put(f"/api/platform/images/{protected['id']}/group",
        json={'group_id':'fixture-event','split':'train','confirmed':True,'reviewer':'software fixture','evidence':'Intentional forbidden assignment'})
    assert forbidden.status_code==422


def test_video_import_preserves_recording_group_and_unreviewed_status(client,tmp_path):
    import cv2
    capture=cv2.VideoCapture(str(config.ROOT/'data/video/real_leatherback_demo.mp4'))
    width,height=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    clip=tmp_path/'recording.mp4'
    writer=cv2.VideoWriter(str(clip),cv2.VideoWriter_fourcc(*'mp4v'),10,(width,height))
    for _ in range(12):
        ok,frame=capture.read()
        assert ok
        writer.write(frame)
    writer.release();capture.release()
    result=client.post('/api/platform/datasets/upload',data={'name':'Actual-frame extraction fixture'},
                       files=[('files',('recording.mp4',clip.read_bytes(),'video/mp4'))])
    assert result.status_code==202,result.text
    wait(client,result.json()['job']['id'])
    images=client.get(f"/api/platform/datasets/{result.json()['dataset_id']}").json()['images']
    assert len(images)==1 and images[0]['status']=='unreviewed'
    assert images[0]['source_group'].startswith('recording:')


def test_yolo_serialization_rounding_keeps_edge_box(tmp_path):
    from backend.app.platform_data import parse_yolo
    label=tmp_path/'edge.txt'
    label.write_text('0 0.5 0.468988 1.0 0.937977\n')
    boxes,issues=parse_yolo(label,1024,768,{0:'hatchling'})
    assert len(boxes)==1
    assert boxes[0]['xyxy'][1]==0
    assert not any(i['code']=='invalid_label' for i in issues)
    assert any(i['code']=='boundary_rounding' for i in issues)



