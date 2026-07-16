import subprocess, json

# Use catdesk browser to take screenshot
cmd = [
    r"C:\Users\姜一鸣\.catdesk\bin\catdesk.cmd",
    "browser-action",
    json.dumps({"action": "screenshot", "path": r"M:\social-media-marketing-auto\web\screenshot.png", "fullPage": True})
]
result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
print('stdout:', result.stdout)
print('stderr:', result.stderr)
print('returncode:', result.returncode)
