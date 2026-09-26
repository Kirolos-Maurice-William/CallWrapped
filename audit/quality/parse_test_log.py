import re
from datetime import datetime
from pathlib import Path

log_path = Path(r"C:\Users\LENOVO\.gemini\antigravity\brain\552af00a-073e-4c81-bad3-b69ef3d37a87\.system_generated\tasks\task-1174.log")
lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()

# Search for test class / test runs
time_regex = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
test_regex = re.compile(r"coro=<(\w+)\.(\w+)\(\)")

events = []
for line in lines:
    m_time = time_regex.search(line)
    if m_time:
        t_str = m_time.group(1)
        t_dt = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S,%f")
        m_test = test_regex.search(line)
        if m_test:
            events.append((t_dt, f"{m_test.group(1)}.{m_test.group(2)}"))

print(f"Captured {len(events)} test event timestamps.")
durations = []
for i in range(len(events) - 1):
    dt = (events[i+1][0] - events[i][0]).total_seconds()
    durations.append((dt, events[i][1]))

durations.sort(reverse=True)
print("\n--- TOP 10 SLOWEST TESTS FROM LOG TIMESTAMPS ---")
seen = set()
for dt, name in durations:
    if name not in seen:
        seen.add(name)
        print(f"  {dt:6.2f}s : {name}")
    if len(seen) >= 10:
        break
