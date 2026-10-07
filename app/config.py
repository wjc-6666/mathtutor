import os
from pathlib import Path
from dotenv import load_dotenv
ROOT=Path(os.getenv('MATHTUTOR_ROOT',Path(__file__).resolve().parents[1]))
load_dotenv(ROOT/'.env', override=False)
DATA=ROOT/'data'
DATA.mkdir(parents=True,exist_ok=True)
BOOKS=Path(os.getenv('MATHTUTOR_BOOKS',ROOT/'books'))
