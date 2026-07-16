# -*- coding: utf-8 -*-
"""
AI 选题匹配引擎
将热点 × 品牌产品 × 营销日历 → 生成关联选题
"""
import yaml
from datetime import datetime
from typing import List, Dict, Tuple
from collectors.base import HotTopicItem
from utils.ai_client import get_ai_client
from utils.logger import logger
from utils.paths import config_path as get_config_path


class TopicSelector:
    """热点选题匹配器"""
    
    def __init__(self):
        self.ai = get_ai_client()
        self._load_brand_keywords()
        self._load_marketing_calendar()
    
    def _load_brand_keywords(self):
        with open(get_config_path("brand_keywords.yaml"), "r", encoding="utf-8") as f:
            self.brand = yaml.safe_load(f)
    
    def _load_marketing_calendar(self):
        with open(get_config_path("marketing_calendar.yaml"), "r", encoding="utf-8") as f:
            self.calendar = yaml.safe_load(f)
    
    def get_current_marketing_event(self, date: datetime = None) -> Dict:
        """获取当前正在进行的营销节点"""
        if date is None:
            date = datetime.now()
        
        current_year = str(date.year)
        events = self.calendar.get("calendar", {}).get(current_year, [])
        
        for event in events:
            period = event.get("period", "")
            if "~" in period:
                start_str, end_str = period.split("~")
                start = datetime.strptime(start_str.strip(), "%Y-%m-%d")
                end = datetime.strptime(end_str.strip(), "%Y-%m-%d")
                if start <= date <= end:
                    return event
        return None
    
    def calculate_match_score(self, hot: HotTopicItem) -> Tuple[int, str]:
        """
        计算热点与品牌的匹配度
        返回: (score, reason)
        """
        title = hot.title.lower()
        score = 0
        reasons = []
        
        # 高关联关键词
        high_kw = self.brand["hot_match_keywords"]["high"]
        for kw in high_kw:
            if kw.lower() in title:
                score += 30
                reasons.append(f"高关联关键词: {kw}")
        
        # 中关联关键词
        medium_kw = self.brand["hot_match_keywords"]["medium"]
        for kw in medium_kw:
            if kw.lower() in title:
                score += 15
                reasons.append(f"中关联关键词: {kw}")
        
        # 低关联关键词
        low_kw = self.brand["hot_match_keywords"]["low"]
        for kw in low_kw:
            if kw.lower() in title:
                score += 5
                reasons.append(f"低关联关键词: {kw}")
        
        # 产品关键词匹配
        for cat in self.brand["products"]:
            for item in cat["items"]:
                if item.lower() in title:
                    score += 20
                    reasons.append(f"产品匹配: {item}")
            for kw in cat["keywords"]:
                if kw.lower() in title:
                    score += 10
                    reasons.append(f"品类关键词: {kw}")
        
        return min(score, 100), "; ".join(reasons) if reasons else "暂无强关联"
    
    def select_topics(self, hot_items: List[HotTopicItem], top_n: int = 10) -> List[Dict]:
        """
        从热点列表中筛选出最匹配的选题
        """
        logger.info(f"[选题] 开始匹配 {len(hot_items)} 条热点...")
        
        scored_items = []
        for item in hot_items:
            score, reason = self.calculate_match_score(item)
            scored_items.append({
                "hot": item,
                "score": score,
                "reason": reason
            })
        
        # 按匹配度排序，取 Top N
        scored_items.sort(key=lambda x: x["score"], reverse=True)
        selected = scored_items[:top_n]
        
        # 获取当前营销节点
        event = self.get_current_marketing_event()
        
        # 为每个选题生成关联策略
        results = []
        for item in selected:
            strategy = self._generate_strategy(item["hot"], item["score"], item["reason"], event)
            results.append(strategy)
        
        logger.info(f"[选题] 完成，选出 {len(results)} 个关联选题")
        return results
    
    def _generate_strategy(self, hot: HotTopicItem, score: int, reason: str, event: Dict) -> Dict:
        """为单个热点生成营销关联策略"""
        strategy = {
            "hot_topic": hot.to_dict(),
            "match_score": score,
            "match_reason": reason,
            "marketing_event": event,
            "suggested_products": [],
            "suggested_themes": [],
            "content_angles": []
        }
        
        # 匹配产品
        title = hot.title.lower()
        for cat in self.brand["products"]:
            for item_name in cat["items"]:
                if item_name.lower() in title or any(kw.lower() in title for kw in cat["keywords"]):
                    strategy["suggested_products"].append({
                        "name": item_name,
                        "category": cat["category"]
                    })
        
        # 匹配内容主题
        for theme in self.brand["content_themes"]:
            strategy["suggested_themes"].append(theme)
        
        # 生成内容切入点（AI 辅助）
        if score >= 30:
            strategy["content_angles"] = self._ai_generate_angles(hot, event)
        else:
            strategy["content_angles"] = ["通用借势: 蹭热点 + 产品露出"]
        
        return strategy
    
    def _ai_generate_angles(self, hot: HotTopicItem, event: Dict) -> List[str]:
        """用 AI 生成内容切入点"""
        event_name = event["name"] if event else "日常营销"
        event_themes = event["themes"] if event else ["品牌推广"]
        
        prompt = f"""你是一位资深社交媒体内容营销专家，擅长为品牌借势热点。

当前热点: {hot.title}
当前营销节点: {event_name}（主题: {', '.join(event_themes)}）
品牌: 美团装备（骑手装备商城，产品包括头盔、服装、餐箱、防护用品等）

请针对这个热点，为品牌生成 3-5 个具体的内容切入点/创意角度。
每个角度要求:
1. 具体可执行，不要空洞
2. 结合热点和品牌产品
3. 说明适合哪个平台（抖音/小红书/站内）
4. 说明预期效果

请用中文回答，格式如下:
1. 【角度名称】具体内容...
2. 【角度名称】具体内容...
"""
        try:
            result = self.ai.generate_content(prompt)
            # 解析为列表
            angles = [line.strip() for line in result.split("\n") if line.strip() and line.strip()[0].isdigit()]
            return angles if angles else ["AI 生成角度失败，使用默认策略"]
        except Exception as e:
            logger.warning(f"[AI 选题] 生成失败: {e}")
            return ["通用策略: 结合热点做产品推荐"]


# 单例
_topic_selector = None

def get_topic_selector() -> TopicSelector:
    global _topic_selector
    if _topic_selector is None:
        _topic_selector = TopicSelector()
    return _topic_selector
