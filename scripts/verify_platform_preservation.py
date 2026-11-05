"""Read-only verification against the pre-implementation snapshot and Task 1 audit."""
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
evidence = ROOT/'artifacts/platform/implementation'
before = json.loads((evidence/'repository_audit.json').read_text(encoding='utf-8'))


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


db = ROOT/'artifacts/annotation_review/task03/reviews.sqlite3'
with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as connection:
    records = {table:connection.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()
               for table in ('reviews','review_events')}
    row_counts = {key:len(value) for key,value in records.items()}
    annotation_hashes = {key:hashlib.sha256(json.dumps(value,separators=(',',':'),default=str).encode()).hexdigest()
                         for key,value in records.items()}
    integrity = connection.execute('PRAGMA integrity_check').fetchall()
    foreign_keys = connection.execute('PRAGMA foreign_key_check').fetchall()
    connection.row_factory=sqlite3.Row
    images=[dict(row) for row in connection.execute('SELECT * FROM platform_images')]
    reviews=[dict(row) for row in connection.execute('SELECT * FROM reviews')]
    models=[dict(row) for row in connection.execute('SELECT * FROM platform_models')]
    active=connection.execute("SELECT value FROM platform_settings WHERE key='active_model'").fetchone()['value']
    groups=connection.execute('SELECT COUNT(*) FROM platform_groups').fetchone()[0]
    versions=connection.execute('SELECT COUNT(*) FROM platform_versions').fetchone()[0]

model_checks=[{'path':row['path'],'expected':row['sha256'],'actual':digest(ROOT/row['path'])}
              for row in before['models']]
source_mismatches=[row['id'] for row in images if not (ROOT/row['path']).is_file() or digest(ROOT/row['path'])!=row['sha256']]
task1_mismatches=[]
task1_count=0
with (ROOT/'artifacts/model_improvement/task01_audit/samples.csv').open(newline='',encoding='utf-8-sig') as stream:
    for row in csv.DictReader(stream):
        task1_count+=1
        image=ROOT/'data/generated/hatchling_yolo_v1/images'/row['split']/row['filename']
        label=ROOT/'data/generated/hatchling_yolo_v1/labels'/row['split']/(image.stem+'.txt')
        if not image.is_file() or digest(image)!=row['file_sha256']:
            task1_mismatches.append({'filename':row['filename'],'issue':'image checksum differs from Task 1'})
        parsed=[]
        for line in label.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():continue
            fields=line.split()
            parsed.append((int(fields[0]),*(round(float(value),6) for value in fields[1:])))
        signature=hashlib.sha256(json.dumps(sorted(parsed)).encode()).hexdigest()
        if signature!=row['label_signature']:
            task1_mismatches.append({'filename':row['filename'],'issue':'label geometry differs from Task 1'})

baseline=next(row for row in models if row['id']==active)
statuses=Counter(row['status'] for row in reviews)
approved_objects=sum(sum(box['class_name']=='hatchling' for box in json.loads(row['boxes_json']))
                     for row in reviews if row['status'] in {'verified_positive','verified_negative'})
result={'verified_at':datetime.now(timezone.utc).isoformat(),
        'original_annotation_counts':row_counts,'original_annotation_content_sha256':annotation_hashes,
        'original_annotations_unchanged':annotation_hashes==before['annotation_content_sha256'] and row_counts==before['annotation_row_counts'],
        'original_models':model_checks,'original_models_unchanged':all(row['expected']==row['actual'] for row in model_checks),
        'sqlite_integrity':integrity,'foreign_key_violations':foreign_keys,
        'catalog_images':len(images),'catalog_source_checksum_mismatches':source_mismatches,
        'task1_samples_checked':task1_count,'task1_image_or_label_mismatches':task1_mismatches,
        'review_status':dict(statuses),'approved_hatchling_boxes':approved_objects,
        'pending_reviews':len(images)-sum(statuses.values()),'production_group_assignments':groups,
        'production_prepared_versions':versions,'production_models':len(models),
        'active_checkpoint':baseline['checkpoint'],'active_sha256':baseline['sha256']}
result['passed']=bool(result['original_annotations_unchanged'] and result['original_models_unchanged']
                      and integrity==[('ok',)] and not foreign_keys and not source_mismatches and not task1_mismatches)
(evidence/'preservation_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
if not result['passed']:
    raise SystemExit('Preservation verification failed; inspect the written evidence')
