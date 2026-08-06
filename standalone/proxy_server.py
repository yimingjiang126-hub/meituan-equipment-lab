# -*- coding: utf-8 -*-
"""
美境 AI 设计师 - 独立代理服务器
为 standalone/index.html 提供 /api/generate-material 接口

使用方法：
    python proxy_server.py

默认监听端口：8081
"""
import os
import sys
import uuid
import tempfile

# 把项目根目录加入路径
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from generators.meigen_material import (
    generate_material,
    start_generate_task,
    get_task_status,
    MEIGEN_SCRIPT_DIR,
    GENERATE_PY,
    LOCAL_IMAGE_DIR
)

app = Flask(__name__)
CORS(app)  # 允许跨域，前端在8080端口访问8081

# LLM 配置（必须在所有使用它的函数之前定义）
LLM_CONFIG = {
    "openai_api_key": os.environ.get("OPENAI_API_KEY", "sk-e606ed1b8e3344879f109cc2b214f7c2"),
    "openai_base_url": os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com"),
    "openai_model": os.environ.get("OPENAI_MODEL", "deepseek-chat"),
    "claude_api_key": os.environ.get("CLAUDE_API_KEY", ""),
    "claude_base_url": os.environ.get("CLAUDE_BASE_URL", "https://api.anthropic.com"),
    "claude_model": os.environ.get("CLAUDE_MODEL", "claude-3-sonnet-20240229"),
}


