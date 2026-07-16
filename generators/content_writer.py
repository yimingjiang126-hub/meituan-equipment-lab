# -*- coding: utf-8 -*-
"""
内容文案生成器
生成小红书种草文案、抖音文案、站内活动文案
"""
import yaml
from typing import List, Dict
from utils.ai_client import get_ai_client
from utils.logger import logger
from utils.paths import config_path as get_config_path


class ContentWriter:
    """AI 内容文案生成"""
    
    def __init__(self):
        self.ai = get_ai_client()
        with open(get_config_path("brand_keywords.yaml"), "r", encoding="utf-8") as f:
            self.brand = yaml.safe_load(f)
    
    def generate_xiaohongshu_note(self, topic: Dict, product: str = None) -> Dict:
        """生成小红书图文笔记"""
        hot_title = topic["hot_topic"]["title"]
        event = topic.get("marketing_event", {})
        event_name = event["name"] if event else ""
        
        system_prompt = """你是一位小红书头部种草文案写手，擅长写真实、有温度、能引发共鸣的种草笔记。
写作风格：
- 标题吸引人，用emoji增加点击率
- 内容真实，有具体使用场景和感受
- 结尾自然引导互动（评论/收藏）
- 标签精准（5-8个）"""
        
        prompt = f"""请为以下热点写一篇小红书种草笔记:

热点主题: {hot_title}
营销节点: {event_name}
品牌: 美团装备（骑手装备商城）
产品: {product or '骑手装备（头盔/服装/餐箱等）'}

要求:
1. 标题要吸睛，结合热点 + 产品
2. 正文 300-500 字，真实感强
3. 包含使用场景（如骑手送餐、夏日防晒等）
4. 结尾引导互动
5. 给出 5-8 个推荐标签

请用中文输出，格式:
【标题】
...

【正文】
...

【推荐标签】
#... #...
"""
        content = self.ai.generate_content(prompt, system_prompt=system_prompt)
        return {
            "platform": "xiaohongshu",
            "format": "图文笔记",
            "content": content,
            "topic": hot_title
        }
    
    def generate_douyin_copy(self, topic: Dict, product: str = None) -> Dict:
        """生成抖音短视频文案"""
        hot_title = topic["hot_topic"]["title"]
        event = topic.get("marketing_event", {})
        event_name = event["name"] if event else ""
        
        system_prompt = """你是一位抖音短视频脚本策划，擅长写节奏快、钩子强、有反转的短视频脚本。
风格要求：
- 前3秒必须有强钩子（冲突/好奇/痛点）
- 中间有反转或价值输出
- 结尾引导关注/评论/购买
- 口语化，适合视频口播"""
        
        prompt = f"""请为以下热点写一个抖音短视频脚本:

热点主题: {hot_title}
营销节点: {event_name}
品牌: 美团装备（骑手装备商城）
产品: {product or '骑手装备'}

要求:
1. 视频时长: 15-30 秒
2. 结构: 钩子(前3秒) → 内容(中间) → 结尾(引导)
3. 给出具体的画面描述和口播文案
4. 给出推荐 BGM 风格和标题

请用中文输出，格式:
【视频标题】
...

【口播文案】
...

【画面描述】
...

【BGM建议】
...
"""
        content = self.ai.generate_content(prompt, system_prompt=system_prompt)
        return {
            "platform": "douyin",
            "format": "短视频脚本",
            "content": content,
            "topic": hot_title
        }
    
    def generate_ecommerce_activity(self, topic: Dict, event: Dict) -> Dict:
        """生成电商站内活动文案"""
        hot_title = topic["hot_topic"]["title"]
        event_name = event["name"] if event else ""
        
        system_prompt = """你是一位电商运营专家，擅长写转化率高、促销感强的站内活动文案。
风格：简洁有力，卖点突出，紧迫感强。"""
        
        prompt = f"""请为以下热点设计一个电商站内促销活动:

热点主题: {hot_title}
营销节点: {event_name}
品牌: 美团装备商城

要求输出:
1. 活动名称（10字以内）
2. 活动 slogan（一句话）
3. 主推产品推荐（2-3个）
4. 促销机制（满减/折扣/赠品等）
5. 首页 Banner 文案（主标题 + 副标题）
6. 商品详情页卖点文案（3-5个 bullet points）
7. Push/短信文案（30字以内）

请用中文输出。
"""
        content = self.ai.generate_content(prompt, system_prompt=system_prompt)
        return {
            "platform": "ecommerce",
            "format": "站内活动方案",
            "content": content,
            "topic": hot_title
        }
    
    def generate_daily_report(self, topics: List[Dict], date_str: str) -> str:
        """生成每日热点营销简报（Markdown 格式）"""
        hot_list = "\n".join([f"{i+1}. {t['hot_topic']['title']} (匹配度: {t['match_score']})" 
                              for i, t in enumerate(topics[:5])])
        
        prompt = f"""请根据以下今日热点，生成一份社交媒体内容营销日报简报:

日期: {date_str}
今日 Top 5 关联热点:
{hot_list}

要求:
1. 标题: 今日热点营销简报（含日期）
2. 概述: 今日热点总体趋势（2-3句话）
3. 重点选题: 选择最匹配品牌的1-2个热点，给出具体营销建议
4. 风险提示: 如果有敏感/负面热点，给出避雷建议
5. 明日预告: 根据营销日历，预告明天可能的借势方向

请用 Markdown 格式输出，专业简洁。
"""
        return self.ai.generate_content(prompt)


# 单例
_writer = None

def get_content_writer() -> ContentWriter:
    global _writer
    if _writer is None:
        _writer = ContentWriter()
    return _writer
