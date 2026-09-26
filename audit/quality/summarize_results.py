import json
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

with open("audit/quality/deep_audit_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("=== SCRATCH FILES ===")
for item in data.get('phase1e_scratch', []):
    print(f"  {item['type']}: {item['path']} ({item['size']} bytes)")

print("\n=== MODEL NAME HITS ===")
for item in data['phase2'].get('model_hits', []):
    print(f"  {item['file']}:{item['line']}: {item['text']}")

print("\n=== BRANDING SWEEP ===")
print(f"  Voice Arbitrator count: {data['phase2']['va_hits_count']}")
for item in data['phase2']['va_hits']:
    print(f"    {item['file']}:{item['line']}: {item['text']}")

print("\n=== TODO / FIXME / XXX / HACK ===")
print(f"  Total markers: {len(data['phase2']['markers'])}")
for item in data['phase2']['markers']:
    print(f"    {item['marker']} [{item['file']}:{item['line']}]: {item['text']}")

print("\n=== DEBUG PRINTS ===")
print(f"  Total prints: {len(data['phase2']['print_hits'])}")
for item in data['phase2']['print_hits']:
    print(f"    {item['file']}:{item['line']}: {item['text']}")

print("\n=== HARDCODED IDS & MAGIC NUMBERS ===")
for item in data['phase2'].get('id_hits', []):
    print(f"    ID: {item['file']}:{item['line']}: {item['text']}")
for item in data['phase2'].get('magic_numbers', []):
    print(f"    Magic: {item['file']}:{item['line']}: {item['text']}")

print("\n=== ASYNC WITHOUT AWAIT ===")
for item in data['phase3'].get('async_no_await', []):
    print(f"    {item['file']}:{item['line']}: async def {item['name']}")

print("\n=== BLOCKING CALLS IN ASYNC ===")
for item in data['phase3'].get('blocking_calls', []):
    print(f"    {item['file']}:{item['line']} ({item['type']}): {item['text']}")

print("\n=== SILENT EXCEPTIONS ===")
print(f"  Total silent exceptions: {len(data['phase3']['silent_exceptions'])}")
for item in data['phase3']['silent_exceptions']:
    print(f"    {item['file']}:{item['line']}: {item['type']} -> {item['code']}")

print("\n=== RESOURCE LEAKS ===")
for item in data['phase3'].get('resource_leaks', []):
    print(f"    {item['file']}:{item['line']}: {item['type']} -> {item['text']}")

print("\n=== STAR IMPORTS ===")
for item in data['phase4'].get('star_imports', []):
    print(f"    {item['file']}:{item['line']}: {item['text']}")

print("\n=== HARDCODED KEYS ===")
for item in data['phase6'].get('hardcoded_keys', []):
    print(f"    {item['type']} at {item['file']}:{item['line']}")

print("\n=== CORS CONFIG ===")
for item in data['phase6'].get('cors_info', []):
    print(f"    {item['line']}: {item['text']}")
