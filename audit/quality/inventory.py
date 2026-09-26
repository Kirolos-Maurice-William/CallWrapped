import os
import sys
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

MODULES = {
    "bot": "bot",
    "backend": "backend",
    "frontend (components+app)": [
        os.path.join("frontend", "components"),
        os.path.join("frontend", "app")
    ],
    "tests": "tests"
}

file_stats = []

def count_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

for mod_name, targets in MODULES.items():
    if isinstance(targets, str):
        target_list = [targets]
    else:
        target_list = targets
    
    mod_files = []
    mod_lines = 0
    for target in target_list:
        for root, dirs, files in os.walk(target):
            # ignore venv, node_modules, .next, __pycache__, .git
            if any(ign in root for ign in ["venv", "node_modules", ".next", "__pycache__", ".git"]):
                continue
            for f in files:
                if f.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".sql")):
                    p = os.path.join(root, f)
                    lc = count_lines(p)
                    mod_files.append((p, lc))
                    mod_lines += lc
                    file_stats.append((p, lc, mod_name))
    
    print(f"\nModule: {mod_name} ({len(mod_files)} files, {mod_lines} lines)")
    for p, lc in sorted(mod_files, key=lambda x: -x[1])[:10]:
        print(f"  {lc:5d} lines : {p}")

total_loc = sum(x[1] for x in file_stats)
print(f"\nTOTAL CODEBASE LOC (scanned modules): {total_loc} lines across {len(file_stats)} files")

print("\n--- TOP 5 LARGEST FILES ---")
top5 = sorted(file_stats, key=lambda x: -x[1])[:5]
for idx, (p, lc, mod) in enumerate(top5, 1):
    print(f"  {idx}. {p} : {lc} lines [{mod}]")

print("\n--- GIT COMMITS SINCE 701a7c0 ---")
git_cmd = ["git", "log", "--oneline", "701a7c0..HEAD"]
res = subprocess.run(git_cmd, capture_output=True, text=True, encoding="utf-8")
commits = res.stdout.strip().split("\n") if res.stdout.strip() else []
print(f"Total commits since 701a7c0: {len(commits)}")

# Categorize commits by prefix or message
areas = {
    "fix / stability": 0,
    "referee / arbitration": 0,
    "tts": 0,
    "stt / assemblyai": 0,
    "frontend / dashboard": 0,
    "tests / harness": 0,
    "ledger / docs": 0,
    "other": 0
}
for c in commits:
    cl = c.lower()
    if "ledger" in cl or "hash" in cl:
        areas["ledger / docs"] += 1
    elif "test" in cl or "judge" in cl or "harness" in cl:
        areas["tests / harness"] += 1
    elif "frontend" in cl or "dashboard" in cl or "disputespanel" in cl:
        areas["frontend / dashboard"] += 1
    elif "tts" in cl:
        areas["tts"] += 1
    elif "stt" in cl or "assemblyai" in cl or "silence" in cl or "keyterm" in cl or "custom spelling" in cl:
        areas["stt / assemblyai"] += 1
    elif "referee" in cl or "arbitrat" in cl or "dispute" in cl or "gate" in cl:
        areas["referee / arbitration"] += 1
    elif "fix" in cl:
        areas["fix / stability"] += 1
    else:
        areas["other"] += 1

for a, cnt in sorted(areas.items(), key=lambda x: -x[1]):
    print(f"  {a:<25}: {cnt} commits")