@app.route("/api/generate-material", methods=["POST"])
def api_generate_material():
    """提交美境 AI 物料生成任务"""
    try:
        # 调试：打印接收到的表单数据
        print(f"[DEBUG] 收到 generate-material 请求")
        print(f"[DEBUG] form keys: {list(request.form.keys())}")
        print(f"[DEBUG] files keys: {list(request.files.keys())}")
        for k, v in request.form.items():
            print(f"[DEBUG] form[{k}] = {v[:50] if v else 'empty'}...")

        # 检查美境脚本是否存在
        if not os.path.exists(GENERATE_PY):
            return jsonify({
                "status": "failed",
                "error": f"美境服务未配置，请检查 meigen-cli 安装。脚本路径：{GENERATE_PY}"
            }), 200

        prompt = request.form.get("prompt", "")
        if not prompt:
            return jsonify({"error": "图片生成描述不能为空"}), 400

        # 其他参数
        width = request.form.get("width", "1080")
        height = request.form.get("height", "1920")
        title = request.form.get("title", "")
        subtitle = request.form.get("subtitle", "")
        style = request.form.get("style", "国漫风")

        # 生成任务ID
        task_id = "mat_" + uuid.uuid4().hex[:8]

        # 保存上传的图片（支持多张）
        image_paths = []
        if "image" in request.files:
            files = request.files.getlist("image")
            for file in files:
                if file.filename:
                    ext = os.path.splitext(file.filename)[1] or ".png"
                    temp_path = os.path.join(
                        tempfile.gettempdir(),
                        f"upload_{uuid.uuid4().hex}{ext}"
                    )
                    file.save(temp_path)
                    image_paths.append(temp_path)

        # 启动生成任务（后台线程）
        start_generate_task(task_id, width, height, title, subtitle, style, image_paths, prompt)

        return jsonify({
            "status": "started",
            "task_id": task_id,
            "msg": "美境AI物料生成任务已提交，正在生成中..."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-material/status/<task_id>")
def api_generate_material_status(task_id: str):
    """查询物料生成任务状态"""
    try:
        status = get_task_status(task_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.route("/health")
def health_check():
    """健康检查"""
    meigen_ready = os.path.exists(GENERATE_PY)
    return jsonify({
        "status": "ok",
        "meigen_ready": meigen_ready,
        "meigen_script_dir": MEIGEN_SCRIPT_DIR
    })


@app.route("/static/images/generated/<path:filename>")
def serve_generated_image(filename):
    """提供生成的图片文件访问"""
    file_path = os.path.join(LOCAL_IMAGE_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "图片不存在"}), 404
    return send_file(file_path)


# ========== 数据持久化与定时更新 ==========
import json
import random
import threading
import time
from datetime import datetime, timedelta

# 数据文件路径
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
TOPICS_FILE = os.path.join(DATA_DIR, "xhs_topics.json")
RANK_FILE = os.path.join(DATA_DIR, "xhs_rank.json")
PROFILE_FILE = os.path.join(DATA_DIR, "xhs_profile.json")
TREND_FILE = os.path.join(DATA_DIR, "xhs_trend.json")

# 小红书账号配置
XHS_PROFILE_URL = "https://www.xiaohongshu.com/user/profile/672e12dc000000001c01aef0"
XHS_USER_ID = "63048899491"

# 预置话题模板库（按主题分类，生成时混合抽取，确保多样性）
TOPIC_TEMPLATES = {
    # 装备测评类 — 美团装备研究所核心内容
    "装备测评": [
        {"title": "头盔不是越贵越好｜3C认证+通风设计，这3款闭眼入", "tag": "#头盔测评", "product": "头盔", "heat": 11234, "category": "测评", "reason": "头盔是骑手刚需装备，测评类内容收藏率高"},
        {"title": "50元手套 vs 500元手套｜摔过一次才知道差距", "tag": "#手套测评", "product": "手套", "heat": 9876, "category": "对比", "reason": "手套价格差异大，对比内容引发讨论"},
        {"title": "手机支架避坑｜这4个雷区别踩，省下大几百", "tag": "#手机支架", "product": "手机支架", "heat": 8901, "category": "避坑", "reason": "手机支架是高频踩坑品类，避坑内容实用"},
        {"title": "餐箱保温实测｜3小时后外卖还是热的？", "tag": "#保温餐箱", "product": "餐箱", "heat": 9234, "category": "测评", "reason": "餐箱保温效果直接影响顾客评价"},
        {"title": "蓝牙耳机横评｜导航清晰+听歌爽，这3款闭眼入", "tag": "#蓝牙耳机", "product": "耳机", "heat": 10567, "category": "测评", "reason": "蓝牙耳机是骑手日常必备，测评需求大"},
        {"title": "雨衣选购指南｜分体vs连体，跑了3年我选这个", "tag": "#雨衣", "product": "雨衣", "heat": 8765, "category": "指南", "reason": "雨季刚需，选购指南收藏率高"},
        {"title": "夜间照明装备清单｜这5样让你夜跑安全翻倍", "tag": "#夜间照明", "product": "照明灯", "heat": 8345, "category": "清单", "reason": "夜间安全是骑手核心痛点"},
        {"title": "护膝真的有用吗？老寒腿骑手60天实测", "tag": "#护膝", "product": "护膝", "heat": 9123, "category": "测评", "reason": "长期跑单膝盖问题普遍，测评有共鸣"},
        {"title": "电动车续航实测｜这3招让续航多跑30公里", "tag": "#电动车续航", "product": "电动车", "heat": 10890, "category": "测评", "reason": "续航焦虑是骑手最大痛点之一"},
        {"title": "新品开箱｜这款装备刚上市，第一手体验来了", "tag": "#新品开箱", "product": "新装备", "heat": 9678, "category": "开箱", "reason": "新品开箱引发好奇和期待"},
        {"title": "装备红黑榜｜这10件必买，这5件别碰", "tag": "#红黑榜", "product": "装备", "heat": 12456, "category": "榜单", "reason": "红黑榜类内容天然具备讨论属性"},
        {"title": "腰靠餐箱实测｜跑单8小时腰不酸的秘密", "tag": "#腰靠餐箱", "product": "餐箱", "heat": 7890, "category": "测评", "reason": "腰靠餐箱解决长期跑单腰痛问题"},
    ],
    # 骑手日常故事类 — 情感共鸣、人设建立
    "骑手日常": [
        {"title": "跑单时最暖的瞬间｜顾客一句话让我感动一整天", "tag": "#跑单故事", "product": "故事", "heat": 10234, "category": "故事", "reason": "温情故事容易引发共鸣和传播"},
        {"title": "骑手与顾客的相爱相杀｜这些备注笑死我了", "tag": "#搞笑备注", "product": "搞笑", "heat": 11567, "category": "搞笑", "reason": "搞笑内容传播率高，容易引发互动"},
        {"title": "深夜收工路上｜这个城市凌晨2点还在运转", "tag": "#深夜跑单", "product": "日常", "heat": 9876, "category": "日常", "reason": "深夜跑单有独特的氛围感和故事性"},
        {"title": "跑了三年单，这些歌已经刻进DNA了", "tag": "#骑手歌单", "product": "音乐", "heat": 8901, "category": "共鸣", "reason": "歌单分享是骑手群体的共同记忆"},
        {"title": "最让骑手崩溃的10件事｜第5个我真忍不了", "tag": "#骑手吐槽", "product": "吐槽", "heat": 10543, "category": "吐槽", "reason": "吐槽内容容易引发同行共鸣和讨论"},
        {"title": "新人骑手跑单前7天｜我踩过的坑和总结的经验", "tag": "#新人指南", "product": "经验", "heat": 9234, "category": "经验", "reason": "新人经验分享，实用干货+互动拉满"},
        {"title": "骑手午餐吃什么｜这5家外卖店性价比最高", "tag": "#午餐推荐", "product": "餐饮", "heat": 8345, "category": "推荐", "reason": "骑手日常饮食话题，贴近生活"},
        {"title": "跑单路线优化｜每天少跑10公里多赚50块", "tag": "#路线优化", "product": "技巧", "heat": 9789, "category": "技巧", "reason": "路线优化直接影响收入，实用性强"},
        {"title": "骑手与保安的恩怨情仇｜这些小区我能吐槽一年", "tag": "#骑手日常", "product": "日常", "heat": 10123, "category": "吐槽", "reason": "骑手vs保安是经典话题，容易引发共鸣"},
        {"title": "雨天跑单实录｜这一身湿透，但收入翻倍", "tag": "#雨天跑单", "product": "日常", "heat": 8876, "category": "故事", "reason": "雨天跑单有画面感，故事性强"},
        {"title": "骑手收入大揭秘｜月入过万真的吗？", "tag": "#骑手收入", "product": "收入", "heat": 11234, "category": "揭秘", "reason": "收入话题天然吸引眼球和讨论"},
        {"title": "717骑士节｜这一天，我想对每一位骑手说声谢谢", "tag": "#717骑士节", "product": "骑士节", "heat": 9678, "category": "共鸣", "reason": "骑士节情感节点，容易引发共鸣"},
    ],
    # 季节装备类 — 结合当季痛点，但不全是季节
    "季节装备": [
        {"title": "夏季防晒衣横评｜UPF50+真的有用吗？", "tag": "#防晒衣", "product": "防晒衣", "heat": 12456, "category": "测评", "reason": "夏季防晒刚需，搜索量最高"},
        {"title": "夏天跑单防暑指南｜中暑一次损失300+", "tag": "#防暑", "product": "防暑", "heat": 11234, "category": "指南", "reason": "夏季高温防暑，骑手最关心"},
        {"title": "夏季冰袖实测｜这3款降温效果最真实", "tag": "#冰袖", "product": "冰袖", "heat": 9876, "category": "测评", "reason": "夏季冰袖是刚需装备"},
        {"title": "夏季跑单神器｜这3个小物让我少流一半汗", "tag": "#夏季装备", "product": "装备", "heat": 10567, "category": "推荐", "reason": "夏季降温神器，关注度高"},
        {"title": "冬季保暖手套实测｜零下5度也能暖", "tag": "#保暖手套", "product": "保暖手套", "heat": 11234, "category": "测评", "reason": "冬季保暖刚需，关注度高"},
        {"title": "冬季骑手装备清单｜从头到脚，少一样都冷", "tag": "#冬季装备", "product": "冬季装备", "heat": 10567, "category": "清单", "reason": "冬季装备清单，收藏率高"},
        {"title": "冬季电动车续航实测｜这3招能多跑50公里", "tag": "#电动车续航", "product": "电动车", "heat": 9876, "category": "测评", "reason": "冬季续航痛点，实用内容"},
        {"title": "春季装备换新季｜这5件该淘汰换新了", "tag": "#装备换新", "product": "装备", "heat": 9123, "category": "清单", "reason": "春季换新高峰，引发收藏"},
        {"title": "秋季护膝提前备｜老寒腿预防从现在开始", "tag": "#护膝", "product": "护膝", "heat": 8345, "category": "指南", "reason": "秋季护膝预防，提前准备"},
        {"title": "雨季骑手自救指南｜这5样雨天装备缺一不可", "tag": "#雨天装备", "product": "雨衣", "heat": 9234, "category": "清单", "reason": "雨季刚需，雨天装备需求"},
    ],
    # 效率技巧类 — 提升收入、节省时间
    "效率技巧": [
        {"title": "跑单时段选择｜这3个时间段最容易出大单", "tag": "#跑单技巧", "product": "技巧", "heat": 9789, "category": "技巧", "reason": "时段选择直接影响收入"},
        {"title": "午高峰 vs 平峰期｜同样时间收入差3倍", "tag": "#收入对比", "product": "收入", "heat": 9234, "category": "对比", "reason": "收入对比数据直观，引发关注"},
        {"title": "电动车充电技巧｜这样充电池多用2年", "tag": "#充电技巧", "product": "电动车", "heat": 8901, "category": "技巧", "reason": "电池养护知识，骑手实用"},
        {"title": "手机省电设置｜跑单一天不用带充电宝", "tag": "#手机省电", "product": "手机", "heat": 8345, "category": "技巧", "reason": "手机续航是跑单痛点，技巧实用"},
        {"title": "差评申诉成功率提升｜这3个话术亲测有效", "tag": "#差评申诉", "product": "技巧", "heat": 7654, "category": "技巧", "reason": "差评影响收入，申诉技巧需求大"},
        {"title": "跑单2年总结｜这些装备让我多赚了30%", "tag": "#赚钱技巧", "product": "技巧", "heat": 10234, "category": "经验", "reason": "收入提升经验，引发收藏和关注"},
        {"title": "新手骑手装备清单｜这8样必备，少一样都难受", "tag": "#新手装备", "product": "装备", "heat": 9123, "category": "清单", "reason": "新人装备清单，收藏率高"},
        {"title": "导航设置优化｜这2个选项让你少走弯路", "tag": "#导航技巧", "product": "导航", "heat": 7890, "category": "技巧", "reason": "导航效率影响跑单速度"},
        {"title": "骑手如何维护高评分｜这5个细节别忽略", "tag": "#评分维护", "product": "技巧", "heat": 8567, "category": "技巧", "reason": "评分影响派单优先级"},
        {"title": "雨天补贴攻略｜天气差的时候怎么多赚", "tag": "#雨天补贴", "product": "补贴", "heat": 8345, "category": "技巧", "reason": "天气补贴是额外收入来源"},
    ],
    # 安全警示类 — 骑手安全相关内容
    "安全警示": [
        {"title": "夜间跑单安全装备｜反光条+照明+警示灯", "tag": "#安全装备", "product": "安全装备", "heat": 8901, "category": "清单", "reason": "夜间安全是骑手核心关切"},
        {"title": "头盔不是摆设｜一次事故让我明白3C认证有多重要", "tag": "#头盔安全", "product": "头盔", "heat": 10234, "category": "共鸣", "reason": "安全意识类内容容易引发共鸣"},
        {"title": "骑手最危险的5个路段｜老司机都绕道走", "tag": "#安全路段", "product": "安全", "heat": 9567, "category": "避坑", "reason": "路段安全信息，实用价值高"},
        {"title": "电动车刹车检查｜这3个信号说明该换了", "tag": "#刹车检查", "product": "电动车", "heat": 8345, "category": "指南", "reason": "刹车安全直接关系生命安全"},
        {"title": "雨天跑单防滑技巧｜这3招保平安", "tag": "#防滑技巧", "product": "防滑", "heat": 8765, "category": "技巧", "reason": "雨天路滑是事故高发场景"},
        {"title": "骑手保险怎么选｜这2种最实用", "tag": "#骑手保险", "product": "保险", "heat": 7234, "category": "指南", "reason": "保险是骑手保障，选择指南实用"},
        {"title": "夏季中暑预警信号｜出现这3个症状马上休息", "tag": "#中暑预警", "product": "防暑", "heat": 8901, "category": "指南", "reason": "夏季中暑高发，预警内容重要"},
        {"title": "骑手常见交通事故｜这5种情况最易发生", "tag": "#交通安全", "product": "安全", "heat": 9456, "category": "避坑", "reason": "交通事故预防，安全意识内容"},
    ]
}

# 预置热点榜单模板
RANK_TEMPLATES = [
    [{"rank": 1, "title": "跑单时的神级操作", "heat": "14.7w", "tag": "热梗"},
     {"rank": 2, "title": "骑手与顾客的相爱相杀", "heat": "10.6w", "tag": "热梗"},
     {"rank": 3, "title": "骑手搞笑对话实录", "heat": "10.4w", "tag": "热梗"},
     {"rank": 4, "title": "骑手防晒装备真实测评", "heat": "9.5w", "tag": "热点"},
     {"rank": 5, "title": "适合跑单听的电子音乐", "heat": "7.0w", "tag": "BGM"},
     {"rank": 6, "title": "夜间跑单照明装备", "heat": "6.0w", "tag": "热点"},
     {"rank": 7, "title": "骑手解压歌单分享", "heat": "5.8w", "tag": "BGM"},
     {"rank": 8, "title": "骑手夏日装备红黑榜", "heat": "5.7w", "tag": "热点"},
     {"rank": 9, "title": "骑手头盔选购全攻略", "heat": "5.6w", "tag": "热点"},
     {"rank": 10, "title": "骑手提神醒脑歌单", "heat": "4.3w", "tag": "BGM"}],
    [{"rank": 1, "title": "骑手雨天装备实测", "heat": "12.3w", "tag": "热点"},
     {"rank": 2, "title": "顾客奇葩备注大赏", "heat": "11.5w", "tag": "热梗"},
     {"rank": 3, "title": "骑手装备避坑指南", "heat": "9.8w", "tag": "热点"},
     {"rank": 4, "title": "跑单遇到的最暖瞬间", "heat": "8.6w", "tag": "故事"},
     {"rank": 5, "title": "骑手冬季保暖秘籍", "heat": "7.9w", "tag": "热点"},
     {"rank": 6, "title": "电动车续航实测对比", "heat": "7.2w", "tag": "测评"},
     {"rank": 7, "title": "骑手与保安的恩怨情仇", "heat": "6.8w", "tag": "热梗"},
     {"rank": 8, "title": "新手骑手第一天实录", "heat": "6.5w", "tag": "日常"},
     {"rank": 9, "title": "骑手午餐吃什么", "heat": "5.9w", "tag": "日常"},
     {"rank": 10, "title": "骑手省钱小技巧", "heat": "5.4w", "tag": "技巧"}],
    [{"rank": 1, "title": "717骑士节限定装备", "heat": "15.2w", "tag": "限定"},
     {"rank": 2, "title": "骑手跑单vlog拍摄技巧", "heat": "11.8w", "tag": "技巧"},
     {"rank": 3, "title": "骑手收入大揭秘", "heat": "10.5w", "tag": "揭秘"},
     {"rank": 4, "title": "最让骑手崩溃的10件事", "heat": "9.7w", "tag": "吐槽"},
     {"rank": 5, "title": "骑手装备收纳神器", "heat": "8.9w", "tag": "推荐"},
     {"rank": 6, "title": "骑手导航翻车现场", "heat": "8.2w", "tag": "搞笑"},
     {"rank": 7, "title": "骑手护膝测评", "heat": "7.6w", "tag": "测评"},
     {"rank": 8, "title": "骑手与商家的日常", "heat": "7.1w", "tag": "日常"},
     {"rank": 9, "title": "骑手蓝牙耳机推荐", "heat": "6.5w", "tag": "推荐"},
     {"rank": 10, "title": "骑手跑单音乐歌单", "heat": "6.0w", "tag": "BGM"}]
]


def _get_season(month=None):
    """根据月份返回季节"""
    if month is None:
        month = datetime.now().month
    if month in (3, 4, 5):
        return "春季"
    elif month in (6, 7, 8):
        return "夏季"
    elif month in (9, 10, 11):
        return "秋季"
    else:
        return "冬季"


def _generate_topics_data(use_llm=False):
    """生成话题推荐数据"""
    now = datetime.now()
    season = _get_season(now.month)

    # 尝试用LLM生成（如果配置了API Key）
    if use_llm and (LLM_CONFIG["openai_api_key"] or LLM_CONFIG["claude_api_key"]):
        try:
            prompt = f"""你是小红书内容运营专家，服务于骑手账号"美团装备研究所"。
现在是{now.month}月（{season}），请为这个账号推荐10个适合当季发布的内容话题。

【推荐原则】
1. 话题要结合当季骑手的真实痛点和需求
2. 话题类型要多样：装备测评、骑手日常、情感共鸣、实用技巧、趣味互动各占一些
3. 每个话题要有明确的内容方向，不能太泛
4. 话题要有小红书平台特征：适合图文笔记、有互动空间
5. 合理预估热度值（1000-15000区间）

请返回严格JSON格式（不要任何markdown标记）：
{{"topics": [
  {{"id": 1, "title": "话题标题", "tag": "#标签", "product": "涉及产品/主题", "heat": 8500, "category": "类型", "reason": "推荐理由"}}
]}}"""
            content = _call_llm(prompt, temperature=0.9)
            result = _extract_json(content)
            if result and "topics" in result:
                result["last_updated"] = now.strftime("%Y-%m-%d %H:%M:%S")
                result["source"] = "llm"
                result["total"] = len(result["topics"])
                result["next_update"] = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
                return result
        except Exception as e:
            print(f"[WARN] LLM话题生成失败，回退模板: {e}")

    # 模板模式：从5个主题池中混合抽取，确保多样性
    # 装备测评、骑手日常、季节装备、效率技巧、安全警示
    all_pools = list(TOPIC_TEMPLATES.keys())  # ["装备测评", "骑手日常", "季节装备", "效率技巧", "安全警示"]
    selected = []
    used_indices = {pool: set() for pool in all_pools}

    # 第一步：每个主题池至少抽1条，确保覆盖面
    for pool_name in all_pools:
        pool = TOPIC_TEMPLATES[pool_name]
        available = [i for i in range(len(pool)) if i not in used_indices[pool_name]]
        if available:
            idx = random.choice(available)
            used_indices[pool_name].add(idx)
            topic = dict(pool[idx])
            topic["pool"] = pool_name
            selected.append(topic)

    # 第二步：再抽5条，按权重随机选池
    # 权重：装备测评和骑手日常权重更高（账号核心内容）
    weights = {"装备测评": 3, "骑手日常": 3, "季节装备": 2, "效率技巧": 2, "安全警示": 1}
    for _ in range(5):
        # 加权随机选池
        pool_choices = []
        for p in all_pools:
            pool_choices.extend([p] * weights.get(p, 1))
        pool_name = random.choice(pool_choices)
        pool = TOPIC_TEMPLATES[pool_name]
        available = [i for i in range(len(pool)) if i not in used_indices[pool_name]]
        if not available:
            # 该池已抽完，从其他池补
            for alt_pool in all_pools:
                alt_available = [i for i in range(len(TOPIC_TEMPLATES[alt_pool])) if i not in used_indices[alt_pool]]
                if alt_available:
                    pool_name = alt_pool
                    pool = TOPIC_TEMPLATES[alt_pool]
                    available = alt_available
                    break
        if available:
            idx = random.choice(available)
            used_indices[pool_name].add(idx)
            topic = dict(pool[idx])
            topic["pool"] = pool_name
            selected.append(topic)

    # 第三步：微调热度（随机波动 ±15%）
    for topic in selected:
        base_heat = topic["heat"]
        topic["heat"] = int(base_heat * random.uniform(0.85, 1.15))

    # 按热度排序
    selected.sort(key=lambda x: x["heat"], reverse=True)
    for i, t in enumerate(selected, 1):
        t["id"] = i
        # 移除内部标记
        t.pop("pool", None)

    return {
        "topics": selected,
        "last_updated": now.strftime("%Y-%m-%d %H:%M:%S"),
        "next_update": (now + timedelta(days=1)).replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S"),
        "source": "template",
        "total": len(selected)
    }


def _generate_rank_data():
    """生成热点榜单数据"""
    now = datetime.now()
    # 随机选择一套模板
    base = random.choice(RANK_TEMPLATES)
    items = []
    for i, item in enumerate(base, 1):
        new_item = dict(item)
        new_item["rank"] = i
        new_item["date"] = now.strftime("%Y-%m-%d")
        # URL 编码处理
        new_item["url"] = f"https://www.xiaohongshu.com/search_result?keyword={new_item['title']}"
        items.append(new_item)

    return {
        "items": items,
        "last_updated": now.strftime("%Y-%m-%d %H:%M:%S"),
        "next_update": (now + timedelta(days=1)).replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "total": len(items)
    }


def _generate_trend_data():
    """生成账号互动量趋势数据（近24小时，每2小时一个点）
    
    模拟真实的社交账号互动曲线：
    - 基于账号规模（5.1万粉丝）确定基准量级
    - 按时间段设置权重反映真实用户活跃规律
    - 加入随机波动使每天数据不同
    """
    now = datetime.now()
    
    # 基准互动量（根据5.1万粉丝估算：每小时互动约 2000-8000）
    base_interaction = 4500
    
    # 24小时时段权重（模拟真实用户活跃曲线）
    # 索引0=当前小时，向前推每2小时一个点
    hourly_weights = [
        0.45,  # 00:00-02:00 深夜低谷
        0.35,  # 02:00-04:00 深夜最低
        0.30,  # 04:00-06:00 凌晨最低
        0.50,  # 06:00-08:00 清晨开始活跃
        0.85,  # 08:00-10:00 早高峰
        1.00,  # 10:00-12:00 上午高峰
        0.95,  # 12:00-14:00 午间高峰
        0.80,  # 14:00-16:00 下午平稳
        0.90,  # 16:00-18:00 傍晚回升
        1.15,  # 18:00-20:00 晚间高峰
        1.05,  # 20:00-22:00 晚间活跃
        0.70,  # 22:00-00:00 夜间下降
    ]
    
    # 根据当前时间计算各时段的时间标签
    current_hour = now.hour
    # 将当前小时对齐到偶数小时
    aligned_hour = (current_hour // 2) * 2
    
    hours = []
    values = []
    
    # 生成12个数据点（每2小时一个，覆盖近24小时）
    for i in range(12):
        # 计算该点对应的小时（从当前时间往前推）
        point_hour = (aligned_hour - i * 2) % 24
        # 格式化时间标签
        hours.insert(0, f"{point_hour:02d}:00")
        
        # 获取对应时段的权重
        weight_idx = point_hour // 2
        weight = hourly_weights[weight_idx]
        
        # 计算该时段的互动量：基准 × 权重 × 随机波动(±15%)
        random_factor = random.uniform(0.85, 1.15)
        value = int(base_interaction * weight * random_factor)
        values.insert(0, value)
    
    peak = max(values)
    avg = int(sum(values) / len(values))
    min_val = min(values)
    current = values[-1]
    
    return {
        "hours": hours,
        "values": values,
        "peak": peak,
        "avg": avg,
        "min": min_val,
        "current": current,
        "last_updated": now.strftime("%Y-%m-%d %H:%M:%S"),
        "next_update": (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d")
    }


def _load_data(filepath, default_generator):
    """加载数据文件，不存在则生成"""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 加载数据文件失败 {filepath}: {e}")

    # 生成默认数据
    data = default_generator()
    _save_data(filepath, data)
    return data


def _save_data(filepath, data):
    """保存数据到文件"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 保存数据文件失败 {filepath}: {e}")


def _should_refresh(data):
    """检查数据是否需要刷新（超过当天10点且未更新）"""
    now = datetime.now()
    # 如果今天已经过了10点，检查数据是否是今天10点后更新的
    today_10am = now.replace(hour=10, minute=0, second=0, microsecond=0)

    if now < today_10am:
        # 还没到10点，不需要刷新
        return False

    last_updated_str = data.get("last_updated", "")
    if not last_updated_str:
        return True

    try:
        last_updated = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")
        # 如果上次更新是在今天10点之前，需要刷新
        return last_updated < today_10am
    except Exception:
        return True


def _auto_refresh_topics():
    """自动刷新话题数据（定时任务调用）"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始自动刷新话题数据...")
    data = _generate_topics_data(use_llm=True)
    _save_data(TOPICS_FILE, data)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 话题数据已刷新，共{len(data['topics'])}条")


def _auto_refresh_rank():
    """自动刷新榜单数据（定时任务调用）"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始自动刷新榜单数据...")
    data = _generate_rank_data()
    _save_data(RANK_FILE, data)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 榜单数据已刷新")


def _fetch_xhs_profile():
    """从小红书网页爬取账号数据（未登录状态下可能获取到模糊值）"""
    import urllib.request
    import re

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.xiaohongshu.com/',
    }

    try:
        req = urllib.request.Request(XHS_PROFILE_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode('utf-8', errors='replace')

        result = {
            "user_id": XHS_USER_ID,
            "source": "web_crawl",
            "crawl_status": "success"
        }

        # 解析昵称
        nick_match = re.search(r'<h1[^>]*class="[^"]*nickname[^"]*"[^>]*>([^<]+)</h1>', html, re.IGNORECASE)
        if not nick_match:
            nick_match = re.search(r'"nickname"\s*:\s*"([^"]+)"', html)
        if nick_match:
            result["nickname"] = nick_match.group(1).strip()

        # 解析小红书号 / red_id
        red_id_match = re.search(r'小红书号\s*[:：]?\s*(\d+)', html)
        if not red_id_match:
            red_id_match = re.search(r'redId\s*[:：]?\s*(\d+)', html, re.IGNORECASE)
        if red_id_match:
            result["user_id"] = red_id_match.group(1).strip()

        # 解析 IP 属地
        ip_match = re.search(r'IP属地\s*[:：]?\s*([^<\s]+)', html)
        if ip_match:
            result["ip_location"] = ip_match.group(1).strip()

        # 解析简介
        # 简介可能在 meta description 或特定 div 中
        desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html, re.IGNORECASE)
        if desc_match:
            desc = desc_match.group(1).strip()
            if desc and len(desc) < 200:
                result["bio"] = desc

        # 解析统计数据（关注、粉丝、获赞）
        # 小红书网页版中，统计数据通常在 user-interactions 或 stats 区域
        stats = {}

        # 方法1：从 HTML 中查找 count + shows 的组合（按顺序：关注、粉丝、获赞与收藏）
        stats_section = re.search(r'<div[^>]*class="[^"]*user-interactions[^"]*"[^>]*>([\s\S]*?)</div>', html, re.IGNORECASE)
        if stats_section:
            section = stats_section.group(1)
            counts = re.findall(r'<span[^>]*class="count"[^>]*>([^<]+)</span>', section)
            labels = re.findall(r'<span[^>]*class="shows"[^>]*>([^<]+)</span>', section)
            # 小红书页面统计顺序固定：关注(0)、粉丝(1)、获赞与收藏(2)
            mapping = ['following', 'followers', 'likes_collects']
            for i in range(min(len(counts), len(mapping))):
                val = counts[i].strip()
                if val and val not in ('--', '-'):
                    stats[mapping[i]] = val

        # 方法2：如果方法1没拿到，全局搜索
        if not stats.get('following') or not stats.get('followers'):
            all_stats = re.findall(r'<span[^>]*class="count"[^>]*>([^<]+)</span>\s*<span[^>]*class="shows"[^>]*>([^<]+)</span>', html)
            mapping = ['following', 'followers', 'likes_collects']
            for i, (val, label) in enumerate(all_stats):
                if i < len(mapping):
                    val = val.strip()
                    if val and val not in ('--', '-'):
                        stats[mapping[i]] = val

        result.update(stats)

        # 笔记数量：网页版通常不直接显示总数，尝试从 API 数据或页面中查找
        note_match = re.search(r'(笔记|作品|发布)\s*[:：]?\s*(\d+)', html)
        if note_match:
            result["notes"] = note_match.group(2)

        return result

    except Exception as e:
        print(f"[WARN] 爬取小红书账号数据失败: {e}")
        return {"source": "web_crawl", "crawl_status": "failed", "error": str(e)}


def _is_fuzzy_value(value):
    """判断数值是否为模糊值（如'1万+'），如果是则不应该覆盖精确值"""
    if not value or not isinstance(value, str):
        return False
    return '+' in value or '万' in value or value in ('--', '-', '')


def _merge_profile_data(old_data, new_data):
    """合并新旧账号数据：保留精确值，用新数据中的确定值更新"""
    merged = dict(old_data) if old_data else {}

    for key, new_val in new_data.items():
        if key in ('source', 'crawl_status', 'error', 'last_updated'):
            continue

        old_val = merged.get(key)

        # 如果新值是模糊值，但旧值是精确值，保留旧值
        if _is_fuzzy_value(new_val) and old_val and not _is_fuzzy_value(old_val):
            continue

        # 如果新值有效，更新
        if new_val and str(new_val).strip():
            merged[key] = new_val

    return merged


def _generate_default_profile():
    """生成默认账号数据（基于真实账号信息）"""
    return {
        "nickname": "美团装备研究所",
        "user_id": XHS_USER_ID,
        "ip_location": "北京",
        "bio": "探索不一样的骑手装备\n认准唯一官号 其他均不是所长哦",
        "avatar": "",
        "following": "8",
        "followers": "5.1万",
        "likes_collects": "6.1万",
        "notes": "81",
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "next_update": (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S"),
        "tags": ["骑手装备", "安全指南", "测评", "装备推荐"],
        "source": "manual"
    }


def _auto_refresh_profile():
    """自动刷新账号数据（定时任务调用）"""
    global profile_data
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始自动刷新账号数据...")
    old_data = profile_data if 'profile_data' in globals() else _load_data(PROFILE_FILE, _generate_default_profile)
    new_data = _fetch_xhs_profile()

    if new_data.get("crawl_status") == "success":
        merged = _merge_profile_data(old_data, new_data)
        merged["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        merged["next_update"] = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        merged["source"] = "auto_crawl"
        _save_data(PROFILE_FILE, merged)
        profile_data = merged
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 账号数据已刷新，来源: {merged.get('source')}")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 账号数据刷新失败，保留现有数据")


def _auto_refresh_trend():
    """自动刷新趋势数据（定时任务调用，每2小时刷新一次）"""
    global trend_data
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始自动刷新趋势数据...")
    trend_data = _generate_trend_data()
    _save_data(TREND_FILE, trend_data)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 趋势数据已刷新，峰值: {trend_data.get('peak')}, 当前: {trend_data.get('current')}")


def _auto_refresh_all():
    """自动刷新所有数据"""
    _auto_refresh_topics()
    _auto_refresh_rank()
    _auto_refresh_profile()
    _auto_refresh_trend()


def _schedule_daily_refresh():
    """设置每天10点的定时刷新任务，启动时若已错过当天10点则补刷"""
    def _should_refresh_today():
        """检查今天10点后数据是否已刷新过"""
        today_10am = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        if datetime.now() < today_10am:
            return False  # 今天10点还没到，不需要补刷

        files_to_check = [TOPICS_FILE, RANK_FILE, PROFILE_FILE, TREND_FILE]
        for f in files_to_check:
            if os.path.exists(f):
                mtime = datetime.fromtimestamp(os.path.getmtime(f))
                if mtime > today_10am:
                    return False  # 已有文件在今天10点后更新过
        return True  # 今天10点后没有任何文件更新，需要补刷

    def _run_scheduler():
        while True:
            now = datetime.now()
            # 计算到下一个10:00的时间
            target = now.replace(hour=10, minute=0, second=0, microsecond=0)
            if now >= target:
                # 今天10点已过，目标改为明天10点
                target = target + timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            print(f"[定时任务] 下次数据刷新时间: {target.strftime('%Y-%m-%d %H:%M:%S')}，等待{wait_seconds/3600:.1f}小时")
            time.sleep(wait_seconds)

            # 到达目标时间，执行刷新
            _auto_refresh_all()

    # 启动后台线程
    scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
    scheduler_thread.start()
    print("[定时任务] 已启动每天10:00自动刷新任务")

    # 启动时检查：若今天10点已过但数据未刷新，立即补刷
    if _should_refresh_today():
        print("[定时任务] 检测到今天10:00的数据刷新已错过，立即补刷...")
        _auto_refresh_all()
        print("[定时任务] 补刷完成")


# 初始化数据
topics_data = _load_data(TOPICS_FILE, lambda: _generate_topics_data(use_llm=False))
rank_data = _load_data(RANK_FILE, _generate_rank_data)
profile_data = _load_data(PROFILE_FILE, _generate_default_profile)
trend_data = _load_data(TREND_FILE, _generate_trend_data)

# ========== LLM API 代理转发 ==========
import urllib.request
import urllib.error


def _call_llm(prompt, temperature=0.8, max_tokens=4000):
    """统一 LLM 调用入口，优先 OpenAI/DeepSeek，回退 Claude"""
    # 优先使用 OpenAI/DeepSeek
    api_key = LLM_CONFIG["openai_api_key"]
    if api_key:
        base_url = LLM_CONFIG["openai_base_url"].rstrip("/")
        model = LLM_CONFIG["openai_model"]
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        req = urllib.request.Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("choices") and result["choices"][0].get("message"):
                    return result["choices"][0]["message"]["content"]
                raise Exception("API 返回格式异常")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")[:500]
            if e.code == 401:
                raise Exception(f"API Key 无效或已过期，请检查 proxy_server.py 中的 LLM_CONFIG.openai_api_key。当前 key 前8位: {api_key[:8]}...")
            elif e.code == 402:
                raise Exception(f"API Key 余额不足，请充值。当前 key 前8位: {api_key[:8]}...")
            elif e.code == 429:
                raise Exception("API 调用频率过高，请稍后重试")
            else:
                raise Exception(f"API 错误 HTTP {e.code}: {error_body}")

    # 回退 Claude
    api_key = LLM_CONFIG["claude_api_key"]
    if api_key:
        base_url = LLM_CONFIG["claude_base_url"].rstrip("/")
        model = LLM_CONFIG["claude_model"]
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }
        req = urllib.request.Request(
            f"{base_url}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("content") and result["content"][0].get("text"):
                return result["content"][0]["text"]
        raise Exception("Claude 返回格式异常")

    raise Exception("未配置任何 LLM API Key（OPENAI_API_KEY 或 CLAUDE_API_KEY）")


def _extract_json(text):
    """从 LLM 回复中提取 JSON"""
    # 直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # markdown 代码块
    import re
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 提取第一个 {...}
    m = re.search(r'(\{[\s\S]*\})', text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return None


@app.route("/api/llm-generate", methods=["POST"])
def api_llm_generate():
    """通用 LLM 代理转发（保持向后兼容）"""
    try:
        data = request.get_json() or {}
        prompt = data.get("prompt", "")
        if not prompt:
            return jsonify({"error": "缺少 prompt 参数"}), 400
        content = _call_llm(prompt)
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 话题推荐 ==========
@app.route("/api/llm-topics", methods=["POST"])
def api_llm_topics():
    """LLM 生成话题推荐"""
    try:
        data = request.get_json() or {}
        season = data.get("season", "")
        month = data.get("month", datetime.now().month)
        recent_topics = data.get("recentTopics", [])

        # 季节感知
        if not season:
            if month in (3, 4, 5):
                season = "春季"
            elif month in (6, 7, 8):
                season = "夏季"
            elif month in (9, 10, 11):
                season = "秋季"
            else:
                season = "冬季"

        # 已发布话题去重提示
        recent_hint = ""
        if recent_topics:
            recent_hint = f"\n\n【近期已发布的话题（请避免重复）】\n" + "\n".join(f"- {t}" for t in recent_topics[:10])

        prompt = f"""你是小红书内容运营专家，服务于骑手账号"美团装备研究所"。
账号定位：美团骑手装备测评、骑手日常分享、骑手生活方式内容。
人设：所长——一个真实送单的骑手，幽默实在，说话像跟兄弟聊天。

现在是{month}月（{season}），请为这个账号推荐10个适合当季发布的内容话题。

【推荐原则】
1. 话题要结合当季骑手的真实痛点和需求（{season}气候、装备需求、节日活动等）
2. 话题类型要多样：装备测评、骑手日常、情感共鸣、实用技巧、趣味互动各占一些
3. 每个话题要有明确的内容方向，不能太泛（比如不要只写"防晒"，而是"骑手防晒面罩横评"）
4. 话题要有小红书平台特征：适合图文笔记、有互动空间、能引发评论讨论
5. 合理预估热度值（1000-15000区间），热度高的话题应该是当季最受关注的痛点
{recent_hint}

请返回严格JSON格式（不要任何markdown标记）：
{{"topics": [
  {{"id": 1, "title": "话题标题", "tag": "#标签", "product": "涉及产品/主题", "heat": 8500, "category": "类型(测评/清单/避坑/日常/故事/对比/指南/穿搭/开箱/推荐)", "reason": "一句话说明为什么推荐这个话题"}}
]}}"""

        content = _call_llm(prompt, temperature=0.9)
        result = _extract_json(content)
        if result and "topics" in result:
            result["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result["source"] = "llm"
            result["total"] = len(result["topics"])
            return jsonify(result)
        return jsonify({"error": "LLM 返回格式不正确", "raw": content[:500]}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 标题生成 ==========
@app.route("/api/llm-titles", methods=["POST"])
def api_llm_titles():
    """LLM 生成标题"""
    try:
        data = request.get_json() or {}
        topic = data.get("topic", "骑手装备")
        count = data.get("count", 8)
        month = data.get("month", datetime.now().month)

        prompt = f"""你是小红书爆款标题专家，服务于骑手账号"美团装备研究所"（人设：所长，真实送单的骑手）。

用户给出了一个话题方向，请根据这个方向生成{count}个小红书爆款标题。

【话题方向】
{topic}

【当前月份】{month}月

【核心规则——最重要】
1. 话题方向是「内容领域」或「选题角度」，不是商品名称
2. 先理解这个方向在骑手日常中对应什么场景、什么痛点、什么故事，再基于理解生成标题
3. 如果话题跟产品/装备相关（如防晒、头盔），标题要围绕真实使用体验，不要硬广
4. 如果话题跟骑手生活相关（如音乐、故事、日常），标题要有情感共鸣和画面感
5. 标题不能出现"美团"二字，不能出现具体品牌名，不能有硬广感

【标题技巧】
- 用数字增加说服力（"3款""跑了2年""省下大几百"）
- 用对比制造冲突感（"50元 vs 500元""以前 vs 现在"）
- 用第一人称增加真实感（"我终于找到""跑了xx天"）
- 用问句引发好奇（"真的有必要吗？""到底值不值？"）
- 善用｜分割前后半句，前半句引流后半句价值
- 长度控制在15-25字

【标题类型要求】
8个标题要覆盖至少5种不同类型，从以下选择：
共鸣、反转、悬念、测评、对比、吐槽、揭秘、经验、指南、清单、避坑、故事、技巧

请返回严格JSON格式（不要任何markdown标记）：
{{"titles": [{{"title": "标题内容", "type": "类型", "score": 9.5}}, ...]}}"""

        content = _call_llm(prompt, temperature=0.85)
        result = _extract_json(content)
        if result and "titles" in result and isinstance(result["titles"], list):
            return jsonify(result)
        return jsonify({"error": "LLM 返回格式不正确", "raw": content[:500]}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 正文生成 ==========
@app.route("/api/llm-body", methods=["POST"])
def api_llm_body():
    """LLM 生成正文"""
    try:
        data = request.get_json() or {}
        title = data.get("title", "")
        topic = data.get("topic", "骑手装备")
        title_type = data.get("type", "经验")

        if not title:
            return jsonify({"error": "缺少 title 参数"}), 400

        prompt = f"""你是"美团装备研究所"的所长，一个真实送单的骑手，现在要写一篇小红书笔记正文。

你的性格：幽默、实在、爱自嘲，说话像跟兄弟聊天，不装不端，偶尔毒舌但心是好的。
你的身份：真实的外卖骑手，每天送单，对装备有真实体验。

【选定标题】{title}
【话题方向】{topic}
【标题类型】{title_type}

【写作要求】
1. 内容分析（4步走，先想清楚再写）：
   - 第一步：分析标题的核心卖点和读者期待——这个标题吸引的人，他们想看到什么？
   - 第二步：列出3个具体场景/痛点——必须是骑手真实会遇到的，有画面感
   - 第三步：构思第一人称叙事线——像跟兄弟聊天一样讲述真实经历
   - 第四步：设计结尾互动——自然地引导评论，不要硬求赞

2. 正文写作要求：
   - 字数：300-500字
   - 第一人称叙述，语气自然，像聊天不像写作文
   - 开头第一句要有「钩子」——让人想继续看下去
   - 中间要有真实细节：具体场景（几楼、什么天气、什么路段）、具体数据（温度、时间、花了多少钱）
   - 如果涉及装备，讲使用体验而非产品参数，讲解决了什么问题
   - 如果涉及生活/情感，要有真实故事和细节，能引发共鸣
   - 不能出现"美团"二字，不能提具体品牌名
   - 结尾互动问题要跟正文内容紧密关联
   - 段落分明，每段4-6行，用空行分段

3. 关键词和标签：
   - keywords：5-8个跟主题相关的搜索词
   - hashtags：5个标签，第一个固定是 #美团装备研究所，第二个固定是 #骑手装备

请返回严格JSON格式（不要任何markdown标记）：
{{"body": {{
  "hook": "开头第一句钩子（15-30字）",
  "pain_points": "场景1描述（2-3句真实场景）\\n场景2描述\\n场景3描述",
  "cta": "结尾互动问题（自然、有趣、跟正文相关）",
  "full_text": "完整正文（300-500字，分段用\\n\\n）",
  "keywords": "关键词1,关键词2,关键词3",
  "hashtags": "#美团装备研究所 #骑手装备 #相关标签1 #相关标签2 #相关标签3"
}}}}"""

        content = _call_llm(prompt, temperature=0.85, max_tokens=4000)
        result = _extract_json(content)
        if result and "body" in result:
            return jsonify(result)
        return jsonify({"error": "LLM 返回格式不正确", "raw": content[:500]}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========== 数据查询与刷新 ==========
@app.route("/api/xhs-topics", methods=["GET"])
def api_xhs_topics():
    """获取小红书话题推荐数据"""
    global topics_data
    # 检查是否需要自动刷新（超过10点且未更新）
    if _should_refresh(topics_data):
        print("[INFO] 话题数据需要刷新，执行自动刷新...")
        topics_data = _generate_topics_data(use_llm=True)
        _save_data(TOPICS_FILE, topics_data)
    return jsonify(topics_data)


@app.route("/api/xhs-rank", methods=["GET"])
def api_xhs_rank():
    """获取小红书热点榜单数据"""
    global rank_data
    if _should_refresh(rank_data):
        print("[INFO] 榜单数据需要刷新，执行自动刷新...")
        rank_data = _generate_rank_data()
        _save_data(RANK_FILE, rank_data)
    return jsonify(rank_data)


@app.route("/api/xhs-topics/refresh", methods=["POST"])
def api_xhs_topics_refresh():
    """手动刷新话题数据"""
    global topics_data
    try:
        topics_data = _generate_topics_data(use_llm=True)
        _save_data(TOPICS_FILE, topics_data)
        return jsonify({"status": "ok", "msg": "话题数据已刷新", "count": len(topics_data.get("topics", [])), "last_updated": topics_data.get("last_updated")})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/xhs-rank/refresh", methods=["POST"])
def api_xhs_rank_refresh():
    """手动刷新榜单数据"""
    global rank_data
    try:
        rank_data = _generate_rank_data()
        _save_data(RANK_FILE, rank_data)
        return jsonify({"status": "ok", "msg": "榜单数据已刷新", "last_updated": rank_data.get("last_updated")})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ========== 账号数据 ==========
@app.route("/api/xhs-profile", methods=["GET"])
def api_xhs_profile():
    """获取小红书账号数据"""
    global profile_data
    # 检查是否需要自动刷新（超过10点且未更新）
    if _should_refresh(profile_data):
        print("[INFO] 账号数据需要刷新，执行自动刷新...")
        _auto_refresh_profile()
    return jsonify(profile_data)


@app.route("/api/xhs-profile/refresh", methods=["POST"])
def api_xhs_profile_refresh():
    """手动刷新账号数据"""
    global profile_data
    try:
        old_data = profile_data
        new_data = _fetch_xhs_profile()

        if new_data.get("crawl_status") == "success":
            merged = _merge_profile_data(old_data, new_data)
            merged["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            merged["next_update"] = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
            merged["source"] = "manual_crawl"
            _save_data(PROFILE_FILE, merged)
            profile_data = merged
            return jsonify({
                "status": "ok",
                "msg": "账号数据已刷新",
                "data": merged,
                "crawl_result": new_data
            })
        else:
            return jsonify({
                "status": "warning",
                "msg": "网页爬取失败，保留现有数据",
                "error": new_data.get("error", "未知错误"),
                "data": old_data
            })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ========== 趋势数据 ==========
@app.route("/api/xhs-trend", methods=["GET"])
def api_xhs_trend():
    """获取账号互动量趋势数据"""
    global trend_data
    return jsonify(trend_data)


@app.route("/api/xhs-trend/refresh", methods=["POST"])
def api_xhs_trend_refresh():
    """手动刷新趋势数据"""
    global trend_data
    try:
        trend_data = _generate_trend_data()
        _save_data(TREND_FILE, trend_data)
        return jsonify({
            "status": "ok",
            "msg": "趋势数据已刷新",
            "data": trend_data
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ========== 连接测试 ==========
@app.route("/api/llm-test", methods=["GET"])
def api_llm_test():
    """测试 LLM 连接是否可用"""
    try:
        content = _call_llm("你好，请回复'连接成功'四个字，不要加任何其他内容。", temperature=0)
        return jsonify({"status": "ok", "content": content, "provider": "openai" if LLM_CONFIG["openai_api_key"] else "claude"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/status", methods=["GET"])
def api_status():
    """获取服务状态和数据更新时间"""
    return jsonify({
        "status": "ok",
        "topics": {
            "last_updated": topics_data.get("last_updated", ""),
            "next_update": topics_data.get("next_update", ""),
            "source": topics_data.get("source", ""),
            "count": len(topics_data.get("topics", []))
        },
        "rank": {
            "last_updated": rank_data.get("last_updated", ""),
            "next_update": rank_data.get("next_update", ""),
            "count": len(rank_data.get("items", []))
        },
        "profile": {
            "last_updated": profile_data.get("last_updated", ""),
            "next_update": profile_data.get("next_update", ""),
            "source": profile_data.get("source", ""),
            "nickname": profile_data.get("nickname", ""),
            "followers": profile_data.get("followers", ""),
            "likes_collects": profile_data.get("likes_collects", "")
        },
        "trend": {
            "last_updated": trend_data.get("last_updated", ""),
            "next_update": trend_data.get("next_update", ""),
            "peak": trend_data.get("peak", 0),
            "current": trend_data.get("current", 0),
            "avg": trend_data.get("avg", 0)
        },
        "llm": {
            "configured": bool(LLM_CONFIG["openai_api_key"] or LLM_CONFIG["claude_api_key"]),
            "provider": "openai" if LLM_CONFIG["openai_api_key"] else ("claude" if LLM_CONFIG["claude_api_key"] else "none")
        }
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    print("=" * 60)
    print("美团装备研究所 - 代理服务器 + LLM 引擎")
    print("=" * 60)
    print(f"美境脚本目录: {MEIGEN_SCRIPT_DIR}")
    print(f"美境脚本就绪: {os.path.exists(GENERATE_PY)}")
    llm_provider = "OpenAI" if LLM_CONFIG["openai_api_key"] else ("Claude" if LLM_CONFIG["claude_api_key"] else "未配置")
    print(f"LLM 引擎: {llm_provider}")
    if LLM_CONFIG["openai_api_key"]:
        print(f"  模型: {LLM_CONFIG['openai_model']}")
        print(f"  Base URL: {LLM_CONFIG['openai_base_url']}")
    print("-" * 60)
    print("API 端点:")
    print(f"  POST  http://localhost:{port}/api/generate-material     (美境物料)")
    print(f"  GET   http://localhost:{port}/api/xhs-topics            (话题推荐数据)")
    print(f"  GET   http://localhost:{port}/api/xhs-rank              (热点榜单数据)")
    print(f"  GET   http://localhost:{port}/api/xhs-profile           (账号概览数据)")
    print(f"  GET   http://localhost:{port}/api/xhs-trend             (互动量趋势数据)")
    print(f"  POST  http://localhost:{port}/api/xhs-topics/refresh    (手动刷新话题)")
    print(f"  POST  http://localhost:{port}/api/xhs-rank/refresh      (手动刷新榜单)")
    print(f"  POST  http://localhost:{port}/api/xhs-profile/refresh   (手动刷新账号数据)")
    print(f"  POST  http://localhost:{port}/api/xhs-trend/refresh     (手动刷新趋势数据)")
    print(f"  POST  http://localhost:{port}/api/llm-topics            (LLM 话题推荐)")
    print(f"  POST  http://localhost:{port}/api/llm-titles            (LLM 标题生成)")
    print(f"  POST  http://localhost:{port}/api/llm-body              (LLM 正文生成)")
    print(f"  GET   http://localhost:{port}/api/llm-test              (LLM 连接测试)")
    print(f"  GET   http://localhost:{port}/api/status                (服务状态)")
    print(f"  GET   http://localhost:{port}/health")
    print("=" * 60)
    print(f"数据文件:")
    print(f"  话题数据: {TOPICS_FILE}")
    print(f"  榜单数据: {RANK_FILE}")
    print(f"  账号数据: {PROFILE_FILE}")
    print(f"  趋势数据: {TREND_FILE}")
    print("=" * 60)
    _schedule_daily_refresh()  # 所有函数定义完成后启动定时任务
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
