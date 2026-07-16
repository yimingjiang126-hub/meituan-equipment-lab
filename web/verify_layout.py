import requests

r = requests.get('http://127.0.0.1:5000/', timeout=10)
html = r.text

# Check layout modifications
checks = [
    ('grid-row:3 / span 2', '相关话题推荐 expanded'),
    ('grid-row:5', '内容生成 compact'),
    ('content-gen-top', 'content-gen-top CSS class'),
    ('analysis-focus', 'analysis-focus element'),
    ('analysis-scene', 'analysis-scene element'),
    ('analysis-interaction', 'analysis-interaction element'),
    ('full-text-preview', 'full-text-preview element'),
    ('生成正文', '生成正文 button text'),
    ('关注点', '关注点 label'),
    ('第一视角场景', '第一视角场景 label'),
    ('结尾互动', '结尾互动 label'),
    ('完整正文', '完整正文 label'),
]

print('Layout verification results:')
for keyword, desc in checks:
    found = keyword in html
    status = 'OK' if found else 'FAIL'
    print(f'  [{status}] {desc}: {found}')

# Count title items in default state
title_items = html.count('title-item')
print(f'\nTitle list items in default HTML: {title_items}')
