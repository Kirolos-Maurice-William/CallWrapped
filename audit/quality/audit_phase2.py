import os
import re
import sys
import subprocess
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path("g:/CallWrapper")

def audit_phase2():
    print("=== PHASE 2: GHOST STRINGS & CONSISTENCY ===")
    
    # 2a: Model name grep: "llama|3-6|3.6|mock" across bot/, backend/, frontend/
    print("\n--- 2a: Hardcoded model strings ---")
    model_pattern = re.compile(r'(llama|3-6|3\.6|mock)', re.IGNORECASE)
    for folder in ['bot', 'backend', 'frontend']:
        dir_path = REPO_ROOT / folder
        if not dir_path.exists():
            continue
        for p in dir_path.rglob('*'):
            if p.is_file() and not any(part in p.parts for part in ['node_modules', '.next', '__pycache__', 'venv']):
                try:
                    text = p.read_text(encoding='utf-8', errors='ignore')
                    for idx, line in enumerate(text.splitlines(), 1):
                        if model_pattern.search(line):
                            # Ignore comments or check? User said: "search for ANY hardcoded 'llama|3-6|3.6|mock' across bot/, backend/, frontend/. All LLM calls must go through configured model name."
                            print(f"{p.relative_to(REPO_ROOT)}:{idx}: {line.strip()[:120]}")
                except Exception as e:
                    pass

    # 2b: Branding sweep: "Voice Arbitrator" vs "CallWrapped"
    print("\n--- 2b: Branding sweep: 'Voice Arbitrator' / 'VoiceArbitrator' ---")
    va_pattern = re.compile(r'voice[\s_-]?arbitrat', re.IGNORECASE)
    cw_count = 0
    va_count = 0
    for folder in ['bot', 'backend', 'frontend']:
        dir_path = REPO_ROOT / folder
        if not dir_path.exists():
            continue
        for p in dir_path.rglob('*'):
            if p.is_file() and not any(part in p.parts for part in ['node_modules', '.next', '__pycache__', 'venv']):
                try:
                    text = p.read_text(encoding='utf-8', errors='ignore')
                    for idx, line in enumerate(text.splitlines(), 1):
                        if va_pattern.search(line):
                            va_count += 1
                            print(f"VA: {p.relative_to(REPO_ROOT)}:{idx}: {line.strip()[:120]}")
                        if 'callwrapped' in line.lower() or 'call_wrapped' in line.lower() or 'call-wrapped' in line.lower() or 'callwrapper' in line.lower():
                            cw_count += 1
                except Exception:
                    pass
    print(f"Total CallWrapped mentions: {cw_count}, Total Voice Arbitrator mentions: {va_count}")

    # 2c: TODO/FIXME/XXX/HACK/DEBUG sweep
    print("\n--- 2c: TODO / FIXME / XXX / HACK sweep ---")
    marker_pattern = re.compile(r'\b(TODO|FIXME|XXX|HACK)\b', re.IGNORECASE)
    markers = []
    for folder in ['bot', 'backend', 'frontend', 'tests']:
        dir_path = REPO_ROOT / folder
        for p in dir_path.rglob('*'):
            if p.is_file() and not any(part in p.parts for part in ['node_modules', '.next', '__pycache__', 'venv']):
                try:
                    text = p.read_text(encoding='utf-8', errors='ignore')
                    for idx, line in enumerate(text.splitlines(), 1):
                        m = marker_pattern.search(line)
                        if m:
                            markers.append((p.relative_to(REPO_ROOT), idx, m.group(1).upper(), line.strip()))
                except Exception:
                    pass
    print(f"Total markers found: {len(markers)}")
    for file, line, marker, text in markers:
        print(f"{marker} [{file}:{line}]: {text[:120]}")

    # 2d: Debug prints: print( in bot/ and backend/
    print("\n--- 2d: Debug prints: print( in bot/ and backend/ ---")
    print_pattern = re.compile(r'^\s*print\s*\(', re.MULTILINE)
    print_sites = []
    for folder in ['bot', 'backend']:
        dir_path = REPO_ROOT / folder
        for p in dir_path.rglob('*.py'):
            if 'venv' in p.parts or '__pycache__' in p.parts:
                continue
            text = p.read_text(encoding='utf-8', errors='ignore')
            for idx, line in enumerate(text.splitlines(), 1):
                if re.match(r'^\s*print\s*\(', line):
                    print_sites.append((p.relative_to(REPO_ROOT), idx, line.strip()))
    print(f"Total print() calls in production bot/backend: {len(print_sites)}")
    for file, line, text in print_sites:
        print(f"{file}:{line}: {text[:120]}")

    # 2e: Hardcoded values: Discord IDs, permissions, magic numbers
    print("\n--- 2e: Hardcoded values: Discord IDs, permissions, magic numbers ---")
    discord_id_pattern = re.compile(r'\b\d{17,20}\b')
    for folder in ['bot', 'backend']:
        dir_path = REPO_ROOT / folder
        for p in dir_path.rglob('*.py'):
            if 'venv' in p.parts:
                continue
            text = p.read_text(encoding='utf-8', errors='ignore')
            for idx, line in enumerate(text.splitlines(), 1):
                # Search for long integer IDs
                for m in discord_id_pattern.finditer(line):
                    print(f"Hardcoded ID {m.group(0)} at {p.relative_to(REPO_ROOT)}:{idx}: {line.strip()[:100]}")

if __name__ == '__main__':
    audit_phase2()
