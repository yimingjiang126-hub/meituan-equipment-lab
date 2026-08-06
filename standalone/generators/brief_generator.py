# -*- coding: utf-8 -*-
"""
达人 Brief 生成器
为 KOL/KOC 合作生成标准化的传播 brief
"""
from typing import Dict, List
from utils.ai_client import get_ai_client
from utils.logger import logger


class BriefGenerator:
    """生成达人传播 Brief"""
    
    def __init__(self):
        self.ai = get_ai_client()
    
    def generate_brief(self, 
                       topic: Dict,
                       platform: str,
                       kol_tier: str = "中腰部",  # 头部/中腰部/素人
                       content_type: str = "种草",  # 种草/测评/剧情/口播
                       deliverables: List[str] = None) -> Dict:
        """
        生成达人传播 Brief
        
        Args:
            topic: 选题信息
            platform: 平台（小红书/抖音）
            kol_tier: 达人层级
            content_type: 内容类型
            deliverables: 交付物清单
        """
        if deliverables is None:
            deliverables = ["1篇图文笔记" if platform == "xiaohongshu" else "1条短视频"]
        
        hot_title = topic["hot_topic"]["title"]
        event = topic.get("marketing_event", {})
        event_name = event["name"] if event else ""
        
        prompt = f"""你是一位品牌方 PR，请为以下合作生成一份达人传播 Brief:

【项目背景】
- 品牌: 美团装备（骑手装备商城）
- 营销节点: {event_name}
- 借势热点: {hot_title}
- 合作平台: {"小红书" if platform == "xiaohongshu" else "抖音"}
- 达人层级: {kol_tier}
- 内容类型: {content_type}

【Brief 要求】
1. 品牌介绍（50字）
2. 产品信息（主推产品 + 核心卖点）
3. 内容方向（结合热点，给达人明确的创作方向）
4. 必现元素（logo、产品、话题标签等硬性要求）
5. 发布要求（发布时间、话题标签、@账号等）
6. 注意事项（避雷、敏感词、竞品回避）
7. 数据要求（预期阅读/互动量，或不做硬性要求）

请用中文，专业、清晰、对达人友好。
"""
        try:
            content = self.ai.generate_content(prompt)
            return {
                "platform": platform,
                "kol_tier": kol_tier,
                "content_type": content_type,
                "deliverables": deliverables,
                "brief": content,
                "topic": hot_title
            }
        except Exception as e:
            logger.error(f"[Brief生成] 失败: {e}")
            return None
    
    def generate_batch_briefs(self, topic: Dict, platforms: List[str] = None) -> List[Dict]:
        """为同一热点生成多平台/多层级 brief"""
        if platforms is None:
            platforms = ["xiaohongshu", "douyin"]
        
        briefs = []
        for platform in platforms:
            # 小红书：图文种草 + 中腰部达人
            if platform == "xiaohongshu":
                briefs.append(self.generate_brief(topic, platform, "中腰部", "种草"))
            # 抖音：短视频 + 口播/测评
            elif platform == "douyin":
                briefs.append(self.generate_brief(topic, platform, "中腰部", "口播"))
        
        return [b for b in briefs if b is not None]


# 单例
_brief_gen = None

def get_brief_generator() -> BriefGenerator:
    global _brief_gen
    if _brief_gen is None:
        _brief_gen = BriefGenerator()
    return _brief_gen
