import os
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path("g:/CallWrapper")
EXCLUDE_DIRS = {'node_modules', '.next', '__pycache__', 'venv', 'out', '.git', 'dist', 'mgb3_clips'}

def search_in_files(files, terms):
    results = {term: [] for term in terms}
    for f in files:
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
            for line_idx, line in enumerate(content.splitlines(), 1):
                line_lower = line.lower()
                for term in terms:
                    if term.lower() in line_lower:
                        results[term].append((f.relative_to(REPO_ROOT), line_idx, line.strip()))
        except Exception:
            pass
    return results

# Gather files in bot, backend, and specific root config files
target_files = []
for folder in ['bot', 'backend']:
    base = REPO_ROOT / folder
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            p = Path(root) / f
            if p.suffix in ('.py', '.env', '.example', '.json', '.md', '.txt'):
                target_files.append(p)

for root_file in ['.env', '.env.example', 'README.md']:
    p = REPO_ROOT / root_file
    if p.exists():
        target_files.append(p)

print("=== PHASE 0a: VOICE CHECK (ShakirNeural vs SalmaNeural) ===")
voice_results = search_in_files(target_files, ['ShakirNeural', 'SalmaNeural'])
print(f"Hits for ShakirNeural: {len(voice_results['ShakirNeural'])}")
for path, line_no, text in voice_results['ShakirNeural']:
    print(f"  {path}:{line_no}: {text}")

print(f"\nHits for SalmaNeural: {len(voice_results['SalmaNeural'])}")
for path, line_no, text in voice_results['SalmaNeural']:
    print(f"  {path}:{line_no}: {text}")

print("\nWhere is voice read at runtime?")
tts_file = REPO_ROOT / 'bot/ai/tts.py'
for line_idx, line in enumerate(tts_file.read_text(encoding='utf-8', errors='ignore').splitlines(), 1):
    if 'TTS_VOICE' in line or 'voice' in line.lower() and ('communicate' in line.lower() or 'config' in line.lower()):
        print(f"  bot/ai/tts.py:{line_idx}: {line.strip()}")

print("\n=== PHASE 0b: LLAMA SEARCH in bot/ and backend/ ===")
llama_results = search_in_files(target_files, ['llama'])
print(f"Hits for 'llama' in bot/ and backend/: {len(llama_results['llama'])}")
for path, line_no, text in llama_results['llama']:
    print(f"  {path}:{line_no}: {text}")

print("\nCheck default model in bot/ai/groq.py and bot/config.py:")
for target in [REPO_ROOT / 'bot/ai/groq.py', REPO_ROOT / 'bot/config.py']:
    if target.exists():
        for line_idx, line in enumerate(target.read_text(encoding='utf-8', errors='ignore').splitlines(), 1):
            if any(k in line for k in ['LLM_MODEL', 'default_model', 'GROQ_MODEL', 'model']):
                print(f"  {target.relative_to(REPO_ROOT)}:{line_idx}: {line.strip()}")
