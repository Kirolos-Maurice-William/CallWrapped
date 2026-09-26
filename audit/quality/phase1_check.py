import os
import sys
import re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath("."))


# 1. Read keys from .env and .env.example
def get_env_keys(fname):
    keys = {}
    if not os.path.exists(fname):
        return keys
    with open(fname, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                keys[k.strip()] = (v.strip().strip('"').strip("'"), idx)
    return keys

env_keys = get_env_keys(".env")
example_keys = get_env_keys(".env.example")

print("=" * 80)
print("1. CONFIG TRUTH CHECK: .env vs CODE USAGE")
print("=" * 80)

# Collect all code files in bot/ and backend/
code_files = []
for d in ["bot", "backend"]:
    for root, dirs, files in os.walk(d):
        if any(ign in root for ign in ["venv", "node_modules", ".next", "__pycache__"]):
            continue
        for f in files:
            if f.endswith(".py"):
                code_files.append(os.path.join(root, f))

# For each env key, search where it is referenced in code_files
key_usages = {}
for k in env_keys:
    key_usages[k] = []
    pattern = re.compile(r'\b' + re.escape(k) + r'\b')
    for cf in code_files:
        with open(cf, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                if pattern.search(line):
                    key_usages[k].append((cf, line_no, line.strip()))

unused_env_keys = []
for k, usages in sorted(key_usages.items()):
    # If the only usage is in bot/config.py or backend/app/config.py defining the default/reading it,
    # let's see if the config attribute itself is actually used!
    config_attr_usages = []
    attr_pattern = re.compile(r'\bconfig\.' + re.escape(k) + r'\b')
    for cf in code_files:
        if cf.endswith("config.py"):
            continue
        with open(cf, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, 1):
                if attr_pattern.search(line):
                    config_attr_usages.append((cf, line_no, line.strip()))

    direct_reads = [u for u in usages if not u[0].endswith("config.py")]
    
    if not direct_reads and not config_attr_usages:
        unused_env_keys.append((k, env_keys[k][0], usages))
        print(f"❌ UNUSED KEY: {k} (value: '{env_keys[k][0]}')")
        if usages:
            print(f"   Defined only in: {usages[0][0]}:{usages[0][1]}")
        else:
            print(f"   NOT EVEN READ IN CONFIG.PY!")
    else:
        # Key is actively used
        pass

print(f"\nTotal unused .env keys: {len(unused_env_keys)} of {len(env_keys)}")

print("\n" + "=" * 80)
print("2. REVERSE CHECK: os.getenv OR config.* REFERENCED BUT MISSING FROM .env")
print("=" * 80)

# Check all os.getenv calls in code_files
os_getenv_keys = set()
for cf in code_files:
    with open(cf, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        for m in re.finditer(r'os\.getenv\(\s*["\']([^"\']+)["\']', content):
            os_getenv_keys.add((m.group(1), cf))

missing_from_env = []
for k, cf in sorted(os_getenv_keys):
    if k not in env_keys:
        missing_from_env.append((k, cf))
        print(f"⚠️  os.getenv('{k}') in {cf} is MISSING from .env")

# Check config attributes referenced in code but not in config.py
# Inspect bot/config.py attributes
from bot.config import config as bot_config
bot_config_attrs = {a for a in dir(bot_config) if not a.startswith("_")}
print(f"\nBot Config Attributes count: {len(bot_config_attrs)}")

# Missing from .env.example
missing_from_example = [k for k in env_keys if k not in example_keys]
print(f"\nKeys in .env but missing from .env.example: {len(missing_from_example)}")
for k in missing_from_example:
    print(f"  - {k}")

print("\n" + "=" * 80)
print("3. DEAD PATHS FROM TWO-STAGE REFACTOR & LEGACY CODE")
print("=" * 80)
# Search for old patterns: auto-speak, is_arbitrating, correct_fact, etc.
dead_patterns = [
    ("is_arbitrating", r"\bis_arbitrating\b"),
    ("auto-speak / unsolicited speak", r"\bauto_speak\b|\bunsolicited\b"),
    ("correct_fact (legacy verifier field)", r"\bcorrect_fact\b"),
    ("single-clause verdict text", r"\bverdict_text\b"),
]

for label, pat_str in dead_patterns:
    pat = re.compile(pat_str, re.IGNORECASE)
    matches = []
    for cf in code_files:
        with open(cf, "r", encoding="utf-8", errors="ignore") as f:
            for lno, line in enumerate(f, 1):
                if pat.search(line):
                    matches.append((cf, lno, line.strip()))
    print(f"\nPattern: '{label}' -> {len(matches)} occurrences")
    for m in matches[:10]:
        print(f"  {m[0]}:{m[1]} -> {m[2]}")

print("\n" + "=" * 80)
print("4. UNUSED DEPENDENCIES (requirements.txt)")
print("=" * 80)

req_file = "requirements.txt"
if os.path.exists(req_file):
    with open(req_file, "r", encoding="utf-8") as f:
        reqs = [l.strip().split("==")[0].split(">=")[0].split("<=")[0].strip() for l in f if l.strip() and not l.startswith("#")]
    
    # Map package names to import names
    PKG_IMPORT_MAP = {
        "discord.py": "discord",
        "discord-ext-voice-recv": "voice_recv",
        "python-dotenv": "dotenv",
        "edge-tts": "edge_tts",
        "numpy": "numpy",
        "httpx": "httpx",
        "tavily-python": "tavily",
        "websockets": "websockets",
        "pydantic": "pydantic",
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "sqlalchemy": "sqlalchemy",
        "aiosqlite": "aiosqlite",
        "duckduckgo-search": "duckduckgo_search",
        "openai": "openai",
        "jiwer": "jiwer",
        "aiohttp": "aiohttp"
    }

    all_scan_files = code_files + [os.path.join("tests", f) for f in os.listdir("tests") if f.endswith(".py")]

    for req in reqs:
        import_name = PKG_IMPORT_MAP.get(req.lower(), req.lower().replace("-", "_"))
        pat = re.compile(r'^\s*(import\s+' + re.escape(import_name) + r'\b|from\s+' + re.escape(import_name) + r'\b)', re.MULTILINE)
        found = []
        for sf in all_scan_files:
            try:
                with open(sf, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if pat.search(content):
                        found.append(sf)
            except Exception:
                pass
        if not found:
            print(f"❌ UNUSED DEPENDENCY in requirements.txt: '{req}' (import: '{import_name}') - 0 imports across bot/, backend/, tests/")
        else:
            print(f"✅ Active dependency: '{req}' (used in {len(found)} files)")
