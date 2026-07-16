# -*- coding: utf-8 -*-
"""
社交媒体内容营销自动化 - Web 后端 (Flask)
"""
import os
import sys
import json
import yaml
import time
import threading
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

# 把项目根目录加入路径
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from flask import Flask, render_template, jsonify, request, send_file, Response
from flask_cors import CORS
from flask_apscheduler import APScheduler

from utils.logger import logger
from utils.file_manager import get_file_manager
from utils.paths import config_path as get_config_path, PROJECT_ROOT
from utils.ai_client import get_ai_client
from collectors.douyin_hot import DouyinHotCollector
from collectors.xiaohongshu_hot import XiaohongshuHotCollector
from collectors.ecommerce_trend import EcommerceTrendCollector
from collectors.xhs_trend import XiaohongshuTrendCollector
from generators.topic_selector import get_topic_selector
from generators.content_writer import get_content_writer
from generators.brief_generator import get_brief_generator
from generators.xhs_topic_recommender import XhsTopicRecommender
from generators.xhs_hot_rank import XhsHotRankGenerator
from generators.meigen_material import generate_material, start_generate_task, get_task_status
from outputs.excel_reporter import get_excel_reporter
from outputs.word_reporter import get_word_reporter

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))
CORS(app)

# ============ APScheduler 定时任务 ============
class SchedulerConfig:
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "Asia/Shanghai"

app.config.from_object(SchedulerConfig)
scheduler = APScheduler()
scheduler.init_app(app)

# ============ 小红书账号数据 ============
XHS_PROFILE_PATH = os.path.join(os.path.dirname(__file__), 'static', 'data', 'xhs_profile.json')
XHS_PROFILE_URL = "https://www.xiaohongshu.com/user/profile/672e12dc000000001c01aef0"

