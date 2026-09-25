import csv
import sys
import jiwer
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

rows = list(csv.DictReader(open('audit/mgb3_exp2_c_expanded_150.csv', encoding='utf-8')))
subs = Counter()
for r in rows:
    ref = r['ref_clean']
    hyp = r['heard_clean']
    try:
        aln = jiwer.process_words(ref, hyp).alignments[0]
        r_toks = ref.split()
        h_toks = hyp.split()
        for c in aln:
            if c.type == 'substitute':
                rw = ' '.join(r_toks[c.ref_start_idx:c.ref_end_idx])
                hw = ' '.join(h_toks[c.hyp_start_idx:c.hyp_end_idx])
                subs[(hw, rw)] += 1
    except Exception as e:
        pass

print(f"Top 35 substitutions (heard -> ref):")
for (hw, rw), cnt in subs.most_common(35):
    print(f"  {cnt}x: '{hw}' -> '{rw}'")
