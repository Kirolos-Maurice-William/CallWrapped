import os
import sys
import time
import subprocess
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path("g:/CallWrapper")
TESTS_DIR = REPO_ROOT / "tests"
PY_EXE = REPO_ROOT / "backend/venv/Scripts/python.exe"

test_files = sorted(list(TESTS_DIR.glob("test_*.py")))
timings = []

for tf in test_files:
    t0 = time.perf_counter()
    res = subprocess.run(
        [str(PY_EXE), "-m", "unittest", f"tests.{tf.stem}"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT)
    )
    dt = time.perf_counter() - t0
    timings.append((dt, tf.name, res.returncode))

timings.sort(reverse=True)
print("=== TOP 10 SLOWEST TEST FILES ===")
for dt, name, code in timings[:10]:
    status = "OK" if code == 0 else "FAIL"
    print(f"  {dt:6.2f}s : {name} ({status})")
