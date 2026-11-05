"""Isolated browser-test server. Never use this database for scientific experiments."""
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.main import create_app
import uvicorn

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,default=ROOT/'artifacts/platform/test_runs/ui')
    parser.add_argument('--port',type=int,default=8001)
    args=parser.parse_args()
    directory=args.directory.resolve()
    if not directory.is_relative_to((ROOT/'artifacts/platform/test_runs').resolve()):
        raise SystemExit('UI test storage must remain inside artifacts/platform/test_runs')
    app=create_app(review_db=directory/'reviews.sqlite3',review_exports=directory/'exports',
                   platform_root=directory/'platform',job_root=directory/'inference',bootstrap_platform=False)
    uvicorn.run(app,host='127.0.0.1',port=args.port)

