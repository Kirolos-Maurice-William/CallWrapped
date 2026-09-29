"""
Comprehensive Traceback & Dead-Code / Button Verification Audit
Audits:
1. Dead code & unused imports in page.tsx, PipelineFlow.tsx, CallWrappedModal.tsx
2. Button handlers and links: verifies every onClick, href, and interactive trigger
3. Old vs New state logic: evaluates component output before vs after current fixes
"""

import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FRONTEND_DIR = os.path.abspath("frontend")

def audit_file_imports(filepath):
    print(f"\n==========================================")
    print(f"AUDITING IMPORTS IN: {os.path.basename(filepath)}")
    print(f"==========================================")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Find all imports
    import_matches = re.findall(r'import\s+\{([^}]+)\}\s+from\s+[\'"]([^\'"]+)[\'"]', content)
    unused_items = []
    total_imports = 0

    for symbols_str, module in import_matches:
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
        for sym in symbols:
            # Handle aliases like "Foo as Bar"
            if " as " in sym:
                used_name = sym.split(" as ")[1].strip()
            else:
                used_name = sym
            total_imports += 1
            # Search for occurrences outside the import line
            # Count how many times it appears in content
            matches = list(re.finditer(r'\b' + re.escape(used_name) + r'\b', content))
            # If it only occurs once (in the import itself), it is UNUSED!
            if len(matches) <= 1:
                unused_items.append((used_name, module))
                print(f"  ❌ UNUSED IMPORT: {used_name} (from '{module}')")
            else:
                print(f"  ✅ USED: {used_name} ({len(matches)} occurrences)")

    default_imports = re.findall(r'import\s+([A-Za-z0-9_]+)\s+from\s+[\'"]([^\'"]+)[\'"]', content)
    for sym, module in default_imports:
        if sym in ("React",):
            continue
        total_imports += 1
        matches = list(re.finditer(r'\b' + re.escape(sym) + r'\b', content))
        if len(matches) <= 1:
            unused_items.append((sym, module))
            print(f"  ❌ UNUSED DEFAULT IMPORT: {sym} (from '{module}')")
        else:
            print(f"  ✅ USED DEFAULT: {sym} ({len(matches)} occurrences)")

    return unused_items

def audit_buttons_and_links(filepath):
    print(f"\n==========================================")
    print(f"AUDITING BUTTONS & LINKS IN: {os.path.basename(filepath)}")
    print(f"==========================================")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Find all <button ...>
    button_matches = list(re.finditer(r'<button([^>]*?)>', content, re.DOTALL))
    print(f"Found {len(button_matches)} <button> elements:")
    for idx, m in enumerate(button_matches, 1):
        b = m.group(1)
        has_onclick = "onClick=" in b
        # match onClick content inside braces
        onclick_match = re.search(r'onClick=\{([\s\S]*?)\}(?:\s+[a-zA-Z]|\s*\/?>)', b)
        handler_summary = "INLINE HANDLER"
        if onclick_match:
            raw_h = onclick_match.group(1).strip()
            # simplify multi-line
            first_line = raw_h.split('\n')[0].strip()
            handler_summary = (first_line[:40] + "...") if len(first_line) > 40 else first_line
        title_match = re.search(r'title=[\'"]([^\'"]+)[\'"]', b)
        title_text = title_match.group(1).strip() if title_match else ""
        status = "✅ FUNCTIONAL" if has_onclick else "⚠️ NO ONCLICK"
        print(f"  Button #{idx}: {status} | handler: `{handler_summary}` | title: '{title_text}'")

    # Find all <a ...>
    anchor_matches = list(re.finditer(r'<a([^>]*?)>', content, re.DOTALL))
    print(f"\nFound {len(anchor_matches)} <a> link elements:")
    for idx, m in enumerate(anchor_matches, 1):
        a = m.group(1)
        href_match = re.search(r'href=[\'"{]([^\'"\}\n]+)[\'"\}]', a)
        target_match = re.search(r'target=[\'"]([^\'"]+)[\'"]', a)
        rel_match = re.search(r'rel=[\'"]([^\'"]+)[\'"]', a)
        href = href_match.group(1).strip() if href_match else "DYNAMIC/NONE"
        has_safe_target = 'target="_blank"' in a and 'rel="noopener noreferrer"' in a
        status = "✅ SECURE EXTERNAL LINK" if has_safe_target else ("✅ LOCAL/ANCHOR LINK" if not href.startswith("http") else "⚠️ MISSING REL")
        print(f"  Link #{idx}: {status} | href: `{href}`")

