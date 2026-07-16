import subprocess, json, time, requests

# Step 1: Navigate to page
subprocess.run([
    r"C:\Users\姜一鸣\.catdesk\bin\catdesk.cmd",
    "browser-action",
    json.dumps({"action": "navigate", "url": "http://127.0.0.1:5000", "waitUntil": "networkidle"})
], capture_output=True, timeout=20)

time.sleep(2)

# Step 2: Fill topic input and generate titles
subprocess.run([
    r"C:\Users\姜一鸣\.catdesk\bin\catdesk.cmd",
    "browser-action",
    json.dumps({"action": "evaluate", "script": """
        document.getElementById('topic-input').value = '骑手的一天';
        document.getElementById('input-count').textContent = '5';
        aiGenerateTitles();
    """})
], capture_output=True, timeout=20)

time.sleep(6)

# Step 3: Select first title and generate body
subprocess.run([
    r"C:\Users\姜一鸣\.catdesk\bin\catdesk.cmd",
    "browser-action",
    json.dumps({"action": "evaluate", "script": """
        var list = document.getElementById('title-list');
        if (list.children.length > 0) {
            selectTitle(list.children[0], 0);
            aiGenerateBody();
        }
    """})
], capture_output=True, timeout=20)

time.sleep(6)

# Step 4: Take screenshot
cmd = [
    r"C:\Users\姜一鸣\.catdesk\bin\catdesk.cmd",
    "browser-action",
    json.dumps({"action": "screenshot", "path": r"M:\social-media-marketing-auto\web\screenshot4.png"})
]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=20)
print('Screenshot result:', result.stdout[:300])
