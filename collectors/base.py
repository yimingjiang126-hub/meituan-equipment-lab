# -*- coding: utf-8 -*-
"""
热点采集器基类
所有平台采集器继承此类
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict
from utils.logger import logger


class HotTopicItem:
    """热点条目数据结构"""
    def __init__(self, 
                 rank: int,
                 title: str,
                 heat: str = "",
                 url: str = "",
                 platform: str = "",
                 category: str = "",
                 raw_data: dict = None):
        self.rank = rank
        self.title = title
        self.heat = heat
        self.url = url
        self.platform = platform
        self.category = category
        self.raw_data = raw_data or {}
        self.crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "title": self.title,
            "heat": self.heat,
            "url": self.url,
            "platform": self.platform,
            "category": self.category,
            "crawl_time": self.crawl_time,
            "raw_data": self.raw_data
        }


class BaseCollector(ABC):
    """采集器基类"""
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.logger = logger
    
    @abstractmethod
    def collect(self) -> List[HotTopicItem]:
        """执行采集，返回热点列表"""
        pass
    
    def filter_by_keywords(self, items: List[HotTopicItem], keywords: List[str]) -> List[HotTopicItem]:
        """根据关键词过滤热点"""
        if not keywords:
            return items
        filtered = []
        for item in items:
            title_lower = item.title.lower()
            if any(kw.lower() in title_lower for kw in keywords):
                filtered.append(item)
        return filtered
    
    def save_raw(self, items: List[HotTopicItem], date_str: str):
        """保存原始数据到 data/hot_data/"""
        from utils.file_manager import get_file_manager
        fm = get_file_manager()
        data = {
            "platform": self.platform_name,
            "date": date_str,
            "count": len(items),
            "items": [item.to_dict() for item in items]
        }
        filepath = fm.archive_hot_data(date_str, data, self.platform_name)
        self.logger.info(f"[{self.platform_name}] 原始数据已保存: {filepath}")
        return filepath