def load_xhs_profile():
    """加载小红书账号数据"""
    if not os.path.exists(XHS_PROFILE_PATH):
        return {}
    try:
        with open(XHS_PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载小红书数据失败: {e}")
        return {}

def save_xhs_profile(data):
    """保存小红书账号数据"""
    try:
        os.makedirs(os.path.dirname(XHS_PROFILE_PATH), exist_ok=True)
        with open(XHS_PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存小红书数据失败: {e}")

def update_xhs_profile():
    """使用浏览器自动化抓取小红书账号数据（粉丝、赞藏、笔记数）"""
    try:
        import subprocess
        import re

        # 先检查当前页面URL，如果不在目标页面再导航
        url_result = subprocess.run([
            "C:\\Users\\姜一鸣\\.catdesk\\bin\\catdesk.cmd", "browser-action",
            '{"action":"evaluate","script":"document.location.href"}'
        ], capture_output=True, text=True, timeout=15, encoding="utf-8", errors="ignore")
        url_output = (url_result.stdout or "") + (url_result.stderr or "")
        
        # 如果不在小红书profile页面，导航过去
        if "63048899491" not in url_output:
            subprocess.run([
                "C:\\Users\\姜一鸣\\.catdesk\\bin\\catdesk.cmd", "browser-action",
                '{"action":"navigate","url":"' + XHS_PROFILE_URL + '","waitUntil":"networkidle"}'
            ], capture_output=True, timeout=30, encoding="utf-8", errors="ignore")
            # 等待页面加载完成
            import time
            time.sleep(3)

        # 获取页面完整文本
        text_result = subprocess.run([
            "C:\\Users\\姜一鸣\\.catdesk\\bin\\catdesk.cmd", "browser-action",
            '{"action":"evaluate","script":"document.body.innerText"}'
        ], capture_output=True, text=True, timeout=15, encoding="utf-8", errors="ignore")
        page_text = (text_result.stdout or "") + (text_result.stderr or "")
        
        # 记录原始输出用于调试
        logger.debug(f"Page text length: {len(page_text)}, contains '4.6万': {'4.6万' in page_text}")
        
        # 检查页面是否加载失败
        if "未连接到服务器" in page_text or len(page_text) < 500:
            logger.warning("小红书页面加载失败，未连接到服务器，跳过本次更新")
            add_log("warning", "小红书页面加载失败，无法获取数据，保留上次数据")
            return
        
        # 加载现有数据用于对比
        old_data = load_xhs_profile()
        
        # 如果获取不到精确数据（1万+），说明可能未登录，尝试从页面DOM元素精确提取
        if "4.6万" not in page_text and "1万+" in page_text:
            logger.warning("检测到模糊数据，尝试从DOM精确提取...")
            # 通过XPath或选择器精确提取
            dom_result = subprocess.run([
                "C:\\Users\\姜一鸣\\.catdesk\\bin\\catdesk.cmd", "browser-action",
                '{"action":"evaluate","script":"(() => { const el = document.querySelector(\"div[class*=user-info]\") || document.querySelector(\"section[class*=user]\") || document.body; return el.innerText; })()"}'
            ], capture_output=True, text=True, timeout=15, encoding="utf-8", errors="ignore")
            dom_text = (dom_result.stdout or "") + (dom_result.stderr or "")
            if len(dom_text) > 50:
                page_text = dom_text
        
        # 再次检查提取后的数据是否仍然模糊
        if "1万+" in page_text and ("4.6万" in old_data.get("followers", "") or "5.4万" in old_data.get("likes_collects", "")):
            logger.warning("仍获取到模糊数据，但已有精确历史数据，保留历史数据不覆盖")
            add_log("warning", "获取到模糊数据，保留已有精确数据")
            return

        # 解析关键数据
        data = load_xhs_profile()
        data["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        # 提取粉丝数 - 支持精确数字如4.6万和模糊数字1万+
        followers_match = re.search(r'(\d+\.?\d*万\+?)\s*粉丝', page_text)
        if followers_match:
            data["followers"] = followers_match.group(1)

        # 提取赞藏数
        likes_match = re.search(r'(\d+\.?\d*万\+?)\s*获赞与收藏', page_text)
        if likes_match:
            data["likes_collects"] = likes_match.group(1)

        # 提取关注数
        following_match = re.search(r'(\d+)\s*关注', page_text)
        if following_match:
            data["following"] = following_match.group(1)

        # 获取笔记数（通过统计笔记链接数量）
        notes_result = subprocess.run([
            "C:\\Users\\姜一鸣\\.catdesk\\bin\\catdesk.cmd", "browser-action",
            '{"action":"evaluate","script":"document.querySelectorAll(\"a[href*=\\\"/explore/\\\"]\").length"}'
        ], capture_output=True, text=True, timeout=15, encoding="utf-8", errors="ignore")
        notes_output = (notes_result.stdout or "") + (notes_result.stderr or "")
        notes_match = re.search(r'(\d+)', notes_output)
        if notes_match and int(notes_match.group(1)) > 0:
            data["notes"] = notes_match.group(1)

        # 获取头像
        avatar_result = subprocess.run([
            "C:\\Users\\姜一鸣\\.catdesk\\bin\\catdesk.cmd", "browser-action",
            '{"action":"evaluate","script":"(function() { var img = document.querySelector(\"img[src*=avatar]\"); if (img) return img.src; img = document.querySelector(\".avatar img\"); return img ? img.src : null; })()"}'
        ], capture_output=True, text=True, timeout=15, encoding="utf-8", errors="ignore")
        avatar_output = (avatar_result.stdout or "") + (avatar_result.stderr or "")
        url_match = re.search(r"(https?://[^\s'\"]+)", avatar_output)
        if url_match:
            data["avatar"] = url_match.group(1)

        # 提取昵称和简介
        if "美团装备研究所" in page_text:
            data["nickname"] = "美团装备研究所"
        bio_match = re.search(r'探索不一样的骑手装备.*?认准唯一官号 其他均不是所长哦', page_text, re.DOTALL)
        if bio_match:
            data["bio"] = bio_match.group(0).replace('\n', ' ').strip()

        # 保存
        save_xhs_profile(data)
        add_log("info", f"账号数据已更新：粉丝{data.get('followers','?')}, 赞藏{data.get('likes_collects','?')}, 笔记{data.get('notes','?')}")

    except Exception as e:
        logger.error(f"更新小红书数据失败: {e}")
        add_log("error", f"小红书数据更新失败: {e}")

# 注册定时任务：每天 10:00 更新账号数据
@scheduler.task('cron', id='update_xhs_profile', hour=10, minute=0)
def scheduled_update_xhs():
    add_log("info", "定时任务：开始更新小红书账号数据...")
    update_xhs_profile()

# 注册定时任务：每天 0:05 更新趋势数据
@scheduler.task('cron', id='update_xhs_trend', hour=0, minute=5)
def scheduled_update_xhs_trend():
    add_log("info", "定时任务：开始更新小红书趋势数据...")
    try:
        cfg = load_config()
        trend_cfg = cfg.get("xhs_trend_api", {})
        collector = XiaohongshuTrendCollector(trend_cfg)
        collector.collect()
        add_log("info", "小红书趋势数据已更新")
    except Exception as e:
        add_log("error", f"小红书趋势数据更新失败: {e}")

# 注册定时任务：每天 10:00 更新小红书话题推荐
@scheduler.task('cron', id='update_xhs_topics', hour=10, minute=0)
def scheduled_update_xhs_topics():
    add_log("info", "定时任务：开始生成小红书话题推荐...")
    try:
        recommender = XhsTopicRecommender()
        recommender.generate(use_ai=True)
        add_log("info", "小红书话题推荐已更新（10条装备相关话题）")
    except Exception as e:
        add_log("error", f"小红书话题推荐更新失败: {e}")

# 注册定时任务：每天 10:00 更新小红书热点榜单
@scheduler.task('cron', id='update_xhs_hot_rank', hour=10, minute=0)
def scheduled_update_xhs_hot_rank():
    add_log("info", "定时任务：开始更新小红书热点榜单...")
    try:
        generator = XhsHotRankGenerator()
        generator.generate()
        add_log("info", "小红书热点榜单已更新（前一日Top10热梗/热点/BGM）")
    except Exception as e:
        add_log("error", f"小红书热点榜单更新失败: {e}")

scheduler.start()

# ============ 全局状态 ============
app_state = {
    "collecting": False,
    "generating": False,
    "last_collect_time": None,
    "last_generate_time": None,
    "logs": [],
    "current_hot_data": {},
    "current_topics": [],
    "current_contents": [],
    "current_briefs": [],
    "task_status": "idle",
    "daily_task": {"enabled": False, "time": "09:00"}
}

MAX_LOGS = 200

def add_log(level, msg):
    entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "level": level, "msg": str(msg)}
    app_state["logs"].append(entry)
    if len(app_state["logs"]) > MAX_LOGS:
        app_state["logs"] = app_state["logs"][-MAX_LOGS:]

# ============ 工具函数 ============
def load_config():
    cfg_path = get_config_path("settings.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def save_config(cfg):
    cfg_path = get_config_path("settings.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)

def load_marketing_calendar():
    cal_path = get_config_path("marketing_calendar.yaml")
    with open(cal_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_latest_output_dir():
    out_dir = os.path.join(PROJECT_DIR, "outputs_daily")
    if not os.path.exists(out_dir):
        return None
    dirs = [d for d in os.listdir(out_dir) if os.path.isdir(os.path.join(out_dir, d)) and d.isdigit()]
    if not dirs:
        return None
    dirs.sort(reverse=True)
    return os.path.join(out_dir, dirs[0])

def get_all_output_dirs():
    out_dir = os.path.join(PROJECT_DIR, "outputs_daily")
    if not os.path.exists(out_dir):
        return []
    dirs = []
    for d in os.listdir(out_dir):
        dpath = os.path.join(out_dir, d)
        if os.path.isdir(dpath) and d.isdigit():
            dirs.append({"name": d, "path": dpath, "display": f"{d[:4]}-{d[4:6]}-{d[6:]}"})
    dirs.sort(key=lambda x: x["name"], reverse=True)
    return dirs

# ============ API 路由 ============

@app.route("/")
def index():
    return render_template("index.html")

# ---- 小红书账号数据 ----
@app.route("/api/xhs-profile")
def api_xhs_profile():
    """获取小红书账号数据"""
    data = load_xhs_profile()
    return jsonify(data)

@app.route("/api/xhs-profile/update", methods=["POST"])
def api_xhs_profile_update():
    """手动触发小红书账号数据更新"""
    def do_update():
        update_xhs_profile()
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"status": "started", "msg": "小红书数据更新任务已启动"})

# ---- 小红书账号趋势数据 ----
@app.route("/api/xhs-trend")
def api_xhs_trend():
    """获取小红书账号热度趋势数据（近24小时）"""
    try:
        cfg = load_config()
        trend_cfg = cfg.get("xhs_trend_api", {})
        collector = XiaohongshuTrendCollector(trend_cfg)
        data = collector.get_chart_data()
        return jsonify(data)
    except Exception as e:
        logger.error(f"获取趋势数据失败: {e}")
        return jsonify({"error": str(e), "hours": [], "values": [], "peak": 0}), 500

@app.route("/api/xhs-trend/update", methods=["POST"])
def api_xhs_trend_update():
    """手动触发小红书趋势数据更新"""
    def do_update():
        try:
            cfg = load_config()
            trend_cfg = cfg.get("xhs_trend_api", {})
            collector = XiaohongshuTrendCollector(trend_cfg)
            collector.collect()
            add_log("info", "小红书趋势数据已更新")
        except Exception as e:
            add_log("error", f"小红书趋势数据更新失败: {e}")
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"status": "started", "msg": "小红书趋势数据更新任务已启动"})

# ---- 小红书每日话题推荐 ----
@app.route("/api/xhs-topics")
def api_xhs_topics():
    """获取每日小红书话题推荐（10条装备相关话题方向）"""
    try:
        recommender = XhsTopicRecommender()
        topics = recommender.get_topics(use_ai=True)
        return jsonify({
            "topics": topics,
            "total": len(topics),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        logger.error(f"获取话题推荐失败: {e}")
        return jsonify({"error": str(e), "topics": [], "total": 0}), 500

@app.route("/api/xhs-topics/update", methods=["POST"])
def api_xhs_topics_update():
    """手动触发小红书话题推荐更新"""
    def do_update():
        try:
            recommender = XhsTopicRecommender()
            recommender.generate(use_ai=True)
            add_log("info", "小红书话题推荐已更新")
        except Exception as e:
            add_log("error", f"小红书话题推荐更新失败: {e}")
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"status": "started", "msg": "小红书话题推荐更新任务已启动，约10秒后刷新查看最新内容"})

# ---- 小红书热点榜单 ----
@app.route("/api/xhs-rank")
def api_xhs_rank():
    """获取前一日小红书热点榜单（Top10：热梗/热点/BGM）"""
    try:
        generator = XhsHotRankGenerator()
        items = generator.get_rank()
        return jsonify({
            "items": items,
            "total": len(items),
            "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        })
    except Exception as e:
        logger.error(f"获取热点榜单失败: {e}")
        return jsonify({"error": str(e), "items": [], "total": 0}), 500

@app.route("/api/xhs-rank/update", methods=["POST"])
def api_xhs_rank_update():
    """手动触发小红书热点榜单更新"""
    def do_update():
        try:
            generator = XhsHotRankGenerator()
            generator.generate()
            add_log("info", "小红书热点榜单已手动更新")
        except Exception as e:
            add_log("error", f"小红书热点榜单更新失败: {e}")
    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"status": "started", "msg": "小红书热点榜单更新任务已启动，约10秒后刷新查看最新内容"})

# ---- 美境 AI 设计师 - 物料生成 ----
@app.route("/api/generate-material", methods=["POST"])
def api_generate_material():
    """提交美境 AI 物料生成任务"""
    try:
        prompt = request.form.get("prompt", "")
        
        if not prompt:
            return jsonify({"error": "图片生成描述不能为空"}), 400
        
        # 保存上传的图片（支持多张）
        image_paths = []
        if "image" in request.files:
            files = request.files.getlist("image")
            for file in files:
                if file.filename:
                    ext = os.path.splitext(file.filename)[1] or ".png"
                    tmp_dir = os.path.join(PROJECT_ROOT, "web", "static", "uploads")
                    os.makedirs(tmp_dir, exist_ok=True)
                    import uuid
                    img_path = os.path.join(tmp_dir, f"mat_{uuid.uuid4().hex[:8]}{ext}")
                    file.save(img_path)
                    image_paths.append(img_path)
        
        # 生成任务 ID
        import uuid
        task_id = f"mat_{uuid.uuid4().hex[:8]}"
        
        # 启动后台任务（传入 prompt 和多张图片路径）
        start_generate_task(task_id, "1080", "1920", "", "", "", image_paths, prompt)
        
        return jsonify({
            "status": "started",
            "task_id": task_id,
            "msg": "美境 AI 设计师任务已提交，正在生成中..."
        })
    except Exception as e:
        logger.error(f"物料生成任务提交失败: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate-material/status/<task_id>")
def api_generate_material_status(task_id: str):
    """查询物料生成任务状态"""
    try:
        status = get_task_status(task_id)
        return jsonify(status)
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        return jsonify({"status": "failed", "error": str(e)}), 500

# ---- AI 内容生成（标题 + 正文） ----
def _ai_generate_titles(topic_direction: str) -> list:
    """AI 生成标题列表，遵循 xhs-content-creator 规范，18字以内，有趣吸引人"""
    ai = get_ai_client()
    prompt = f'''你是"美团装备研究所"的内容运营官，专门为小红书平台创作骑手装备/生活相关的内容标题。

请为以下话题方向生成 10 个小红书笔记标题：
话题方向：{topic_direction}

要求：
1. 每个标题严格控制在 18 个字以内（含标点符号），适合小红书信息流展示
2. 标题必须有趣、有料、捕捉热点或关键信息，让人一眼就想点进去看
3. 风格多样化：悬念型、反转型、共鸣型、吐槽型、好奇型、现场型、观点型等
4. 结合骑手真实生活场景，口语化表达，像朋友聊天不是广告
5. 一次输出 10 个，风格各不相同，覆盖不同受众兴趣点

红线原则（必须遵守）：
- 坚决不聊价格：标题中不要出现价格、多少钱、省钱、平价、性价比等字眼
- 不做硬广推销：不用"必买""赶紧入""冲冲冲""强烈推荐"等推销语气
- 不堆砌专业术语：把装备名词翻译成人话，让读者秒懂

请严格按以下 JSON 数组格式返回，不要包含其他文字：
[
  {{"title": "标题1", "type": "悬念型"}},
  {{"title": "标题2", "type": "反转型"}}
]
'''
    result = ai.generate_content(prompt, temperature=0.85, max_tokens=2000)
    try:
        start_idx = result.find("[")
        end_idx = result.rfind("]")
        if start_idx != -1 and end_idx != -1:
            json_str = result[start_idx:end_idx + 1]
            titles = json.loads(json_str)
            for i, t in enumerate(titles, 1):
                t["id"] = i
            return titles[:10]
    except Exception:
        pass
    return []


def _ai_generate_body(title: str, topic_direction: str, title_type: str = "") -> dict:
    """AI 生成正文内容，遵循 xhs-content-creator 规范：内容分析+完整正文"""
    ai = get_ai_client()
    style_hint = f"\n标题风格：{title_type}（请根据该风格调整正文语气）" if title_type else ""
    prompt = f'''你是"美团装备研究所"的内容运营官，以"所长"第一人称身份写小红书笔记。

请为以下标题生成内容分析和完整正文：
标题：{title}
话题方向：{topic_direction}{style_hint}

【输出格式 — 严格按以下 JSON 返回】
{{
  "focus": "内容关注点（1-2句话）：这篇笔记的核心看点是什么，为什么读者会感兴趣，用口语化表达",
  "scene": "第一视角场景（2-3句话）：以所长身份描述一个真实的骑手生活场景，有画面感、有细节、有代入感，让读者仿佛身临其境",
  "interaction": "结尾互动（1-2句话）：设计一个自然的评论区互动话题，引导读者留言，不要生硬、不要套路",
  "full_text": "完整正文（300-500字）：一篇完整、连贯、有逻辑的小红书笔记，不是四段机械拼接，而是自然流畅的文章。要求：1.以所长第一人称视角；2.有真实故事/经历分享；3.内容积极向上；4.不是人机味，像朋友聊天；5.口语化、有情感递进；6.适当加入1-2个生活化emoji；7.段与段之间有过渡衔接；8.不提价格、不硬广推销"
}}

【内容风格规范 — 必须遵守】
- 人设：所长是真实骑手，不是品牌方/客服/广告文案，可以吐槽、可以有小惊喜
- 语气：幽默有趣、口语化、像跟兄弟聊天，善用反转和自嘲
- 场景：融入具体送单场景（等红灯、爬楼梯、暴晒骑行、夜间配送、被顾客搭话）
- 有细节感："汗湿的后背""兜里揣手机""车灯一照就亮"
- 有时间感："跑了一整天""35度的午后""凌晨收工"

【红线原则】
- 坚决不聊价格：不要出现价格、多少钱、省钱、平价、性价比等字眼
- 不做硬广推销：不直接推销具体产品，不用"强烈推荐""赶紧买""冲冲冲"等话术
- 禁用模板句式："在当今XX的时代""不得不说""值得深思""让我们一起""关键在于""核心秘诀"
- 禁用居高临下："我告诉你""你们新人啊""听我一句劝"
- 禁用小白味："我也不确定""我在纠结"
- 禁用引流收尾："想了解详情后台滴滴""现在正是好时机"

请严格按 JSON 格式返回，不要包含其他文字。'''
    result = ai.generate_content(prompt, temperature=0.8, max_tokens=2000)
    try:
        start_idx = result.find("{")
        end_idx = result.rfind("}")
        if start_idx != -1 and end_idx != -1:
            json_str = result[start_idx:end_idx + 1]
            return json.loads(json_str)
    except Exception:
        pass
    return {}


# ---- 规则生成兜底（AI 不可用时） ----
def _rule_generate_titles(topic_direction: str) -> list:
    """基于规则模板生成标题列表，无需 API。以所长第一视角，幽默有趣，不聊价格，不硬广。"""
    import random

    # 装备关键词 + 场景/需求关键词
    # 按长度从高到低排序，优先匹配更具体的词
    gear_keywords = {
        "袋鼠耳朵": ["袋鼠耳朵", "耳朵头盔"],
        "蓝牙耳机": ["蓝牙耳机", "耳机"],
        "手机支架": ["手机支架", "导航支架"],
        "防晒衣": ["防晒衣", "防晒服"],
        "头盔": ["头盔", "夏盔", "安全帽"],
        "手套": ["手套", "骑行手套"],
        "雨衣": ["雨衣", "雨披"],
        "餐箱": ["餐箱", "保温箱", "外卖箱"],
        "护膝": ["护膝"],
        "面罩": ["面罩", "防晒面罩"],
        "冰袖": ["冰袖", "防晒袖"],
    }
    # 按关键词长度从高到低排序，长的优先匹配（更具体的优先）
    sorted_gears = sorted(gear_keywords.items(), key=lambda x: -len(x[0]))

    scene_keywords = {
        "防晒": ["防晒", "遮阳", "紫外线", "晒黑", "晒伤"],
        "降温": ["降温", "凉快", "清凉", "散热", "透气", "闷热"],
        "防雨": ["防雨", "防水", "雨天", "暴雨", "淋雨"],
        "防滑": ["防滑", "抓地", "摩擦力"],
        "保暖": ["保暖", "防风", "御寒", "冬天", "冬季"],
        "轻便": ["轻便", "轻量", "减重", "不累", "省力"],
        "耐用": ["耐用", "结实", "耐造", "抗造", "扛造"],
        "舒适": ["舒适", "舒服", "贴合", "不勒", "不痛"],
        "安全": ["安全", "防护", "保护", "保命", "事故"],
    }

    # 通用修饰词（用于提取核心话题时过滤）
    filter_words = ["美团", "推荐", "攻略", "指南", "选购", "怎么选", "如何选择", "外卖", "测评", "开箱", "对比", "清单", "盘点"]
    season_words = ["夏季", "冬季", "春天", "秋天", "四季", "新款", "热门", "网红", "爆款"]

    def _find_best_gear(text):
        """在文本中查找最佳匹配的装备词，返回 (装备词, 匹配到的别名, 在文本中的位置)"""
        for gear, aliases in sorted_gears:
            for a in aliases:
                pos = text.find(a)
                if pos != -1:
                    return gear, a, pos
        return None, None, -1

    def _find_best_scene(text):
        """在文本中查找最佳匹配的场景词，返回 (场景词, 匹配到的别名, 在文本中的位置)"""
        best_pos = len(text)
        best_scene = None
        best_alias = None
        for scene, aliases in scene_keywords.items():
            for a in aliases:
                pos = text.find(a)
                if pos != -1 and pos < best_pos:
                    best_pos = pos
                    best_scene = scene
                    best_alias = a
        return best_scene, best_alias, best_pos

    def _extract_prefix(text, pos):
        """提取装备词前面的有效修饰词，如 '带灯头盔' 中的 '带灯'"""
        if pos <= 0:
            return ""
        prefix = text[:pos].strip()
        # 去掉连接词和常见修饰词
        for w in ["的", "和", "与", "用", "式", "型", "款", "的"]:
            prefix = prefix.replace(w, "")
        prefix = prefix.strip()
        # 如果前缀不是过滤词，保留它
        if prefix and prefix not in filter_words + season_words + ["骑手", "外卖"]:
            return prefix
        return ""

    # 1. 识别装备
    matched_gear, gear_alias, gear_pos = _find_best_gear(topic_direction)

    # 2. 识别场景
    matched_scene, scene_alias, scene_pos = _find_best_scene(topic_direction)

    # 3. 提取装备前的修饰词（如：带灯头盔 → "带灯"）
    gear_prefix = _extract_prefix(topic_direction, gear_pos) if gear_pos > 0 else ""

    # 4. 检查场景词是否被包含在装备词中（如"防晒"在"防晒衣"中）
    if matched_scene and matched_gear and (scene_alias in matched_gear or matched_scene in matched_gear):
        matched_scene = None

    # 5. 检查场景词是否被包含在装备修饰词中
    if matched_scene and gear_prefix and (scene_alias in gear_prefix or matched_scene in gear_prefix):
        matched_scene = None

    # 6. 构建主题词
    if matched_gear and matched_scene:
        # 场景 + 修饰词 + 装备（如：防雨 + 带灯 + 头盔）
        if matched_scene in matched_gear:
            topic = matched_gear
        else:
            topic = matched_scene + matched_gear
        if gear_prefix and gear_prefix not in topic:
            topic = gear_prefix + topic
    elif matched_gear:
        topic = gear_prefix + matched_gear if gear_prefix else matched_gear
        # 检查匹配gear后面是否还有基础装备词（如"袋鼠耳朵"后接"头盔"）
        suffix_pos = gear_pos + len(gear_alias)
        if suffix_pos < len(topic_direction):
            suffix_text = topic_direction[suffix_pos:].strip()
            # 去掉常见连接词
            for w in ["的", "和", "与", "用", "式", "型", "款"]:
                suffix_text = suffix_text.replace(w, "")
            suffix_text = suffix_text.strip()
            # 基础装备词列表
            base_gears = ["头盔", "手套", "护膝", "面罩", "支架", "雨衣", "餐箱", "冰袖", "耳机"]
            for bg in base_gears:
                if bg in suffix_text and bg not in matched_gear:
                    topic += bg
                    break
    elif matched_scene:
        topic = matched_scene
    else:
        # 没有匹配到任何关键词，通用话题模式：只过滤极少量通用词，保留核心概念
        topic = topic_direction.strip()
        for word in ["美团", "推荐", "攻略", "指南", "怎么选", "如何选择"]:
            topic = topic.replace(word, "")
        topic = topic.strip()
        # 如果过滤后为空或只剩1个字，回退到原始话题（过滤掉纯通用词）
        if not topic or len(topic) <= 1:
            topic = topic_direction.strip()
            for word in ["美团", "推荐", "攻略", "指南"]:
                topic = topic.replace(word, "")
            topic = topic.strip() if topic.strip() else topic_direction.strip()

    # 7. 清理重复（如"防晒防晒衣" → "防晒衣"）
    if matched_scene and matched_gear and topic.startswith(matched_scene) and matched_gear.startswith(matched_scene):
        topic = gear_prefix + matched_gear if gear_prefix else matched_gear

    # 8. 根据话题类型选择标题模板
    is_gear_topic = matched_gear is not None or matched_scene is not None

    if is_gear_topic:
        # 装备类话题：丰富多样的模板，不都带所长，不做硬广
        templates = [
            ("疑问式", f"骑手{topic}怎么选？看完少踩一半坑"),
            ("疑问式", f"你的{topic}选对了吗？评论区聊聊"),
            ("吐槽式", f"{topic}踩坑实录｜这份学费交得太冤枉"),
            ("吐槽式", f"买{topic}前必看，这些坑所长替你们踩过了"),
            ("攻略式", f"{topic}选购不聊虚的，只说真实体验"),
            ("攻略式", f"{topic}怎么选？这几点比参数更重要"),
            ("体验式", f"亲测30天{topic}：从嫌弃到真香，经历了什么"),
            ("体验式", f"用了{topic}一个月，说说真实感受"),
            ("测评式", f"{topic}真实测评｜结论有点意外"),
            ("测评式", f"测了这么多{topic}，这款让我没想到"),
            ("互动式", f"{topic}你最看重啥？舒服还是耐造？"),
            ("互动式", f"关于{topic}，骑手们最有发言权"),
            ("场景式", f"{topic}实战测试，效果竟然…"),
            ("场景式", f"极端天气下{topic}的表现，有点意思"),
            ("冷知识", f"{topic}冷知识｜90%骑手不知道这些"),
            ("冷知识", f"关于{topic}的隐藏用法，白嫖体验升级"),
            ("对比式", f"{topic}对比｜差别比想象中大"),
            ("对比式", f"{topic}的买家秀vs卖家秀，太真实了"),
            ("穿搭式", f"{topic}也能搭好看？骑手穿搭小心机"),
            ("穿搭式", f"谁说骑手不能精致？{topic}这样选"),
        ]
    else:
        # 通用话题：完全口语化、幽默、有共鸣，不套模板，避免"骑手"重复
        templates = [
            ("共鸣式", f"{topic}这件事，真的只有跑单的人才懂"),
            ("共鸣式", f"小哥的{topic}日常，笑不活了"),
            ("幽默式", f"关于{topic}，有些话不得不说"),
            ("幽默式", f"{topic}这个事儿，劝你别太认真"),
            ("讨论式", f"{topic}火了，大家怎么看？"),
            ("讨论式", f"当{topic}遇上外卖骑手，画风变成这样"),
            ("真实式", f"{topic}的真实情况，看完太真实了"),
            ("真实式", f"聊聊{topic}的真实情况，是这样的"),
            ("好奇式", f"{topic}有多离谱？真相来了"),
            ("好奇式", f"{topic}的真相，可能跟你想的不一样"),
            ("现场式", f"{topic}现场，离谱又好笑"),
            ("现场式", f"当{topic}遇到现实，结果亮了"),
            ("故事式", f"{topic}背后，是每个外卖人的日常"),
            ("故事式", f"{topic}实录，看完太有共鸣"),
            ("观点式", f"关于{topic}，大家的反应绝了"),
            ("观点式", f"{topic}的N种打开方式，你选哪种"),
            ("轻松式", f"{topic}现场观察，结果让人意外"),
            ("轻松式", f"关于{topic}，有话要说"),
            ("感叹式", f"{topic}这个事儿，看完我沉默了"),
            ("感叹式", f"{topic}现场，太有画面感了"),
        ]
    random.shuffle(templates)
    titles = []
    for i, (t_type, title) in enumerate(templates[:10], 1):
        titles.append({"id": i, "title": title, "type": t_type})
    return titles
def _rule_generate_body(title: str, topic_direction: str, title_type: str = "") -> dict:
    """基于规则模板生成正文结构，无需 API。以所长第一视角，幽默有趣，不聊价格，不硬广。"""
    import random

    gear_keywords = {
        "袋鼠耳朵": ["袋鼠耳朵", "耳朵头盔"],
        "蓝牙耳机": ["蓝牙耳机", "耳机"],
        "手机支架": ["手机支架", "导航支架"],
        "防晒衣": ["防晒衣", "防晒服"],
        "头盔": ["头盔", "夏盔", "安全帽"],
        "手套": ["手套", "骑行手套"],
        "雨衣": ["雨衣", "雨披"],
        "餐箱": ["餐箱", "保温箱", "外卖箱"],
        "护膝": ["护膝"],
        "面罩": ["面罩", "防晒面罩"],
        "冰袖": ["冰袖", "防晒袖"],
    }
    sorted_gears = sorted(gear_keywords.items(), key=lambda x: -len(x[0]))

    scene_keywords = {
        "防晒": ["防晒", "遮阳", "紫外线", "晒黑", "晒伤"],
        "降温": ["降温", "凉快", "清凉", "散热", "透气", "闷热"],
        "防雨": ["防雨", "防水", "雨天", "暴雨", "淋雨"],
        "防滑": ["防滑", "抓地", "摩擦力"],
        "保暖": ["保暖", "防风", "御寒", "冬天", "冬季"],
        "轻便": ["轻便", "轻量", "减重", "不累", "省力"],
        "耐用": ["耐用", "结实", "耐造", "抗造", "扛造"],
        "舒适": ["舒适", "舒服", "贴合", "不勒", "不痛"],
        "安全": ["安全", "防护", "保护", "保命", "事故"],
    }

    filter_words = ["美团", "推荐", "攻略", "指南", "选购", "怎么选", "如何选择", "外卖", "测评", "开箱", "对比", "清单", "盘点"]
    season_words = ["夏季", "冬季", "春天", "秋天", "四季", "新款", "热门", "网红", "爆款"]

    def _find_best_gear(text):
        for gear, aliases in sorted_gears:
            for a in aliases:
                pos = text.find(a)
                if pos != -1:
                    return gear, a, pos
        return None, None, -1

    def _find_best_scene(text):
        best_pos = len(text)
        best_scene = None
        best_alias = None
        for scene, aliases in scene_keywords.items():
            for a in aliases:
                pos = text.find(a)
                if pos != -1 and pos < best_pos:
                    best_pos = pos
                    best_scene = scene
                    best_alias = a
        return best_scene, best_alias, best_pos

    def _extract_prefix(text, pos):
        if pos <= 0:
            return ""
        prefix = text[:pos].strip()
        for w in ["的", "和", "与", "用", "式", "型", "款", "的"]:
            prefix = prefix.replace(w, "")
        prefix = prefix.strip()
        if prefix and prefix not in filter_words + season_words + ["骑手", "外卖"]:
            return prefix
        return ""

    combined_text = title + topic_direction

    matched_gear, gear_alias, gear_pos = _find_best_gear(combined_text)
    matched_scene, scene_alias, scene_pos = _find_best_scene(combined_text)
    gear_prefix = _extract_prefix(combined_text, gear_pos) if gear_pos > 0 else ""

    if matched_scene and matched_gear and (scene_alias in matched_gear or matched_scene in matched_gear):
        matched_scene = None
    if matched_scene and gear_prefix and (scene_alias in gear_prefix or matched_scene in gear_prefix):
        matched_scene = None

    if matched_gear and matched_scene:
        if matched_scene in matched_gear:
            item = matched_gear
        else:
            item = matched_scene + matched_gear
        if gear_prefix and gear_prefix not in item:
            item = gear_prefix + item
    elif matched_gear:
        item = gear_prefix + matched_gear if gear_prefix else matched_gear
        # 检查匹配gear后面是否还有基础装备词（如"袋鼠耳朵"后接"头盔"）
        suffix_pos = gear_pos + len(gear_alias)
        combined_len = len(combined_text)
        if suffix_pos < combined_len:
            suffix_text = combined_text[suffix_pos:].strip()
            for w in ["的", "和", "与", "用", "式", "型", "款"]:
                suffix_text = suffix_text.replace(w, "")
            suffix_text = suffix_text.strip()
            base_gears = ["头盔", "手套", "护膝", "面罩", "支架", "雨衣", "餐箱", "冰袖", "耳机"]
            for bg in base_gears:
                if bg in suffix_text and bg not in matched_gear:
                    item += bg
                    break
    elif matched_scene:
        item = matched_scene
    else:
        item = topic_direction.strip() if topic_direction.strip() else "装备"
        for word in ["美团", "推荐", "攻略", "指南", "怎么选", "如何选择"]:
            item = item.replace(word, "")
        item = item.strip()
        if not item or len(item) <= 1:
            item = topic_direction.strip()
            for word in ["美团", "推荐", "攻略", "指南"]:
                item = item.replace(word, "")
            item = item.strip() if item.strip() else topic_direction.strip()

    if matched_scene and matched_gear and item.startswith(matched_scene) and matched_gear.startswith(matched_scene):
        item = gear_prefix + matched_gear if gear_prefix else matched_gear
        item = item.strip() if item.strip() else "装备"

    # 判断是否为装备类话题
    is_gear_topic = matched_gear is not None or matched_scene is not None

    def _build_full_text(p, s, sc, i, is_gear):
        """将四段模板拼接成完整的正文，加入过渡衔接，避免机械拼接"""
        import random
        # pain → solution 衔接
        if is_gear:
            t1 = random.choice([
                "说到这个，所长多说两句。",
                "接着聊聊实际感受。",
                "话说回来，选装备这事吧。",
                "扯远了，说回正题。",
                "后来所长发现，事情没那么简单。",
            ])
        else:
            t1 = random.choice([
                "接着说，这事儿还有后文。",
                "后来所长想想，其实挺有意思的。",
                "扯回正题，所长再聊几句。",
                "说到这个，所长还有几个观察。",
                "然后所长发现，背后还有不少门道。",
            ])
        # solution → scene 衔接
        if is_gear:
            t2 = random.choice([
                "举个例子，有一次所长印象特别深。",
                "印象最深的一次经历是这样的。",
                "有次跑单，所长亲身经历了一件事。",
                "说个真实的事，所长那次差点翻车。",
            ])
        else:
            t2 = random.choice([
                "有次跑单，所长亲眼看到一件事。",
                "说个真实经历，所长那次印象挺深。",
                "举个例子，那天午高峰所长正好在场。",
                "有次亲身经历，所长到现在还记得。",
            ])
        # scene → interaction 衔接
        if is_gear:
            t3 = random.choice([
                "说到底，装备只是工具。",
                "说到底，适合自己的才是最好的。",
                "所以你看，选装备这事急不得。",
                "最后所长想说的是，别被表面参数忽悠了。",
            ])
        else:
            t3 = random.choice([
                "说到底，骑手的生活就是这样。",
                "所以你看，事情没那么复杂。",
                "说到底，真实比啥都有力。",
                "最后所长想留白，不多说了。",
            ])
        return f"{p}\n\n{t1}{s}\n\n{t2}{sc}\n\n{t3}{i}"

    if not is_gear_topic:
        # 通用话题模板（不围绕装备购买/使用，避免"选骑手的一天"这种逻辑不通的内容）
        # 每段开头使用不同表达方式，避免重复
        general_pain = {
            "共鸣式": f"说到{item}，所长真的有很多话想说。这不是什么高大上的话题，就是咱们骑手日常里真实发生的事。",
            "幽默式": f"说到{item}，所长忍不住想笑。因为这事儿真的挺离谱的，不亲身经历你根本想象不到。",
            "讨论式": f"关于{item}，骑手群里最近讨论挺多的。所长也凑个热闹，说说自己的看法。",
            "真实式": f"今天聊点真实的——{item}。所长不说虚的，就是把自己看到的、感受到的如实说出来。",
            "好奇式": f"所长一直对{item}挺好奇的，真正深入了解之后，发现跟大家想的不太一样。",
            "现场式": f"想象一下{item}的现场，所长到现在还记得那个画面。有紧张、有无奈，也有那么一点点搞笑。",
            "故事式": f"关于{item}，所长脑子里有一段故事。不是什么惊心动魄的大事，就是骑手日常里的小片段。",
            "观点式": f"对于{item}，所长有自己的看法。不一定对，但绝对是真实感受。",
            "轻松式": f"今天聊个轻松的话题——{item}。所长随便说说，你们随便听听。",
            "感叹式": f"{item}这件事，每次想起来所长都会沉默一会儿。不是因为难过，就是觉得太真实了。",
        }
        general_solution = {
            "共鸣式": f"每个人的理解都不一样。有人觉得是苦差事，有人觉得挺有意思。所长今天就把自己的真实感受拿出来聊聊。",
            "幽默式": f"所长总结了几个有意思的点。不是攻略，就是纯粹的观察和吐槽。听完你可能也会会心一笑。",
            "讨论式": f"所长觉得这件事吧，没有标准答案。不同的骑手有不同的经历，不同的感受。今天就是把几种典型的视角拿出来聊聊。",
            "真实式": f"所长跑单这些年，积累了不少真实观察。有些细节不跑单的人根本注意不到，但骑手们看了一定会点头。",
            "好奇式": f"带着好奇心去观察，所长发现了很多平时忽略的细节。原来这件事背后还有这么多值得聊的。",
            "现场式": f"所长印象最深的是那些不经意的瞬间。比如午高峰时的忙碌，或者雨天配送时的紧张。这些画面构成了骑手生活的真实底色。",
            "故事式": f"所长把这个故事讲出来，不是想煽情，就是想让大家看到骑手日常的另一面。那些藏在订单背后的故事。",
            "观点式": f"所长的看法可能跟很多人不一样。但观点这东西本来就没有对错，重要的是真实。今天所长就把自己的立场亮出来。",
            "轻松式": f"所长没有什么深刻的见解，就是一些日常的观察和碎碎念。可能不够干货，但绝对真实。",
            "感叹式": f"所长跑单这些年，感慨挺多的。有些话平时不好意思说，今天借着这个机会倒出来。",
        }
        general_scene = {
            "共鸣式": f"所长印象最深的是那些不经意的瞬间。比如午高峰时的忙碌，或者雨天配送时的紧张。这些画面构成了骑手生活的真实底色。",
            "幽默式": f"所长到现在还记得当时的心情。有紧张，有无奈，也有那么一点点搞笑。",
            "讨论式": f"每个骑手都有自己的版本。所长今天列举几个典型的场景，看看你属于哪一种。",
            "真实式": f"没有滤镜，没有美化。所长今天就把最原始的画面呈现出来。",
            "好奇式": f"深入观察之后，所长发现了很多以前没注意到的细节。原来同一件事在不同情境下差别这么大。",
            "现场式": f"现场永远比想象更精彩。所长经历过几次印象深刻的场景，到现在想起来还觉得有意思。",
            "故事式": f"这个故事发生在某个普通日子里。没有戏剧性的大起大落，就是骑手生活中最常见的一幕。",
            "观点式": f"从不同角度看，所长得出的结论也不太一样。立场不同，感受自然不同。",
            "轻松式": f"所长见得多了。有些挺有意思，有些也就那样。今天挑几个有代表性的跟你们唠唠。",
            "感叹式": f"每次路过相关场景，所长都会停下来看一会儿。不是因为闲，就是觉得这些画面太有生命力了。",
        }
        general_interaction = {
            "共鸣式": f"有些感受，说出来反而没那么真实了。所长今天想说的就这些，剩下的你自己品。",
            "幽默式": f"离谱的事看多了，也就习惯了。但偶尔回头想想，还是会笑出声。",
            "讨论式": f"说了这么多，其实所长也没有定论。有些事本来就没什么标准答案，各有各的活法。",
            "真实式": f"真实的东西不需要包装。所长说完，你听完，这就够了。",
            "好奇式": f"好奇心这件事，最有趣的地方不是答案，而是找到答案的过程。",
            "现场式": f"有些画面，看一次就够了。但留在脑子里的，比拍下来的更清楚。",
            "故事式": f"故事讲完了，但骑手的生活还在继续。下一段故事，可能就在你今天的跑单路上。",
            "观点式": f"所长的观点不一定对，但绝对是真想过。你怎么看，所长不猜，你自己定。",
            "轻松式": f"所长今天就说这么多。轻不轻松的，你说了算。",
            "感叹式": f"有时候沉默比说话更有力。所长今天选择把最后一句话留空。",
        }
        t = title_type if title_type in general_pain else "共鸣式"
        pain = general_pain.get(t, general_pain["共鸣式"])
        solution = general_solution.get(t, general_solution["共鸣式"])
        scene = general_scene.get(t, general_scene["共鸣式"])
        interaction = general_interaction.get(t, general_interaction["共鸣式"])
        full_text = _build_full_text(pain, solution, scene, interaction, False)
        return {
            "focus": pain,
            "scene": scene,
            "interaction": interaction,
            "full_text": full_text
        }

    base_pain = {
        "测评式": [
            f"家人们谁懂啊，买{item}之前所长以为天下的装备都差不多，结果一对比直接傻眼。有的看着像那么回事，用起来就是想当场退货，这差距比所长的发际线还明显。",
            f"所长这些年测过的{item}没有一百也有八十，每次开箱都像开盲盒，你永远不知道下一个惊喜还是惊吓。今天这个测评，纯纯的真实体验，无滤镜无美颜，所长甚至不想给面子。",
            f"说实话，很多{item}的宣传图拍得比所长还精神，拿到手才发现买家秀和卖家秀的区别。所长今天豁出去了，把真实体验全倒出来，能帮一个是一个。",
        ],
        "攻略式": [
            f"新手选{item}的时候，所长当年也是一脸懵，网上的推荐看得眼花缭乱，结果买回家一用就想给自己一巴掌。今天所长把自己交过的学费整理出来，你们看完别再当大冤种了。",
            f"选{item}这件事，所长以前觉得简单，后来才发现水深得很。花里胡哨的参数看得越多越迷糊，所长今天不聊那些虚的，就聊跑单时真实用起来的感受。",
            f"所长当年选{item}踩过的坑，说出来都是泪。有的装备看着高级，用起来就是一整个无语。今天所长用血泪史帮你排雷，能劝一个是一个。",
        ],
        "清单式": [
            f"所长发现很多骑手用{item}的时候根本没注意到一些细节，结果就是装备提前退休，钱也白花了。今天所长列几个重点，看完你可能要回去检查一下自己的{item}了。",
            f"关于{item}的冷知识，所长要是不说，很多人可能一直不知道。有些细节看着不起眼，实际用下来体验差一大截。所长当年也是后来才知道，后悔没早点做功课。",
            f"跑单这么多年，所长总结了几个关于{item}的实用要点。不是那种教科书式的清单，就是接地气的小建议，看完你就知道哪些坑其实完全可以避开。",
        ],
        "体验式": [
            f"所长第一次用{item}的时候，说实话期待值拉满了，结果第一周差点想退货。后来慢慢磨合，居然真香了。这段体验挺有意思的，所长今天拿出来跟你们唠唠。",
            f"从嫌弃到离不开，{item}跟所长的这段关系可以说是跌宕起伏。刚上手时觉得也就那样，用久了才发现，好的装备真的会让你忘了它的存在。",
            f"所长用{item}的经历可以用一句话概括：开始觉得可有可无，后来觉得早该买了。这种后知后觉的感觉，所长现在想起来还想给自己两拳。",
        ],
        "互动式": [
            f"说到{item}，所长发现每个骑手都有自己的偏好。有的喜欢轻的，有的喜欢耐造的，还有的颜值党。所长想问问：你们选{item}最看重啥？评论区亮出你的标准，看看有多少同道中人！",
            f"所长今天不发表意见，就想抛个问题：你现在的{item}用得顺手吗？有没有踩过坑？评论区跟所长分享一下，让其他骑手也避避雷。",
            f"关于{item}，所长觉得每个人感受都不一样。你的{item}体验如何？是好评还是想吐槽？评论区来聊聊，说不定你的经历就是下一篇内容的素材！",
        ],
        "疑问式": [
            f"很多骑手问所长：{item}到底怎么选？说实话这个问题没有标准答案，但所长有几条经验可以分享，帮你缩小范围少走弯路。",
            f"{item}怎么选？这个问题被问过无数次，所长当年也挠过头。今天所长把摸索出来的经验打包给你，看完你心里大概就有数了。",
            f"新手骑手面对各种{item}一脸懵，所长完全理解。当年也是看着推荐乱买，结果交了不少学费。今天所长聊聊自己的思路，希望能给你一点启发。",
        ],
        "穿搭式": [
            f"谁说骑手不能穿得好看？所长选{item}的时候，实用是第一位，但顺眼也很重要。毕竟每天穿在身上，看着心情好跑单都有劲。",
            f"骑手装备也可以有风格，所长选{item}就讲究一个既实用又精神。不追求花哨，但求干净利落。跑单时看起来专业，自己心情也舒服。",
            f"关于{item}的穿搭，所长的原则是：不丑、不碍事、不难打理。做到这三点，基本就能天天开心跑单了。",
        ],
        "场景式": [
            f"极端天气跑单，{item}的表现直接决定你当天的心情。大太阳下闷出一头汗，或者下雨天突然掉链子，这种体验所长太懂了。",
            f"午高峰连续接单的时候，{item}好不好用，身体比脑子更清楚。那种装备不给力的感觉，所长经历过，真的会让人想骂人。",
            f"不同场景下{item}的表现可能完全不同。所长跑单这些年什么天气都见过，深知关键时刻装备不掉链子有多重要。",
        ],
        "对比式": [
            f"市面上的{item}看着都差不多，用起来才知道差距在哪。所长把几款都试了，发现有的细节做工真的差很远，用着用着就想换。",
            f"对比{item}不能只看参数，所长实际用下来发现，很多参数在实际跑单里根本不重要。真正重要的是耐用度和舒适度，这些得用了才知道。",
            f"所长对比了几款{item}，结论是：贵的未必好，便宜的也有惊喜。关键是找到适合自己跑单习惯的那一款，别光看价格。",
        ],
        "冷知识": [
            f"用了这么久{item}，所长最近才发现几个隐藏用法。原来稍微调整一下，体验可以好不少。这些技巧不花钱不费力，白嫖的体验升级，不香吗？",
            f"关于{item}，大部分骑手可能只用来基础功能，其实还有一些小技巧能让体验提升。所长也是偶然发现的，今天免费分享，看完你就比别人多一手。",
            f"所长在装备研究所里卷了这么久，关于{item}总结了几条实用心得。不用换装备，不用加配件，稍微改变一下用法，效果完全不一样。",
        ],
        "吐槽式": [
            f"所长必须吐槽一下，有些{item}真的是买前期待满满，买后想骂骂咧咧。看着宣传图那叫一个高级，拿到手才发现就是包装做得好。",
            f"关于{item}的血泪史，所长能写一本书。当初就是被各种好评种草，结果一用才知道什么叫买家秀和卖家秀。今天把所长交的智商税跟你们唠唠，你们别再交了。",
            f"所长当年第一次买{item}的时候，纯纯大冤种一个。看评价觉得好，买回来用了两天就想挂二手。这种翻车经历，所长现在想起来还想笑。",
        ],
    }

    base_solution = {
        "测评式": [
            f"实际用了一段时间{item}，所长感受就三个字：看贴合。每天跑单佩戴时间长，哪怕一点点不舒服都会被放大。有些装备看着高级，戴久了才知道什么叫折磨。所长现在选装备，舒服排第一，别的往后稍稍。",
            f"测了这么多{item}，所长发现一个规律：宣传图越精神的，实际用起来落差越大。反倒是那些看着不起眼的，实际佩戴舒适度更稳。 riders 都懂，装备不给力的时候，想摔东西的心都有。",
            f"如果要所长给{item}排个优先级：贴合度大于一切，透气性排第二，耐造程度第三。颜值？所长当年也看重过，现在觉得能看就行，毕竟你是来跑单的，不是来走秀的。",
        ],
        "攻略式": [
            f"选{item}所长建议：先想清楚自己每天跑单的时间长度。时间短随便选，时间长的必须重视舒适度。所长当年追求全能，结果吃了大亏，现在只选适合自己的。",
            f"买{item}不用看太多参数，所长重点关注两个：戴着舒服不舒服，清理麻烦不麻烦。其他的花哨功能对骑手日常跑单来说意义不大，别被商家的花里胡哨忽悠了。",
            f"新手选{item}，所长建议先从基础款用起。跑一段时间知道自己的真实需求后再升级，这样反而更省心。所长当年一步到位买了贵的，结果发现很多功能根本用不上，现在还在角落吃灰。",
        ],
        "清单式": [
            f"所长给新手骑手列几个关于{item}的实用要点：第一戴着不勒，第二戴着不闷，第三清理方便，第四结实耐造。按这四点选基本不会踩雷，所长亲测有效。",
            f"关于{item}的日常维护，所长提醒：定期清洁比啥都重要。很多装备不是用坏的，是脏坏的。养成习惯，装备寿命能延长不少，所长有些装备用了两年还跟新的一样。",
            f"新手骑手入门{item}：先了解基础功能，再跑单实际用几天，然后根据体验调整。所长当年就是跳过了实际体验这一步，结果走了很多弯路。",
        ],
        "体验式": [
            f"刚开始用{item}时所长还有些不习惯，但用了一周后明显感觉到变化。跑单时不用频繁调整，注意力可以更集中在路况上。这种无感体验才是真正的好装备，所长现在离不开了。",
            f"用了大半个月{item}，所长最明显的感受是：之前没注意到的小烦恼突然消失了。好的装备就是这样，让你专注于工作本身，而不是分心在装备上。所长终于不用再一边跑单一边骂装备了。",
            f"从试试看到现在成为日常习惯，{item}给所长的体验总结就一句话：用之前觉得可有可无，用之后觉得早该换了。这种后知后觉的感觉，所长现在想起来还想给自己两拳。",
        ],
        "互动式": [
            f"说实话，选{item}这件事每个人的标准不同。所长见过追求极致轻量的，也见过看重功能全面的，还有人只认耐造程度。所长属于实用派，舒适度优先。你是什么派？评论区站队！",
            f"关于{item}的使用心得，所长总结了几条自己的经验。但每个骑手的跑单环境不同，同样的装备在不同人手里感受也不一样。你的体验是什么？所长在评论区等你的故事。",
            f"用了一段时间{item}，所长发现一个小规律：装备好不好，其实跑单第三天就能感觉出来。第一天新鲜，第二天适应，第三天开始真实体验。你同意吗？不同意的来评论区辩论！",
        ],
        "疑问式": [
            f"很多骑手问所长：{item}到底怎么选？说实话这个问题没有标准答案，但所长有几条经验可以分享，帮你缩小范围少走弯路。",
            f"{item}怎么选？这个问题被问过无数次，所长当年也挠过头。今天所长把摸索出来的经验打包给你，看完你心里大概就有数了。",
            f"新手骑手面对各种{item}一脸懵，所长完全理解。当年也是看着推荐乱买，结果交了不少学费。今天所长聊聊自己的思路，希望能给你一点启发。",
        ],
        "穿搭式": [
            f"谁说骑手不能穿得好看？所长选{item}的时候，实用是第一位，但顺眼也很重要。毕竟每天穿在身上，看着心情好跑单都有劲。",
            f"骑手装备也可以有风格，所长选{item}就讲究一个既实用又精神。不追求花哨，但求干净利落。跑单时看起来专业，自己心情也舒服。",
            f"关于{item}的穿搭，所长的原则是：不丑、不碍事、不难打理。做到这三点，基本就能天天开心跑单了。",
        ],
        "场景式": [
            f"极端天气跑单，{item}的表现直接决定你当天的心情。大太阳下闷出一头汗，或者下雨天突然掉链子，这种体验所长太懂了。",
            f"午高峰连续接单的时候，{item}好不好用，身体比脑子更清楚。那种装备不给力的感觉，所长经历过，真的会让人想骂人。",
            f"不同场景下{item}的表现可能完全不同。所长跑单这些年什么天气都见过，深知关键时刻装备不掉链子有多重要。",
        ],
        "对比式": [
            f"市面上的{item}看着都差不多，用起来才知道差距在哪。所长把几款都试了，发现有的细节做工真的差很远，用着用着就想换。",
            f"对比{item}不能只看参数，所长实际用下来发现，很多参数在实际跑单里根本不重要。真正重要的是耐用度和舒适度，这些得用了才知道。",
            f"所长对比了几款{item}，结论是：贵的未必好，便宜的也有惊喜。关键是找到适合自己跑单习惯的那一款，别光看价格。",
        ],
        "冷知识": [
            f"用了这么久{item}，所长最近才发现几个隐藏用法。原来稍微调整一下，体验可以好不少。这些技巧不花钱不费力，白嫖的体验升级，不香吗？",
            f"关于{item}，大部分骑手可能只用来基础功能，其实还有一些小技巧能让体验提升。所长也是偶然发现的，今天免费分享，看完你就比别人多一手。",
            f"所长在装备研究所里卷了这么久，关于{item}总结了几条实用心得。不用换装备，不用加配件，稍微改变一下用法，效果完全不一样。",
        ],
        "吐槽式": [
            f"所长必须吐槽一下，有些{item}真的是买前期待满满，买后想骂骂咧咧。看着宣传图那叫一个高级，拿到手才发现就是包装做得好。",
            f"关于{item}的血泪史，所长能写一本书。当初就是被各种好评种草，结果一用才知道什么叫买家秀和卖家秀。今天把所长交的智商税跟你们唠唠，你们别再交了。",
            f"所长当年第一次买{item}的时候，纯纯大冤种一个。看评价觉得好，买回来用了两天就想挂二手。这种翻车经历，所长现在想起来还想笑。",
        ],
    }

    base_scene = {
        "测评式": [
            f"连续跑单一周后所长测试{item}的真实表现：戴着它从早上跑到晚上，中间经历了大太阳、微风、突然一阵雨。结论是戴着还算舒服，至少没让所长想当场摘掉。总体来说属于那种不会让你特别惊喜，但也不会让你特别失望的类型。",
            f"实战测试{item}的场景：所长从早上十点跑到晚上九点，各种天气都遇上了。高温天戴着没闷到想骂人，雨天也没掉链子，清洁起来也不算麻烦。这就是所长对它的评价：不求有功，但求无过。",
            f"用{item}跑了近一个月的单，所长最真实的感受是：日常戴着存在感很低，不会给你添堵。好装备就是这样，让你忘了它的存在，但关键时刻它还在。这就是所长心中的及格线。",
        ],
        "攻略式": [
            f"选购{item}时所长建议：别光看宣传图，想象一下自己每天戴它跑八小时的感受。不舒服的装备，宣传再好看也没用。所长当年就是这么踩的坑，现在想起来还想给自己一巴掌。",
            f"实际跑单场景下测试{item}的方法：所长建议连续戴一周，不舒服的话第三天就想扔了。如果能撑过一周还想继续用，那基本就是靠谱的。所长管这叫一周定论，简单粗暴但有效。",
            f"给新手骑手的建议：{item}这东西，借同事的戴两天比看十篇测评都强。所长当年先借同事的试用，实际跑单体验后再买，省了不少冤枉钱。现在所长推荐装备，第一句话都是先试试。",
        ],
        "清单式": [
            f"日常跑单中检查{item}：所长习惯早上出门前快速看一下有没有磨损，下午高峰期前检查一下有没有松动。养成习惯，装备状态始终在线。所长称之为跑单仪式感，虽然听起来很中二，但真的有用。",
            f"{item}的使用场景：晴天注意戴着闷不闷、雨天注意漏不漏水、高温天注意烫不烫、夜间注意安不安全。不同场景不同关注点，所长这份清单虽然简单，但覆盖了90%的日常。",
            f"关于{item}的场景适配：所长不建议指望一件装备包打天下。根据季节准备基础配置，灵活调整比追求全能更实际。所长研究装备这么多年，深知全能往往意味着全不能，这个坑所长替你们踩过了。",
        ],
        "体验式": [
            f"从第一天到第七天使用{item}的体验变化：第一天适应手感，第三天开始真实感受，第七天形成习惯。好用的装备就是能让你快速进入无感状态的那款。所长现在用习惯了，换别的反而不适应。",
            f"长期使用{item}后的体验总结：最初关注的功能点，后来都变成了理所当然；真正留在印象里的，反而是那些日常使用中不经意感受到的舒适感。所长称之为润物细无声的装备哲学。",
            f"和队友交流{item}使用体验，所长发现大家的感受差异很大。有人看重功能，有人在意颜值，有人只关心耐久度。这也说明选装备真的要根据个人需求来。所长尊重每一种选择，只要你觉得好用就行。",
        ],
        "互动式": [
            f"所长跑单时用{item}的场景其实挺固定的：早上出门戴上，晚上收工取下。中间就是各种配送场景。平凡但真实，这就是骑手装备的日常。你的日常是什么样的？跟所长分享一下。",
            f"关于{item}在真实跑单中的表现，所长觉得最能检验的场景是：连续接短单、长距离配送、恶劣天气跑单。这三个场景都扛住了，装备才算及格。你家的{item}能扛住几个？",
            f"想象一个场景：午高峰连续接单，全神贯注在导航和配送上，这时{item}的表现应该是感觉不到它的存在。能做到这点的装备，才是真正的好装备。所长亲测，这种装备真的存在，而且不多。",
        ],
        "疑问式": [
            f"{item}到底好不好用？所长的答案是：在真实跑单场景中连续使用一周，自然就有答案了。宣传和测评只能参考，实际体验才是最终标准。所长当年也是看了测评才买的，结果发现……",
            f"如果你问所长{item}适合什么场景，所长会说：先看你的主要跑单时段和天气条件。不同场景下装备的表现差异很大，不能一概而论。所长研究装备这么多年，最深的体会就是没有最好，只有最合适。",
            f"关于{item}的选择问题，所长觉得最好的解决方案就是：试用。借朋友的用几天，或者先买基础款体验。实际感受比任何建议都有说服力。所长当年要是早点悟到这点，能省不少冤枉钱。",
        ],
        "穿搭式": [
            f"日常跑单场景中的穿搭实践：{item}搭配基础工服，整体看起来干净利落。好的装备搭配不需要花哨，简洁实用就是最好的风格。所长现在跑单，经常被顾客说看起来挺专业，其实就是装备选对了。",
            f"在骑手群体中观察到的穿搭趋势：越来越多的骑手开始重视装备的外观设计。{item}选对了，整个人的精神面貌都不一样。所长觉得，这不仅是好看，更是一种对工作的尊重。",
            f"关于{item}的穿搭建议：所长建议选中性色系更百搭，功能性和外观兼顾的款式优先。毕竟每天穿在身上的装备，看着顺眼也是加分项。所长现在出门跑单，装备搭配是固定的，省得纠结。",
        ],
        "场景式": [
            f"极端场景下的{item}表现：中午暴晒时透气性能决定佩戴舒适度，突遇降雨时防水功能保证配送不受影响，夜间跑单时安全设计提供额外保障。所长都经历过，深知这些场景才是真正的试金石。",
            f"不同季节的{item}使用场景：夏季侧重透气散热，冬季侧重防风保暖，雨季侧重防水防滑。装备虽好，也要用对场景才能发挥最大价值。所长管这叫因地制宜的装备哲学。",
            f"连续高强度跑单场景下，{item}的耐久度和舒适度会面临真正考验。日常轻度使用表现好的装备，不一定能扛住骑手的高频使用节奏。所长研究装备这么多年，最看重的就是耐造二字。",
        ],
        "对比式": [
            f"真实场景对比{item}：佩戴舒适度方面差异明显，耐久度需要长期使用才能见分晓，日常维护便利性也是值得考虑的因素。所长综合权衡后，觉得适合自己的最重要，毕竟是你每天戴的东西。",
            f"不同款式{item}的场景对比：基础款能满足核心需求，进阶款在舒适度和耐久度上更有优势，高端款则在细节做工上有提升。所长建议按需选择，不要过度消费，但也别为了省钱委屈自己。",
            f"{item}对比场景建议：所长提醒不要只看静态参数，实际跑单佩戴时的动态体验才是差距最明显的地方。有条件的话多试用几款再做决定。所长当年就是这么对比的，最后选的那款现在还在用。",
        ],
        "冷知识": [
            f"{item}的使用场景小技巧：不同的佩戴方式会影响舒适度，稍微调整位置或松紧度，体验可能完全不同。多试试找到最适合自己的方式。所长也是在研究所里卷了无数次才发现这些隐藏开关。",
            f"关于{item}很多人忽略的场景细节：在极端天气前后的维护方式不同。高温天后注意清洁散热部件，雨天后注意干燥通风。这些细节影响装备寿命。所长有些装备用了三年还跟新的一样，靠的就是这些细节。",
            f"{item}在不同场景下的隐藏功能：有些设计在常规使用中不太显眼，但在特定场景下会派上大用场。多留意装备的各个功能点，也许会有意外发现。所长经常跟同事说：装备不是只会基础功能，你得挖掘它。",
        ],
        "吐槽式": [
            f"所长跑单时用{item}的真实场景：早上出门戴着，晚上收工摘下。中间就是各种配送场景。说实话，大多数时间{item}的表现都是无功无过，但关键时刻能救命。这就是所长对它的评价：不求有功，但求无过。",
            f"关于{item}在真实跑单中的表现，所长觉得最能检验的场景是：连续接短单、长距离配送、恶劣天气跑单。这三个场景都扛住了，装备才算及格。你家的{item}能扛住几个？",
            f"所长经历过最尴尬的场景：午高峰连续接单，全神贯注在导航和配送上，结果{item}突然掉链子。那一刻所长真的想骂人。所以选装备，稳定性是第一位的，其他都是浮云。",
        ],
    }

    base_interaction = {
        "测评式": [
            f"测了这么多，所长最后想说的是：装备这东西，适合自己的才是最好的。别人的测评只是参考，你用了才知道。",
            f"测评写完了，但所长的感受还在。有些装备的好，不是参数能说明白的，是用久了才慢慢体会到的。",
            f"所长测完这件{item}，心情挺复杂的。不是满分，但也不是零分。就是那种，够用但还能更好的感觉。",
        ],
        "攻略式": [
            f"攻略写到这儿，所长突然觉得，所谓的攻略也不过是别人的经验。真正适合你的，还得你自己去试。",
            f"以上就是所长能想到的全部了。剩下的事，交给你的实际体验。攻略只是起点，不是终点。",
            f"选{item}这件事，没有标准答案。所长给的只是参考框架，最终填什么内容，你自己决定。",
        ],
        "清单式": [
            f"清单列完了，但所长知道，实际用起来的细节远比清单丰富。有些坑，只有踩过才知道。",
            f"这份清单是所长能想到的重点，但肯定不是全部。你实际用起来，可能会发现更多需要注意的地方。",
            f"清单只是地图，实际的路还得你自己走。所长能做的，就是帮你少绕几个弯。",
        ],
        "体验式": [
            f"体验这件事，说再多也不如自己用一次。所长的心得就这些，剩下的你自己感受。",
            f"从陌生到熟悉，从嫌弃到依赖，{item}跟所长的这段关系，差不多就是这样。你的故事可能不一样。",
            f"所长用{item}的体验就说到这。好的坏的都说了，最终值不值得，你说了算。",
        ],
        "互动式": [
            f"装备只是辅助，真正的技能来自日复一日的积累。所长今天想说的，就这么多。",
            f"关于{item}，所长没有结论，只有观察。你怎么看，所长不猜，你自己品。",
            f"每次聊装备，所长都觉得，最有意思的不是装备本身，而是用它的人。",
        ],
        "疑问式": [
            f"{item}怎么选？所长答完了，但答案可能不适合你。最终还是要回归你自己的真实需求。",
            f"问题问完了，回答也给了。但所长一直觉得，真正的好答案不是别人给的，是自己试出来的。",
            f"关于{item}，所长能说的都说了。剩下的空白，留给你自己去填。",
        ],
        "穿搭式": [
            f"穿搭这件事，所长觉得舒服顺眼就行。不用太纠结，毕竟你是来跑单的，不是来走秀的。",
            f"关于{item}的穿搭，所长就说这么多。好看固然重要，但别为了好看委屈了自己。",
            f"装备穿得再好看，也得先跑得舒服。所长选{item}的原则就这一个：实用第一，顺眼第二。",
        ],
        "场景式": [
            f"场景再多，核心需求不变：装备在关键时刻别掉链子。所长今天说的这些场景，你遇到过几个？",
            f"不同场景下{item}的表现，所长差不多都聊到了。但真正考验装备的场景，往往是你意想不到的那个。",
            f"场景是死的，人是活的。所长总结的再多，也不如你自己跑单时那一瞬间的真实感受。",
        ],
        "对比式": [
            f"对比做完了，结论也有了。但所长想提醒你：对比只是手段，不是目的。适合你的，才是最好的。",
            f"参数再漂亮，也不如实际戴起来舒服。所长对比{item}的结论就这一个：亲身体验胜过一切数据。",
            f"对比的结果仅供参考。所长选装备，从来不看排名，只看自己用起来顺不顺手。",
        ],
        "冷知识": [
            f"冷知识讲完了，但所长知道，关于{item}的秘密肯定不止这些。有些技巧，只有老骑手才知道。",
            f"知识虽小，用对了能省不少事。所长今天分享的{item}冷知识，希望能帮你少走一点弯路。",
            f"所长知道的{item}技巧就这些了。但装备这件事，永远有新发现。你的独门技巧是什么？",
        ],
        "吐槽式": [
            f"吐槽完了，所长心情好多了。装备这件事，爱之深责之切。吐槽归吐槽，但该用还得用。",
            f"所长的吐槽就到这里。其实每次吐槽完，反而更清楚自己要什么。这大概就是吐槽的价值吧。",
            f"吐槽是情绪出口，但选装备还得理性。所长发泄完了，现在该你去理性判断了。",
        ],
    }

    default_type = "攻略式"
    t = title_type if title_type in base_pain else default_type

    pain = random.choice(base_pain.get(t, base_pain[default_type]))
    solution = random.choice(base_solution.get(t, base_solution[default_type]))
    scene = random.choice(base_scene.get(t, base_scene[default_type]))
    interaction = random.choice(base_interaction.get(t, base_interaction[default_type]))

    full_text = _build_full_text(pain, solution, scene, interaction, True)
    return {
        "focus": pain,
        "scene": scene,
        "interaction": interaction,
        "full_text": full_text
    }


@app.route("/api/ai-generate-titles", methods=["POST"])
def api_ai_generate_titles():
    """AI 根据话题方向生成标题列表，AI 失败时自动规则兜底"""
    data = request.json or {}
    topic = data.get("topic", "").strip()
    if not topic:
        return jsonify({"error": "请提供话题方向"}), 400
    try:
        cfg = load_config()
        or_key = cfg.get("api", {}).get("openrouter", {}).get("api_key", "")
        ali_key = cfg.get("api", {}).get("aliyun", {}).get("api_key", "")

        titles = []
        source = "rule"
        # 优先尝试 AI（配置了有效 Key 时）
        if or_key and or_key != "****" and or_key != "2074755564659879949":
            try:
                titles = _ai_generate_titles(topic)
                source = "ai"
            except Exception as e:
                logger.warning(f"AI 标题生成失败，fallback 到规则: {e}")
        
        # AI 失败或未配置，用规则兜底
        if not titles:
            titles = _rule_generate_titles(topic)
            source = "rule"

        return jsonify({"titles": titles, "topic": topic, "count": len(titles), "source": source})
    except Exception as e:
        logger.error(f"生成标题失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai-generate-body", methods=["POST"])
def api_ai_generate_body():
    """AI 根据标题生成正文内容，AI 失败时自动规则兜底"""
    data = request.json or {}
    title = data.get("title", "").strip()
    topic = data.get("topic", "").strip()
    title_type = data.get("type", "").strip()
    if not title:
        return jsonify({"error": "请提供标题"}), 400
    try:
        cfg = load_config()
        or_key = cfg.get("api", {}).get("openrouter", {}).get("api_key", "")
        ali_key = cfg.get("api", {}).get("aliyun", {}).get("api_key", "")

        body = {}
        source = "rule"
        # 优先尝试 AI
        if or_key and or_key != "****" and or_key != "2074755564659879949":
            try:
                body = _ai_generate_body(title, topic, title_type)
                source = "ai"
            except Exception as e:
                logger.warning(f"AI 正文生成失败，fallback 到规则: {e}")
        
        # AI 失败或未配置，用规则兜底
        if not body:
            body = _rule_generate_body(title, topic, title_type)
            source = "rule"

        return jsonify({"body": body, "title": title, "topic": topic, "type": title_type, "source": source})
    except Exception as e:
        logger.error(f"生成正文失败: {e}")
        return jsonify({"error": str(e)}), 500

# ---- 看板数据 ----
@app.route("/api/dashboard")
def api_dashboard():
    today = datetime.now().strftime("%Y%m%d")
    latest_dir = get_latest_output_dir()
    
    stats = {
        "today": today,
        "hot_total": 0,
        "topic_count": 0,
        "content_count": 0,
        "brief_count": 0,
        "platforms": {"douyin": 0, "xiaohongshu": 0, "ecommerce": 0},
        "last_run": app_state["last_generate_time"] or "未执行",
        "marketing_event": None,
        "daily_task": app_state["daily_task"]
    }
    
    # 统计热点
    for platform, items in app_state["current_hot_data"].items():
        stats["platforms"][platform] = len(items)
        stats["hot_total"] += len(items)
    
    # 统计选题和内容
    stats["topic_count"] = len(app_state["current_topics"])
    stats["content_count"] = len(app_state["current_contents"])
    stats["brief_count"] = len(app_state["current_briefs"])
    
    # 当前营销节点
    try:
        selector = get_topic_selector()
        event = selector.get_current_marketing_event()
        if event:
            stats["marketing_event"] = {
                "name": event["name"],
                "period": event["period"],
                "categories": event.get("categories", []),
                "themes": event.get("themes", [])
            }
    except Exception as e:
        add_log("error", f"营销节点获取失败: {e}")
    
    # 最近7天执行记录
    history = []
    for d in get_all_output_dirs()[:7]:
        files = os.listdir(d["path"]) if os.path.exists(d["path"]) else []
        history.append({
            "date": d["display"],
            "has_excel": any(f.endswith(".xlsx") for f in files),
            "has_word": any(f.endswith(".docx") for f in files),
            "has_md": any(f.endswith(".md") for f in files)
        })
    stats["history"] = history
    
    return jsonify(stats)

# ---- 热点数据 ----
@app.route("/api/hot_data")
def api_hot_data():
    platform = request.args.get("platform", "all")
    keyword = request.args.get("keyword", "").lower()
    
    items = []
    if platform == "all":
        for p, data in app_state["current_hot_data"].items():
            for item in data:
                d = item.to_dict() if hasattr(item, "to_dict") else item
                d["platform"] = p
                items.append(d)
    else:
        data = app_state["current_hot_data"].get(platform, [])
        for item in data:
            d = item.to_dict() if hasattr(item, "to_dict") else item
            items.append(d)
    
    if keyword:
        items = [i for i in items if keyword in i.get("title", "").lower()]
    
    return jsonify({"items": items, "total": len(items), "platform": platform})

@app.route("/api/hot_data/recommended")
def api_hot_data_recommended():
    """筛选与美团骑手/装备相关的热点，并给出AI推荐理由和关联玩法建议"""
    # 骑手装备核心关键词（强关联）
    strong_kw = ["骑手", "外卖", "配送", "美团", "饿了么", "头盔", "装备", "防晒", "清凉", "夏季", "安全", "骑行", "电动车", "摩托车", "餐箱", "雨衣", "手套", "护膝", "工装", "工作服"]
    # 中关联
    medium_kw = ["打工", "通勤", "户外", "潮流", "穿搭", "省钱", "好物", "推荐", "测评", "爆款", "热销", "升级", "新品"]
    
    all_items = []
    for p, data in app_state["current_hot_data"].items():
        for item in data:
            d = item.to_dict() if hasattr(item, "to_dict") else item
            d["platform"] = p
            all_items.append(d)
    
    # 规则筛选 + 基础评分
    recommended = []
    for item in all_items:
        title = item.get("title", "")
        score = 0
        reasons = []
        play_bgm = []
        play_meme = []
        play_video = []
        
        title_lower = title.lower()
        for kw in strong_kw:
            if kw.lower() in title_lower:
                score += 25
                reasons.append(f"强关联：{kw}")
        for kw in medium_kw:
            if kw.lower() in title_lower:
                score += 10
                reasons.append(f"中关联：{kw}")
        
        # 按热点类型自动推荐玩法元素
        if "bgm" in title_lower or "音乐" in title or "歌" in title:
            play_bgm.append("可直接用此BGM，拍骑手装备变装/开箱视频")
            play_bgm.append("BGM节奏卡点，展示装备功能细节")
        if "挑战" in title or "模仿" in title or "梗" in title or "变装" in title:
            play_meme.append("骑手版变装挑战：从便装→全套美团装备")
            play_meme.append("用此梗拍反差：装备前后对比/装备性能测试")
        if "测评" in title or "推荐" in title or "好物" in title:
            play_video.append("骑手装备测评：美团头盔/餐箱/防晒衣实测")
            play_video.append("好物推荐：结合热点拍装备种草短视频")
        
        # 通用保底推荐（任何热点都可以尝试关联）
        if score == 0:
            # 无直接关联，但可能有创意空间
            score = 5
            reasons.append("通用借势：可创意关联骑手场景")
            play_meme.append("通用玩法：骑手视角解读此热点，植入装备露出")
            play_video.append("通用玩法：结合热点话题拍骑手日常，自然植入产品")
        
        # 通用关联玩法（无论是否有关键词匹配）
        if not play_bgm:
            play_bgm.append("通用BGM：用抖音热门BGM，拍骑手装备展示卡点视频")
        if not play_meme:
            play_meme.append("通用梗：用热点梗做骑手装备推荐，制造反差感")
        if not play_video:
            play_video.append("通用视频：骑手送餐路上遇到此热点话题，装备自然露出")
        
        item["recommend_score"] = min(score, 100)
        item["recommend_reason"] = "；".join(reasons) if reasons else "创意关联"
        item["recommend_play_bgm"] = play_bgm[:2]
        item["recommend_play_meme"] = play_meme[:2]
        item["recommend_play_video"] = play_video[:2]
        recommended.append(item)
    
    # 按推荐分排序，取前30
    recommended.sort(key=lambda x: x.get("recommend_score", 0), reverse=True)
    recommended = recommended[:30]
    
    # 如果有AI API Key，尝试对Top10做深度分析
    try:
        cfg = load_config()
        or_key = cfg.get("api", {}).get("openrouter", {}).get("api_key", "")
        if or_key and or_key != "****":
            ai = get_ai_client()
            for item in recommended[:10]:
                title = item.get("title", "")
                prompt = f"""你是一位资深短视频内容营销专家，擅长为品牌「美团骑手装备」借势热点。

热点：{title}

请分析这个热点与美团骑手/骑手装备（头盔、服装、餐箱、防护用品等）的关联度，并给出：
1. 关联度评分（0-100）
2. 一句话推荐理由
3. 推荐BGM玩法（1条）
4. 推荐梗/挑战玩法（1条）
5. 推荐视频拍摄方向（1条）

格式：
评分: xx
理由: xxx
BGM: xxx
梗: xxx
视频: xxx
"""
                try:
                    result = ai.generate_content(prompt, max_tokens=500)
                    # 解析结果
                    lines = result.strip().split("\n")
                    for line in lines:
                        if line.startswith("评分:"):
                            try:
                                item["recommend_score"] = int(line.replace("评分:","").strip().replace("分",""))
                            except: pass
                        elif line.startswith("理由:"):
                            item["recommend_reason"] = line.replace("理由:","").strip()
                        elif line.startswith("BGM:"):
                            item["recommend_play_bgm"] = [line.replace("BGM:","").strip()]
                        elif line.startswith("梗:"):
                            item["recommend_play_meme"] = [line.replace("梗:","").strip()]
                        elif line.startswith("视频:"):
                            item["recommend_play_video"] = [line.replace("视频:","").strip()]
                except Exception as e:
                    pass
    except Exception as e:
        pass
    
    return jsonify({"items": recommended, "total": len(recommended), "type": "recommended"})

@app.route("/api/hot_data/history")
def api_hot_data_history():
    date_str = request.args.get("date", "")
    if not date_str or not date_str.isdigit():
        return jsonify({"error": "请提供日期参数 (YYYYMMDD)"}), 400
    
    hot_dir = os.path.join(PROJECT_DIR, "data", "hot_data")
    items = []
    for platform in ["douyin", "xiaohongshu", "ecommerce"]:
        filepath = os.path.join(hot_dir, f"{date_str}_{platform}_hot.json")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("items", []):
                    item["platform"] = platform
                    items.append(item)
    
    return jsonify({"items": items, "total": len(items), "date": date_str})

# ---- 选题中心 ----
@app.route("/api/topics")
def api_topics():
    return jsonify({
        "topics": app_state["current_topics"],
        "count": len(app_state["current_topics"])
    })

# ---- 内容工坊 ----
@app.route("/api/contents")
def api_contents():
    platform = request.args.get("platform", "all")
    contents = app_state["current_contents"]
    if platform != "all":
        contents = [c for c in contents if c and c.get("platform") == platform]
    return jsonify({"contents": contents, "count": len(contents)})

# ---- 达人 Brief ----
@app.route("/api/briefs")
def api_briefs():
    return jsonify({
        "briefs": app_state["current_briefs"],
        "count": len(app_state["current_briefs"])
    })

# ---- 执行日志 ----
@app.route("/api/logs")
def api_logs():
    level = request.args.get("level", "all")
    logs = app_state["logs"]
    if level != "all":
        logs = [l for l in logs if l["level"] == level]
    return jsonify({"logs": logs[-100:], "count": len(logs)})

@app.route("/api/logs/stream")
def api_logs_stream():
    def event_stream():
        last_idx = len(app_state["logs"])
        while True:
            if len(app_state["logs"]) > last_idx:
                new_logs = app_state["logs"][last_idx:]
                last_idx = len(app_state["logs"])
                for log in new_logs:
                    yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
            time.sleep(1)
    return Response(event_stream(), mimetype="text/event-stream")

# ---- 操作：采集热点 ----
@app.route("/api/run/collect", methods=["POST"])
def api_run_collect():
    if app_state["collecting"]:
        return jsonify({"status": "busy", "msg": "采集任务正在执行中"})
    
    def do_collect():
        app_state["collecting"] = True
        app_state["task_status"] = "collecting"
        add_log("info", "开始采集热点数据...")
        
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            
            # 抖音
            add_log("info", "[抖音] 采集热点...")
            dy = DouyinHotCollector()
            dy_items = dy.collect()
            app_state["current_hot_data"]["douyin"] = dy_items
            dy.save_raw(dy_items, date_str)
            add_log("info", f"[抖音] 采集完成: {len(dy_items)} 条")
            
            # 小红书
            add_log("info", "[小红书] 采集热搜...")
            xhs = XiaohongshuHotCollector()
            xhs_items = xhs.collect()
            app_state["current_hot_data"]["xiaohongshu"] = xhs_items
            xhs.save_raw(xhs_items, date_str)
            add_log("info", f"[小红书] 采集完成: {len(xhs_items)} 条")
            
            # 电商趋势
            add_log("info", "[电商] 采集行业趋势...")
            ec = EcommerceTrendCollector()
            ec_items = ec.collect()
            app_state["current_hot_data"]["ecommerce"] = ec_items
            ec.save_raw(ec_items, date_str)
            add_log("info", f"[电商] 采集完成: {len(ec_items)} 条")
            
            total = len(dy_items) + len(xhs_items) + len(ec_items)
            add_log("info", f"采集全部完成！共 {total} 条热点")
            app_state["last_collect_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
        except Exception as e:
            add_log("error", f"采集失败: {e}")
            logger.exception("采集异常")
        finally:
            app_state["collecting"] = False
            app_state["task_status"] = "idle"
    
    threading.Thread(target=do_collect, daemon=True).start()
    return jsonify({"status": "started", "msg": "采集任务已启动"})

# ---- 操作：生成内容 ----
@app.route("/api/run/generate", methods=["POST"])
def api_run_generate():
    if app_state["generating"]:
        return jsonify({"status": "busy", "msg": "生成任务正在执行中"})
    
    def do_generate():
        app_state["generating"] = True
        app_state["task_status"] = "generating"
        add_log("info", "开始生成内容...")
        
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            
            # 合并所有热点
            all_items = []
            for p, items in app_state["current_hot_data"].items():
                all_items.extend(items)
            
            if not all_items:
                add_log("warning", "没有热点数据，请先执行采集")
                return
            
            # 选题匹配
            add_log("info", "AI 选题匹配中...")
            selector = get_topic_selector()
            selected = selector.select_topics(all_items, top_n=10)
            app_state["current_topics"] = selected
            add_log("info", f"选题匹配完成: {len(selected)} 个关联选题")
            
            # 内容生成
            # 前置检查：API Key 是否已配置
            try:
                cfg = load_config()
                or_key = cfg.get("api", {}).get("openrouter", {}).get("api_key", "")
                ali_key = cfg.get("api", {}).get("aliyun", {}).get("api_key", "")
                if not or_key and not ali_key:
                    add_log("error", "[严重] AI API Key 未配置！请在「系统设置」中填写 OpenRouter 或阿里云 API Key")
                    add_log("error", "获取方式：访问 https://openrouter.ai 注册 → Settings → Keys → Create Key")
                    add_log("error", "免费模型可用：qwen/qwen-3-235b-a22b:free")
                    return
            except Exception as e:
                add_log("error", f"配置检查失败: {e}")
                return

            add_log("info", "AI 内容生成中...")
            writer = get_content_writer()
            contents = []
            
            for topic in selected[:3]:
                add_log("info", f"生成选题内容: {topic['hot_topic']['title'][:30]}...")
                
                xhs = writer.generate_xiaohongshu_note(topic)
                if xhs:
                    contents.append(xhs)
                    add_log("info", "  -> 小红书笔记已生成")
                else:
                    add_log("error", "  -> 小红书笔记生成失败，AI 返回空 (请检查 API Key)")
                
                dy = writer.generate_douyin_copy(topic)
                if dy:
                    contents.append(dy)
                    add_log("info", "  -> 抖音脚本已生成")
                else:
                    add_log("error", "  -> 抖音脚本生成失败，AI 返回空 (请检查 API Key)")
                
                event = topic.get("marketing_event")
                ec = writer.generate_ecommerce_activity(topic, event)
                if ec:
                    contents.append(ec)
                    add_log("info", "  -> 电商活动方案已生成")
                else:
                    add_log("error", "  -> 电商活动方案生成失败，AI 返回空 (请检查 API Key)")
            
            app_state["current_contents"] = contents
            
            # 达人 Brief
            add_log("info", "生成达人 Brief...")
            brief_gen = get_brief_generator()
            briefs = []
            for topic in selected[:2]:
                b = brief_gen.generate_batch_briefs(topic)
                briefs.extend(b)
            app_state["current_briefs"] = briefs
            add_log("info", f"达人 Brief 生成完成: {len(briefs)} 份")
            
            # 输出文件
            add_log("info", "生成输出文件...")
            excel_reporter = get_excel_reporter()
            excel_path = excel_reporter.create_daily_schedule(selected, contents, date_str)
            add_log("info", f"  → Excel 排期表: {os.path.basename(excel_path)}")
            
            word_reporter = get_word_reporter()
            word_path = word_reporter.create_activity_plan(selected, contents, briefs, date_str)
            add_log("info", f"  → Word 策划案: {os.path.basename(word_path)}")
            
            # Markdown 简报
            fm = get_file_manager()
            daily_dir = fm.get_daily_dir(date_str)
            md_path = os.path.join(daily_dir, f"{date_str}_热点营销简报.md")
            report_md = writer.generate_daily_report(selected, date_str)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report_md)
            add_log("info", f"  → Markdown 简报: {os.path.basename(md_path)}")
            
            app_state["last_generate_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            add_log("info", "内容生成全部完成！")
            
        except Exception as e:
            add_log("error", f"生成失败: {e}")
            logger.exception("生成异常")
        finally:
            app_state["generating"] = False
            app_state["task_status"] = "idle"
    
    threading.Thread(target=do_generate, daemon=True).start()
    return jsonify({"status": "started", "msg": "生成任务已启动"})

# ---- 操作：为特定选题生成内容 ----
@app.route("/api/generate_content", methods=["POST"])
def api_generate_content():
    if app_state["generating"]:
        return jsonify({"status": "busy", "msg": "生成任务正在执行中"})
    
    data = request.json or {}
    topic_idx = data.get("topic_index", 0)
    platform = data.get("platform", "xiaohongshu")
    
    topics = app_state.get("current_topics", [])
    if not topics or topic_idx >= len(topics):
        return jsonify({"status": "error", "msg": "选题不存在，请先执行采集和生成"}), 400
    
    topic = topics[topic_idx]
    
    def do_generate_single():
        app_state["generating"] = True
        app_state["task_status"] = "generating"
        add_log("info", f"为用户生成内容: 选题[{topic_idx}] + 平台[{platform}]")
        
        # 前置检查：API Key 是否已配置
        try:
            cfg = load_config()
            or_key = cfg.get("api", {}).get("openrouter", {}).get("api_key", "")
            ali_key = cfg.get("api", {}).get("aliyun", {}).get("api_key", "")
            if not or_key and not ali_key:
                add_log("error", "[严重] AI API Key 未配置！无法生成内容。请在「系统设置」中填写 API Key")
                add_log("error", "获取方式：访问 https://openrouter.ai 注册 → Settings → Keys → Create Key")
                return
        except Exception as e:
            add_log("error", f"配置检查失败: {e}")
            return
        
        try:
            writer = get_content_writer()
            if platform == "xiaohongshu":
                result = writer.generate_xiaohongshu_note(topic)
            elif platform == "douyin":
                result = writer.generate_douyin_copy(topic)
            elif platform == "ecommerce":
                event = topic.get("marketing_event")
                result = writer.generate_ecommerce_activity(topic, event)
            else:
                add_log("error", f"不支持的平台: {platform}")
                return
            
            if result:
                app_state["current_contents"].append(result)
                add_log("info", f"内容生成完成: {result['platform']} - {result['format']}")
            else:
                add_log("error", "内容生成失败，返回空")
        except Exception as e:
            add_log("error", f"内容生成异常: {e}")
            logger.exception("内容生成异常")
        finally:
            app_state["generating"] = False
            app_state["task_status"] = "idle"
    
    threading.Thread(target=do_generate_single, daemon=True).start()
    return jsonify({"status": "started", "msg": f"正在生成 {platform} 内容，请稍候..."})

# ---- 操作：一键执行 ----
@app.route("/api/run/full", methods=["POST"])
def api_run_full():
    if app_state["collecting"] or app_state["generating"]:
        return jsonify({"status": "busy", "msg": "任务正在执行中"})
    
    def do_full():
        # 先采集
        app_state["collecting"] = True
        app_state["task_status"] = "collecting"
        add_log("info", "=== 一键执行: 开始采集 ===")
        
        try:
            date_str = datetime.now().strftime("%Y%m%d")
            
            dy = DouyinHotCollector()
            dy_items = dy.collect()
            app_state["current_hot_data"]["douyin"] = dy_items
            dy.save_raw(dy_items, date_str)
            add_log("info", f"[抖音] {len(dy_items)} 条")
            
            xhs = XiaohongshuHotCollector()
            xhs_items = xhs.collect()
            app_state["current_hot_data"]["xiaohongshu"] = xhs_items
            xhs.save_raw(xhs_items, date_str)
            add_log("info", f"[小红书] {len(xhs_items)} 条")
            
            ec = EcommerceTrendCollector()
            ec_items = ec.collect()
            app_state["current_hot_data"]["ecommerce"] = ec_items
            ec.save_raw(ec_items, date_str)
            add_log("info", f"[电商] {len(ec_items)} 条")
            
            app_state["collecting"] = False
            app_state["last_collect_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 再生成
            app_state["generating"] = True
            app_state["task_status"] = "generating"
            add_log("info", "=== 一键执行: 开始生成 ===")
            
            # 前置检查：API Key 是否已配置
            try:
                cfg = load_config()
                or_key = cfg.get("api", {}).get("openrouter", {}).get("api_key", "")
                ali_key = cfg.get("api", {}).get("aliyun", {}).get("api_key", "")
                if not or_key and not ali_key:
                    add_log("error", "[严重] AI API Key 未配置！无法生成内容。请在「系统设置」中填写 OpenRouter 或阿里云 API Key")
                    add_log("error", "获取方式：访问 https://openrouter.ai 注册 → Settings → Keys → Create Key")
                    add_log("error", "免费模型可用：qwen/qwen-3-235b-a22b:free")
                    return
            except Exception as e:
                add_log("error", f"配置检查失败: {e}")
                return
            
            all_items = []
            for p, items in app_state["current_hot_data"].items():
                all_items.extend(items)
            
            selector = get_topic_selector()
            selected = selector.select_topics(all_items, top_n=10)
            app_state["current_topics"] = selected
            
            writer = get_content_writer()
            contents = []
            for topic in selected[:3]:
                xhs = writer.generate_xiaohongshu_note(topic)
                if xhs:
                    contents.append(xhs)
                dy = writer.generate_douyin_copy(topic)
                if dy:
                    contents.append(dy)
                event = topic.get("marketing_event")
                ec = writer.generate_ecommerce_activity(topic, event)
                if ec:
                    contents.append(ec)
            app_state["current_contents"] = contents
            
            brief_gen = get_brief_generator()
            briefs = []
            for topic in selected[:2]:
                b = brief_gen.generate_batch_briefs(topic)
                briefs.extend(b)
            app_state["current_briefs"] = briefs
            
            excel_reporter = get_excel_reporter()
            excel_path = excel_reporter.create_daily_schedule(selected, contents, date_str)
            
            word_reporter = get_word_reporter()
            word_path = word_reporter.create_activity_plan(selected, contents, briefs, date_str)
            
            fm = get_file_manager()
            daily_dir = fm.get_daily_dir(date_str)
            md_path = os.path.join(daily_dir, f"{date_str}_热点营销简报.md")
            report_md = writer.generate_daily_report(selected, date_str)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report_md)
            
            app_state["last_generate_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            add_log("info", "=== 一键执行全部完成！===")
            
        except Exception as e:
            add_log("error", f"一键执行失败: {e}")
            logger.exception("一键执行异常")
        finally:
            app_state["collecting"] = False
            app_state["generating"] = False
            app_state["task_status"] = "idle"
    
    threading.Thread(target=do_full, daemon=True).start()
    return jsonify({"status": "started", "msg": "一键执行任务已启动（采集+生成）"})

# ---- 配置管理 ----
@app.route("/api/config")
def api_config():
    try:
        cfg = load_config()
        # 脱敏 API Key
        if "api" in cfg:
            for provider in cfg["api"]:
                key = cfg["api"][provider].get("api_key", "")
                if key:
                    cfg["api"][provider]["api_key"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        return jsonify(cfg)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/config", methods=["POST"])
def api_config_save():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "无数据"}), 400
        
        cfg = load_config()
        
        # 更新 API 配置
        if "api" in data:
            for provider in data["api"]:
                if provider not in cfg["api"]:
                    cfg["api"][provider] = {}
                for key, val in data["api"][provider].items():
                    if key == "api_key" and val == "****":
                        continue  # 保留原值
                    cfg["api"][provider][key] = val
        
        # 更新平台配置
        if "platforms" in data:
            cfg["platforms"] = data["platforms"]
        
        # 更新输出配置
        if "output" in data:
            cfg["output"] = data["output"]
        
        # 更新定时任务
        if "schedule" in data:
            cfg["schedule"] = data["schedule"]
        
        save_config(cfg)
        add_log("info", "配置已更新")
        return jsonify({"status": "ok", "msg": "配置保存成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---- 营销日历 ----
@app.route("/api/calendar")
def api_calendar():
    try:
        cal = load_marketing_calendar()
        return jsonify(cal)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---- 文件下载 ----
@app.route("/api/download/<path:filename>")
def api_download(filename):
    try:
        latest = get_latest_output_dir()
        if not latest:
            return jsonify({"error": "无输出文件"}), 404
        filepath = os.path.join(latest, filename)
        if not os.path.exists(filepath):
            # 尝试在历史目录找
            for d in get_all_output_dirs():
                fpath = os.path.join(d["path"], filename)
                if os.path.exists(fpath):
                    filepath = fpath
                    break
        if not os.path.exists(filepath):
            return jsonify({"error": "文件不存在"}), 404
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/files")
def api_files():
    """列出所有输出文件"""
    dirs = get_all_output_dirs()
    files = []
    for d in dirs:
        if os.path.exists(d["path"]):
            for f in os.listdir(d["path"]):
                fpath = os.path.join(d["path"], f)
                if os.path.isfile(fpath):
                    files.append({
                        "name": f,
                        "date": d["display"],
                        "date_raw": d["name"],
                        "size": os.path.getsize(fpath),
                        "type": f.split(".")[-1].upper()
                    })
    return jsonify({"files": files, "count": len(files)})

# ---- 状态 ----
@app.route("/api/status")
def api_status():
    return jsonify({
        "collecting": app_state["collecting"],
        "generating": app_state["generating"],
        "task_status": app_state["task_status"],
        "last_collect_time": app_state["last_collect_time"],
        "last_generate_time": app_state["last_generate_time"]
    })

# ============ 启动 ============
def run_web(host="127.0.0.1", port=5000, debug=False):
    add_log("info", f"Web 服务启动: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)

if __name__ == "__main__":
    run_web()
