# -*- coding: utf-8 -*-
"""
小红书热搜采集器
"""
import json
import time
from typing import List
from collectors.base import BaseCollector, HotTopicItem
from utils.logger import logger


class XiaohongshuHotCollector(BaseCollector):
    """小红书热搜采集"""
    
    def __init__(self):
        super().__init__("xiaohongshu")
    
    def collect(self) -> List[HotTopicItem]:
        """采集小红书热搜"""
        logger.info("[小红书] 开始采集热搜...")
        
        items = self._collect_from_api()
        if items:
            logger.info(f"[小红书] 采集成功: {len(items)} 条")
            return items
        
        logger.warning("[小红书] 采集失败，返回空列表")
        return []
    
    def _collect_from_api(self) -> List[HotTopicItem]:
        """
        小红书热搜 API
        注意：小红书反爬严格，这里用通用搜索接口模拟
        """
        try:
            import requests
            
            # 小红书搜索建议接口（可获取热门搜索词）
            url = "https://www.xiaohongshu.com/api/sns/web/v1/search/recommend"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.xiaohongshu.com/"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            items = []
            if "data" in data and "queries" in data["data"]:
                for idx, query in enumerate(data["data"]["queries"][:50], 1):
                    item = HotTopicItem(
                        rank=idx,
                        title=query.get("query", ""),
                        heat=str(query.get("score", "")),
                        url=f"https://www.xiaohongshu.com/search_result?keyword={query.get('query', '')}",
                        platform="xiaohongshu",
                        category="热搜",
                        raw_data=query
                    )
                    items.append(item)
            return items
        except Exception as e:
            logger.warning(f"[小红书] API 采集失败: {e}")
            return []
    
    def _collect_from_web(self) -> List[HotTopicItem]:
        """备用：网页采集"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            url = "https://www.xiaohongshu.com/explore"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 小红书网页结构经常变化，这里做兜底
            return []
        except Exception as e:
            logger.warning(f"[小红书] 网页采集失败: {e}")
            return []
