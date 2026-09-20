import io
import sys
import soundfile as sf
from datasets import load_dataset, Audio

sys.stdout.reconfigure(encoding="utf-8")

ds = load_dataset("MohamedRashad/MGB-3-Arabic", split="test", streaming=True)
ds = ds.cast_column("audio", Audio(decode=False))

prefixes = {}
samples_by_prefix = {}

count = 0
for item in ds:
    clip_id = item["id"]
    prefix = clip_id.split("_")[0]
    prefixes[prefix] = prefixes.get(prefix, 0) + 1
    if prefix not in samples_by_prefix:
        samples_by_prefix[prefix] = []
    if len(samples_by_prefix[prefix]) < 3:
        samples_by_prefix[prefix].append((clip_id, item["text"]))
    count += 1
    if count >= 300:
        break

print("Prefix counts in first 300 samples:")
for p, c in prefixes.items():
    print(f"  {p}: {c}")

print("\nSample texts:")
for p, samples in samples_by_prefix.items():
    print(f"\n--- Prefix: {p} ---")
    for cid, txt in samples:
        print(f"  [{cid}] -> {txt}")
