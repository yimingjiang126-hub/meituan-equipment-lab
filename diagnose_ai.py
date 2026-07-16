# -*- coding: utf-8 -*-
"""
诊断脚本：测试 AI 内容生成链路
直接运行：python diagnose_ai.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.ai_client import AIClient, get_ai_client
from utils.paths import config_path as get_config_path

print("=" * 60)
print("AI 内容生成诊断")
print("=" * 60)

# 1. 检查配置文件
print("\n[1/4] 检查配置文件...")
cfg_path = get_config_path("settings.yaml")
print(f"  配置文件路径: {cfg_path}")
print(f"  文件存在: {os.path.exists(cfg_path)}")

import yaml
with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

or_key = cfg.get("api", {}).get("openrouter", {}).get("api_key", "")
ali_key = cfg.get("api", {}).get("aliyun", {}).get("api_key", "")

print(f"  OpenRouter API Key: {'已配置 (长度' + str(len(or_key)) + ')' if or_key else '未配置 (空)'}")
print(f"  阿里云 API Key: {'已配置 (长度' + str(len(ali_key)) + ')' if ali_key else '未配置 (空)'}")

if not or_key and not ali_key:
    print("\n  [错误] 两个 API Key 都未配置！")
    print("\n  解决方案：")
    print("  1. 访问 https://openrouter.ai 注册免费账号")
    print("  2. 进入 Settings → Keys → 点击 Create Key")
    print("  3. 复制 Key 格式类似: sk-or-v1-xxxxxxxx...")
    print("  4. 打开文件: M:\\social-media-marketing-auto\\config\\settings.yaml")
    print('  5. 修改 openrouter.api_key: "sk-or-v1-你的Key"')
    print("  6. 保存文件后重新运行「一键执行」")
    sys.exit(1)

# 2. 初始化 AIClient
print("\n[2/4] 初始化 AIClient...")
try:
    ai = AIClient()
    print(f"  Provider: {ai.provider}")
    print(f"  Model: {ai.model}")
    print(f"  Base URL: {ai.base_url}")
    print(f"  API Key 前8位: {ai.api_key[:8]}...")
except Exception as e:
    print(f"  [错误] 初始化失败: {e}")
    sys.exit(1)

# 3. 测试简单调用
print("\n[3/4] 测试简单 API 调用...")
try:
    result = ai.generate_content("请用一句话介绍美团骑手装备商城。", max_tokens=100)
    print(f"  调用成功！")
    print(f"  返回内容: {result[:100]}...")
except Exception as e:
    print(f"  [错误] 调用失败: {e}")
    # 打印更详细的异常信息
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 4. 测试完整内容生成流程
print("\n[4/4] 测试完整内容生成流程...")
from generators.content_writer import ContentWriter

writer = ContentWriter()
mock_topic = {
    "hot_topic": {"title": "夏季防晒装备热销", "rank": 1, "heat": "500万", "platform": "ecommerce"},
    "match_score": 85,
    "match_reason": "强关联：装备；强关联：防晒",
    "suggested_products": [{"name": "防晒衣", "category": "服装"}],
    "content_angles": [],
    "marketing_event": None
}

try:
    result = writer.generate_xiaohongshu_note(mock_topic)
    if result:
        print(f"  小红书笔记生成成功！")
        print(f"  标题预览: {result['content'][:50]}...")
    else:
        print("  [警告] 返回空结果，但无异常抛出")
except Exception as e:
    print(f"  [错误] 生成失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
