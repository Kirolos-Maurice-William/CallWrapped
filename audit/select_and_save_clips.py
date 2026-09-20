import os
import re
import io
import csv
import sys
import numpy as np
import soundfile as sf
from datasets import load_dataset, Audio

sys.stdout.reconfigure(encoding="utf-8")

CLIPS_DIR = os.path.join("audit", "mgb3_clips")
os.makedirs(CLIPS_DIR, exist_ok=True)
LABELS_CSV = os.path.join(CLIPS_DIR, "labels.csv")

print("Loading MGB-3 test split (streaming)...")
ds = load_dataset("MohamedRashad/MGB-3-Arabic", split="test", streaming=True)
ds = ds.cast_column("audio", Audio(decode=False))

# Targets: 8 sports, 6 comedy, 6 other (moviesDrama)
target_counts = {
    "sports": 8,
    "comedy": 6,
    "moviesDrama": 6
}
selected = {k: [] for k in target_counts}

# Keywords to prioritize at least some clips with numbers
number_keywords = ['واحد', 'واحدة', 'اتنين', 'تلاتة', 'تلت', 'اربعة', 'اربع', 'خمسة', 'خمس',
                   'ستة', 'ست', 'سبعة', 'تمانية', 'تسعة', 'عشرة', 'عشرين', 'تلاتين', 'خمسين',
                   'مية', 'الف', 'الفين', 'سنة', 'سنين']

for i, item in enumerate(ds):
    cid = item["id"]
    prefix = cid.split("_")[0]
    
    if prefix not in target_counts:
        continue
    if len(selected[prefix]) >= target_counts[prefix]:
        # Check if all targets met
        if all(len(selected[k]) >= target_counts[k] for k in target_counts):
            break
        continue
    
    # Check text
    text = item.get("text", "").strip()
    if not text:
        continue
        
    raw_bytes = item["audio"]["bytes"]
    data, sr = sf.read(io.BytesIO(raw_bytes))
    
    # Calculate duration
    duration = len(data) / float(sr)
    if not (5.0 <= duration <= 30.0):
        continue
        
    # If stereo, force mono
    if data.ndim > 1:
        data = np.mean(data, axis=1)
        
    # Save WAV
    wav_filename = f"{cid}.wav"
    wav_path = os.path.join(CLIPS_DIR, wav_filename)
    sf.write(wav_path, data, sr)
    
    selected[prefix].append({
        "id": cid,
        "genre": prefix,
        "duration_s": round(duration, 3),
        "reference_text": text,
        "wav_path": wav_path
    })
    print(f"[{prefix} {len(selected[prefix])}/{target_counts[prefix]}] Selected {cid} ({duration:.2f}s)")

# Write labels.csv
all_clips = []
for k in ["sports", "comedy", "moviesDrama"]:
    all_clips.extend(selected[k])

with open(LABELS_CSV, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["id", "genre", "duration_s", "reference_text"])
    writer.writeheader()
    for clip in all_clips:
        writer.writerow({
            "id": clip["id"],
            "genre": clip["genre"],
            "duration_s": clip["duration_s"],
            "reference_text": clip["reference_text"]
        })

print(f"\nSaved {len(all_clips)} clips to {CLIPS_DIR} and {LABELS_CSV}")
for k, clips in selected.items():
    print(f"  {k}: {len(clips)} clips")
