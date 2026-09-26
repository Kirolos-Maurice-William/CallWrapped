import ast
import json
import os
import re
import sys
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path("g:/CallWrapper")
EXCLUDE_DIRS = {'node_modules', '.next', '__pycache__', 'venv', 'out', '.git', 'dist'}

def find_files(folder, exts=('.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.md')):
    base = REPO_ROOT / folder
    if not base.exists():
        return []
    result = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            p = Path(root) / f
            if p.suffix in exts:
                result.append(p)
    return result

report = {}

# ==================== PHASE 1e: SCRATCH FILES ====================
def audit_phase1e():
    scratch_findings = []
    # Check root for one-off scripts
    for p in REPO_ROOT.glob('*'):
        if p.is_file() and p.suffix in ('.py', '.sh', '.bat', '.ps1', '.tmp', '.log', '.bak'):
            scratch_findings.append({
                "path": str(p.relative_to(REPO_ROOT)),
                "type": "root_script",
                "size": p.stat().st_size
            })
    # Check tests/ for non-test files or leftover scratchpad
    for p in (REPO_ROOT / 'tests').glob('*'):
        if p.is_file():
            name = p.name
            if not (name.startswith('test_') or name == 'conftest.py' or name == '__init__.py'):
                scratch_findings.append({
                    "path": str(p.relative_to(REPO_ROOT)),
                    "type": "non_standard_test_file",
                    "size": p.stat().st_size
                })
    # Check audit/ for leftover scratchpad vs benchmarks
    for p in (REPO_ROOT / 'audit').glob('*'):
        if p.is_file():
            scratch_findings.append({
                "path": str(p.relative_to(REPO_ROOT)),
                "type": "audit_root_file",
                "size": p.stat().st_size
            })
    return scratch_findings

report['phase1e_scratch'] = audit_phase1e()

