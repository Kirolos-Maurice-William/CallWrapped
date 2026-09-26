import ast
import os
import re
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path("g:/CallWrapper")
TESTS_DIR = REPO_ROOT / "tests"

test_files = list(TESTS_DIR.glob("test_*.py"))

vacuous_asserts = []
live_network_tests = []
disk_write_tests = []
skipped_tests = []
xfail_tests = []
total_assertions = 0

for tf in test_files:
    content = tf.read_text(encoding='utf-8', errors='ignore')
    
    # Check for skipped / xfail
    for idx, line in enumerate(content.splitlines(), 1):
        if '@unittest.skip' in line or '@pytest.mark.skip' in line:
            skipped_tests.append({"file": tf.name, "line": idx, "text": line.strip()})
        if '@unittest.expectedFailure' in line or '@pytest.mark.xfail' in line:
            xfail_tests.append({"file": tf.name, "line": idx, "text": line.strip()})

    # Check for live network calls (Groq API, Tavily API, AssemblyAI)
    if any(k in content for k in ['api.groq.com', 'api.tavily.com', 'api.assemblyai.com', 'real_groq', 'real_api', 'test_twelve_transcripts_real_groq_api']):
        live_network_tests.append(tf.name)

    # Check for real disk writes
    if any(k in content for k in ['recordings', 'open(', 'to_csv', 'Path(']) and ('write' in content or 'save' in content):
        if 'recordings' in content or 'test_session' in content:
            disk_write_tests.append(tf.name)

    # Parse AST to inspect assertions
    try:
        tree = ast.parse(content, filename=str(tf))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                total_assertions += 1
                # check if test is a constant True
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    vacuous_asserts.append({
                        "file": tf.name,
                        "line": node.lineno,
                        "assert": "assert True"
                    })
            elif isinstance(node, ast.Call):
                func_name = getattr(node.func, 'attr', getattr(node.func, 'id', ''))
                if func_name.startswith('assert'):
                    total_assertions += 1
                    if func_name == 'assertTrue':
                        if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value is True:
                            vacuous_asserts.append({
                                "file": tf.name,
                                "line": node.lineno,
                                "assert": "self.assertTrue(True)"
                            })
                    elif func_name == 'assertEqual':
                        if len(node.args) >= 2 and isinstance(node.args[0], ast.Constant) and isinstance(node.args[1], ast.Constant):
                            if node.args[0].value == node.args[1].value:
                                vacuous_asserts.append({
                                    "file": tf.name,
                                    "line": node.lineno,
                                    "assert": f"self.assertEqual({node.args[0].value}, {node.args[1].value})"
                                })
    except Exception as e:
        pass

print(f"Total test files: {len(test_files)}")
print(f"Total assertions parsed: {total_assertions}")
print(f"Vacuous assertions found: {len(vacuous_asserts)}")
for va in vacuous_asserts:
    print(f"  {va['file']}:{va['line']}: {va['assert']}")

print(f"\nSkipped tests: {len(skipped_tests)}")
for st in skipped_tests:
    print(f"  {st['file']}:{st['line']}: {st['text']}")

print(f"\nLive Network Tests ({len(live_network_tests)} files):")
for nt in sorted(set(live_network_tests)):
    print(f"  {nt}")

print(f"\nTests writing to real disk ({len(disk_write_tests)} files):")
for dt in sorted(set(disk_write_tests)):
    print(f"  {dt}")
