"""Serve a disposable copy of recorded software-test data for manual screenshots.

The original test database, production reviews, source images and checkpoints are
read-only inputs. Existing artifact paths are retained to show genuine plots/logs.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import uvicorn
import cv2
from backend.app.main import create_app
from backend.app.platform_db import PlatformDB
from backend.app.platform_jobs import register_model

source=ROOT/'artifacts/platform/test_runs/smoke/test_authorized_small_training0'
runtime=ROOT/'tmp/pdfs/user_manual/runtime'
runtime.mkdir(parents=True,exist_ok=True)
database=runtime/'preview.sqlite3'
if not database.exists():
    with sqlite3.connect(f"file:{(source/'reviews.sqlite3').as_posix()}?mode=ro",uri=True) as original:
        with sqlite3.connect(database) as copied:
            original.backup(copied)
catalog=PlatformDB(database,source/'platform')
baseline=register_model(catalog,ROOT/'artifacts/training/hatchling_n_640/weights/best.pt')
catalog.execute("INSERT INTO platform_settings VALUES('active_model',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(baseline,))
metadata={'purpose':'Disposable screenshot preview; recorded software-test fixture, not an accuracy benchmark',
          'copied_database':database.relative_to(ROOT).as_posix(),
          'source_database':(source/'reviews.sqlite3').relative_to(ROOT).as_posix(),
          'artifact_root':(source/'platform').relative_to(ROOT).as_posix(),
          'models':catalog.all('SELECT id,name,sha256 FROM platform_models'),
          'versions':catalog.all('SELECT id,name,summary_json FROM platform_versions'),
          'evaluations':catalog.all('SELECT id,kind FROM platform_evaluations')}
(runtime/'source_context.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
clip=runtime/'manual_real_video_excerpt.mp4'
if not clip.exists():
    capture=cv2.VideoCapture(str(ROOT/'data/video/real_leatherback_demo.mp4'))
    width,height=int(capture.get(3)),int(capture.get(4))
    fps=capture.get(cv2.CAP_PROP_FPS) or 24
    writer=cv2.VideoWriter(str(clip),cv2.VideoWriter_fourcc(*'mp4v'),fps,(width,height))
    for _ in range(24):
        ok,frame=capture.read()
        if not ok:break
        writer.write(frame)
    writer.release();capture.release()
app=create_app(review_db=database,review_exports=runtime/'exports',platform_root=source/'platform',
               job_root=runtime/'inference',bootstrap_platform=False)
if __name__=='__main__':
    uvicorn.run(app,host='127.0.0.1',port=8001)