# ==================== PHASE 2: GHOST STRINGS & CONSISTENCY ====================
def audit_phase2():
    p2 = {}
    
    # 2a: Hardcoded model strings
    model_regex = re.compile(r'\b(llama[\w\-\.]*|gemini[\w\-\.]*|universal-3\.6[\w\-\.]*|gpt-[\w\-\.]*)\b', re.IGNORECASE)
    model_hits = []
    for folder in ['bot', 'backend', 'frontend/components', 'frontend/app']:
        for f in find_files(folder):
            if f.suffix in ('.db', '.sqlite', '.sqlite3'):
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                for line_idx, line in enumerate(content.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith('#') or stripped.startswith('//'):
                        continue
                    matches = model_regex.findall(line)
                    if matches:
                        model_hits.append({
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "matches": matches,
                            "text": stripped[:120]
                        })
            except Exception:
                pass
    p2['model_hits'] = model_hits

    # 2b: Branding sweep: Voice Arbitrator vs CallWrapped
    va_regex = re.compile(r'voice[\s_-]?arbitrat', re.IGNORECASE)
    cw_regex = re.compile(r'call[\s_-]?wrap', re.IGNORECASE)
    va_hits = []
    cw_hits = []
    for folder in ['bot', 'backend', 'frontend/components', 'frontend/app', 'audit']:
        for f in find_files(folder):
            if f.suffix in ('.db', '.sqlite', '.sqlite3'):
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                for line_idx, line in enumerate(content.splitlines(), 1):
                    stripped = line.strip()
                    if va_regex.search(line):
                        va_hits.append({
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "text": stripped[:120]
                        })
                    if cw_regex.search(line):
                        cw_hits.append({
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "text": stripped[:120]
                        })
            except Exception:
                pass
    p2['va_hits_count'] = len(va_hits)
    p2['cw_hits_count'] = len(cw_hits)
    p2['va_hits'] = va_hits

    # 2c: Markers TODO/FIXME/XXX/HACK/DEBUG
    marker_regex = re.compile(r'\b(TODO|FIXME|XXX|HACK)\b')
    markers = []
    for folder in ['bot', 'backend', 'frontend/components', 'frontend/app', 'tests']:
        for f in find_files(folder):
            if f.suffix in ('.db', '.sqlite', '.sqlite3'):
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                for line_idx, line in enumerate(content.splitlines(), 1):
                    m = marker_regex.search(line)
                    if m:
                        markers.append({
                            "marker": m.group(1),
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "text": line.strip()[:120]
                        })
            except Exception:
                pass
    p2['markers'] = markers

    # 2d: Debug prints in bot/ and backend/
    print_hits = []
    for folder in ['bot', 'backend']:
        for f in find_files(folder, exts=('.py',)):
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                for line_idx, line in enumerate(content.splitlines(), 1):
                    if re.match(r'^\s*print\s*\(', line):
                        print_hits.append({
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "text": line.strip()[:120]
                        })
            except Exception:
                pass
    p2['print_hits'] = print_hits

    # 2e: Hardcoded values: Discord IDs, permissions, magic numbers
    id_regex = re.compile(r'\b\d{17,20}\b')
    id_hits = []
    magic_numbers = []
    for folder in ['bot', 'backend']:
        for f in find_files(folder, exts=('.py',)):
            content = f.read_text(encoding='utf-8', errors='ignore')
            for line_idx, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                for m in id_regex.finditer(line):
                    id_hits.append({
                        "id": m.group(0),
                        "file": str(f.relative_to(REPO_ROOT)),
                        "line": line_idx,
                        "text": stripped[:120]
                    })
                if '36718592' in line or 'permissions=' in line:
                    magic_numbers.append({
                        "file": str(f.relative_to(REPO_ROOT)),
                        "line": line_idx,
                        "text": stripped[:120]
                    })
    p2['id_hits'] = id_hits
    p2['magic_numbers'] = magic_numbers
    return p2

report['phase2'] = audit_phase2()

# ==================== PHASE 3: CORRECTNESS PATTERNS ====================
def audit_phase3():
    p3 = {}
    
    # 3a: Async issues (async def without await, blocking calls)
    async_no_await = []
    blocking_calls = []
    
    blocking_patterns = [
        (re.compile(r'\btime\.sleep\s*\('), 'time.sleep (blocking in async)'),
        (re.compile(r'\brequests\.(get|post|put|delete)\s*\('), 'requests (blocking HTTP)'),
        (re.compile(r'\burllib\.request\b'), 'urllib.request (blocking HTTP)'),
        (re.compile(r'\basyncio\.run\s*\('), 'asyncio.run (nested event loop risk)')
    ]
    
    for folder in ['bot', 'backend']:
        for f in find_files(folder, exts=('.py',)):
            content = f.read_text(encoding='utf-8', errors='ignore')
            
            try:
                tree = ast.parse(content, filename=str(f))
                for node in ast.walk(tree):
                    if isinstance(node, ast.AsyncFunctionDef):
                        has_await = any(isinstance(sub, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for sub in ast.walk(node))
                        if not has_await:
                            body = node.body
                            if len(body) == 1 and isinstance(body[0], (ast.Pass, ast.Expr)) and isinstance(getattr(body[0], 'value', None), ast.Constant):
                                continue
                            async_no_await.append({
                                "file": str(f.relative_to(REPO_ROOT)),
                                "line": node.lineno,
                                "name": node.name
                            })
            except Exception:
                pass
            
            for line_idx, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                for pat, desc in blocking_patterns:
                    if pat.search(line):
                        blocking_calls.append({
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "type": desc,
                            "text": stripped[:120]
                        })
    p3['async_no_await'] = async_no_await
    p3['blocking_calls'] = blocking_calls

    # 3b: Missing timeouts in network calls (httpx, aiohttp, edge_tts)
    network_sites = []
    for folder in ['bot', 'backend']:
        for f in find_files(folder, exts=('.py',)):
            content = f.read_text(encoding='utf-8', errors='ignore')
            for line_idx, line in enumerate(content.splitlines(), 1):
                if any(x in line for x in ['httpx.', 'aiohttp.', 'edge_tts.Communicate', 'tavily', 'AssemblyAI']):
                    has_timeout = 'timeout' in line
                    network_sites.append({
                        "file": str(f.relative_to(REPO_ROOT)),
                        "line": line_idx,
                        "text": line.strip()[:120],
                        "has_timeout_in_line": has_timeout
                    })
    p3['network_sites'] = network_sites

    # 3c: Silent exceptions: except Exception: pass, except:, or debug-only
    silent_exceptions = []
    for folder in ['bot', 'backend']:
        for f in find_files(folder, exts=('.py',)):
            content = f.read_text(encoding='utf-8', errors='ignore')
            try:
                tree = ast.parse(content, filename=str(f))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Try):
                        for handler in node.handlers:
                            h_body = handler.body
                            if len(h_body) == 1:
                                if isinstance(h_body[0], ast.Pass):
                                    exc_name = ast.unparse(handler.type) if handler.type else "bare"
                                    silent_exceptions.append({
                                        "file": str(f.relative_to(REPO_ROOT)),
                                        "line": handler.lineno,
                                        "type": f"except {exc_name}: pass",
                                        "code": "pass"
                                    })
                                elif isinstance(h_body[0], ast.Expr) and isinstance(h_body[0].value, ast.Call):
                                    call_str = ast.unparse(h_body[0].value)
                                    if 'logger.debug' in call_str:
                                        exc_name = ast.unparse(handler.type) if handler.type else "bare"
                                        silent_exceptions.append({
                                            "file": str(f.relative_to(REPO_ROOT)),
                                            "line": handler.lineno,
                                            "type": f"except {exc_name}: logger.debug only",
                                            "code": call_str[:80]
                                        })
            except Exception:
                pass
    p3['silent_exceptions'] = silent_exceptions

    # 3e: Resource leaks
    resource_leaks = []
    for folder in ['bot', 'backend']:
        for f in find_files(folder, exts=('.py',)):
            content = f.read_text(encoding='utf-8', errors='ignore')
            for line_idx, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if re.search(r'\bopen\s*\(', stripped) and not stripped.startswith('with ') and not 'with open' in stripped:
                    if not stripped.startswith('#') and 'file' in stripped:
                        resource_leaks.append({
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "type": "open() without with",
                            "text": stripped[:120]
                        })
                if 'subprocess.Popen' in stripped:
                    resource_leaks.append({
                        "file": str(f.relative_to(REPO_ROOT)),
                        "line": line_idx,
                        "type": "subprocess.Popen call",
                        "text": stripped[:120]
                    })
    p3['resource_leaks'] = resource_leaks
    return p3

report['phase3'] = audit_phase3()

# ==================== PHASE 4: STRUCTURE & READABILITY ====================
def audit_phase4():
    p4 = {}
    star_imports = []
    for folder in ['bot', 'backend', 'tests']:
        for f in find_files(folder, exts=('.py',)):
            content = f.read_text(encoding='utf-8', errors='ignore')
            for line_idx, line in enumerate(content.splitlines(), 1):
                if re.match(r'^\s*from\s+[\w\.]+\s+import\s+\*', line):
                    star_imports.append({
                        "file": str(f.relative_to(REPO_ROOT)),
                        "line": line_idx,
                        "text": line.strip()
                    })
    p4['star_imports'] = star_imports
    return p4

report['phase4'] = audit_phase4()

# ==================== PHASE 6: SECURITY & PRIVACY ====================
def audit_phase6():
    p6 = {}
    log_secret_risks = []
    for folder in ['bot', 'backend']:
        for f in find_files(folder, exts=('.py',)):
            content = f.read_text(encoding='utf-8', errors='ignore')
            for line_idx, line in enumerate(content.splitlines(), 1):
                if 'logger.' in line:
                    if any(term in line.lower() for term in ['prompt', 'transcript', 'api_key', 'token', 'raw_response', 'headers']):
                        log_secret_risks.append({
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "text": line.strip()[:140]
                        })
    p6['log_secret_risks'] = log_secret_risks

    key_patterns = [
        (re.compile(r'gsk_[A-Za-z0-9_-]{30,}'), 'Groq API Key'),
        (re.compile(r'tvly-[A-Za-z0-9_-]{20,}'), 'Tavily API Key'),
        (re.compile(r'sk-[A-Za-z0-9_-]{30,}'), 'OpenAI/Generic API Key'),
    ]
    hardcoded_keys = []
    for folder in ['bot', 'backend', 'frontend/components', 'frontend/app', 'audit', 'tests']:
        for f in find_files(folder, exts=('.py', '.ts', '.tsx', '.json', '.md', '.env.example')):
            if f.suffix in ('.db', '.sqlite'):
                continue
            content = f.read_text(encoding='utf-8', errors='ignore')
            for line_idx, line in enumerate(content.splitlines(), 1):
                for pat, desc in key_patterns:
                    m = pat.search(line)
                    if m:
                        hardcoded_keys.append({
                            "type": desc,
                            "file": str(f.relative_to(REPO_ROOT)),
                            "line": line_idx,
                            "matched": m.group(0)[:8] + '...'
                        })
    p6['hardcoded_keys'] = hardcoded_keys

    cors_info = []
    main_py = REPO_ROOT / 'backend/app/main.py'
    if main_py.exists():
        content = main_py.read_text(encoding='utf-8', errors='ignore')
        for line_idx, line in enumerate(content.splitlines(), 1):
            if 'CORSMiddleware' in line or 'allow_origins' in line:
                cors_info.append({
                    "line": line_idx,
                    "text": line.strip()
                })
    p6['cors_info'] = cors_info
    return p6

report['phase6'] = audit_phase6()

out_file = REPO_ROOT / 'audit/quality/deep_audit_results.json'
out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"Deep audit complete. Results saved to {out_file.relative_to(REPO_ROOT)}")
