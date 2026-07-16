import subprocess, json, time

# Navigate to the page
cmd1 = [
    r"C:\Users\姜一鸣\.catdesk\bin\catdesk.cmd",
    "browser-action",
    json.dumps({"action": "navigate", "url": "http://127.0.0.1:5000", "waitUntil": "networkidle"})
]
result1 = subprocess.run(cmd1, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20)
print('Navigate result:', result1.stdout[:200], result1.stderr[:200])

time.sleep(2)

# Hard reload with cache clear
cmd2 = [
    r"C:\Users\姜一鸣\.catdesk\bin\catdesk.cmd",
    "browser-action",
    json.dumps({"action": "evaluate", "script": "location.reload(true)"})
]
result2 = subprocess.run(cmd2, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20)
print('Reload result:', result2.stdout[:200], result2.stderr[:200])

time.sleep(3)

# Take screenshot
cmd3 = [
    r"C:\Users\姜一鸣\.catdesk\bin\catdesk.cmd",
    "browser-action",
    json.dumps({"action": "screenshot", "path": r"M:\social-media-marketing-auto\web\screenshot2.png"})
]
result3 = subprocess.run(cmd3, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20)
print('Screenshot result:', result3.stdout[:200], result3.stderr[:200])