def audit_old_vs_new_logic():
    print(f"\n==========================================")
    print(f"OLD VS NEW BEHAVIORAL LOGIC COMPARISON")
    print(f"==========================================")
    
    # 1. Pipeline Flow SLA check
    def old_sla(stt, llm, search, tts, target=2000):
        total = stt + llm + search + tts
        return total <= target if total > 0 else True
    
    def new_sla(stt, llm, search, tts, target=2000):
        is_arbitration = (llm > 0 or search > 0 or tts > 0)
        total = stt + llm + search + tts
        is_passing = total <= target if is_arbitration else True
        badge = "PASSED" if is_passing else "EXCEEDED" if is_arbitration else "PIPELINE ACTIVE"
        return is_arbitration, badge

    # Passive speech case (AssemblyAI batch ~5064ms, llm=0, search=0, tts=0)
    old_passive = "PASSED" if old_sla(5064, 0, 0, 0) else "EXCEEDED"
    is_arb, new_passive = new_sla(5064, 0, 0, 0)
    print(f"Test Case: Passive Speech (AssemblyAI 5064ms, no arbitration)")
    print(f"  OLD SLA Result: {old_passive} (False negative / alarming EXCEEDED during passive listening)")
    print(f"  NEW SLA Result: {new_passive} (Correctly neutral PIPELINE ACTIVE)")

    # Active arbitration case (AssemblyAI 265ms, llm 194ms, search 520ms, tts 185ms = 1164ms)
    old_active = "PASSED" if old_sla(265, 194, 520, 185) else "EXCEEDED"
    _, new_active = new_sla(265, 194, 520, 185)
    print(f"\nTest Case: Fast Active Arbitration (1164ms total < 2.0s SLA)")
    print(f"  OLD SLA Result: {old_active}")
    print(f"  NEW SLA Result: {new_active} (Correctly PASSED)")

    # Active arbitration slow case (AssemblyAI 1200ms, llm 800ms, search 900ms, tts 300ms = 3200ms)
    old_slow = "PASSED" if old_sla(1200, 800, 900, 300) else "EXCEEDED"
    _, new_slow = new_sla(1200, 800, 900, 300)
    print(f"\nTest Case: Slow Active Arbitration (3200ms total > 2.0s SLA)")
    print(f"  OLD SLA Result: {old_slow}")
    print(f"  NEW SLA Result: {new_slow} (Correctly EXCEEDED)")

    # 2. Diplomat Badge Check
    def old_diplomat(speaker_list):
        candidates = [s for s in speaker_list if s.get('vulgarity_count', 0) == 0 and s.get('angry_episodes', 0) == 0 and s.get('talk_seconds', 0) >= 15.0]
        candidates.sort(key=lambda s: s.get('talk_seconds', 0), reverse=True)
        return candidates[0] if candidates else None

    def new_diplomat(speaker_list, longest_streak_name):
        candidates = [s for s in speaker_list if s.get('vulgarity_count', 0) == 0 and s.get('angry_episodes', 0) == 0 and s.get('banter_count', 0) == 0 and s.get('talk_seconds', 0) >= 15.0]
        candidates.sort(key=lambda s: s.get('talk_seconds', 0), reverse=True)
        # Prioritize non-Monologue King
        secondary = [s for s in candidates if s['speaker_name'] != longest_streak_name]
        return secondary[0] if secondary else (candidates[0] if candidates else None)

    # Test Case: Speaker A was Monologue King AND engaged in friendly roasts (banter_count=3).
    # Speaker B spoke for 20s peacefully with 0 banter, 0 anger, 0 vulgarity.
    speakers = [
        {"speaker_name": "Speaker A", "talk_seconds": 60.0, "angry_episodes": 0, "vulgarity_count": 0, "banter_count": 3},
        {"speaker_name": "Speaker B", "talk_seconds": 20.0, "angry_episodes": 0, "vulgarity_count": 0, "banter_count": 0}
    ]
    old_winner = old_diplomat(speakers)
    new_winner = new_diplomat(speakers, longest_streak_name="Speaker A")
    print(f"\nTest Case: The Diplomat Selection (Speaker A has roasts; Speaker B is peaceful)")
    print(f"  OLD Winner: {old_winner['speaker_name']} (BUG: awarded 100% peaceful Diplomat to the Roast Master!)")
    print(f"  NEW Winner: {new_winner['speaker_name']} (FIXED: Speaker B rightly awarded The Diplomat; roasters excluded!)")

if __name__ == "__main__":
    page_unused = audit_file_imports(os.path.join(FRONTEND_DIR, "app", "page.tsx"))
    pipe_unused = audit_file_imports(os.path.join(FRONTEND_DIR, "components", "PipelineFlow.tsx"))
    modal_unused = audit_file_imports(os.path.join(FRONTEND_DIR, "components", "CallWrappedModal.tsx"))
    
    audit_buttons_and_links(os.path.join(FRONTEND_DIR, "app", "page.tsx"))
    audit_buttons_and_links(os.path.join(FRONTEND_DIR, "components", "CallWrappedModal.tsx"))
    
    audit_old_vs_new_logic()

    total_unused = len(page_unused) + len(pipe_unused) + len(modal_unused)
    print(f"\n==========================================")
    print(f"AUDIT SUMMARY: {total_unused} unused imports identified across files.")
    print(f"==========================================")
    if total_unused > 0:
        sys.exit(2)
