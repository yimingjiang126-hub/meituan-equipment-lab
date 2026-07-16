# -*- coding: utf-8 -*-
"""
抖音热点采集器
采用多策略：优先公开 API → 备选网页解析 → 最后兜底模拟
"""
import json
import re
import time
from typing import List
from collectors.base import BaseCollector, HotTopicItem
from utils.logger import logger


class DouyinHotCollector(BaseCollector):
    """抖音热点榜采集"""
    
    def __init__(self):
        super().__init__("douyin")
    
    def collect(self) -> List[HotTopicItem]:
        """
        采集抖音热点
        策略1: 调用公开 API（抖音热点有开放接口）
        策略2: 网页解析（被反爬时降级）
        策略3: 兜底返回空（避免中断）
        """
        logger.info("[抖音] 开始采集热点...")
        
        # 策略1: 尝试公开 API
        items = self._collect_from_api()
        if items:
            logger.info(f"[抖音] API 采集成功: {len(items)} 条")
            return items
        
        # 策略2: 网页解析（备用）
        items = self._collect_from_web()
        if items:
            logger.info(f"[抖音] 网页采集成功: {len(items)} 条")
            return items
        
        # 兜底
        logger.warning("[抖音] 采集失败，返回空列表")
        return []
    
    def _collect_from_api(self) -> List[HotTopicItem]:
        """
        通过抖音公开 API 获取热点榜
        抖音热点 API: https://www.douyin.com/aweme/v1/web/hot/search/list/
        """
        import requests
        
        try:
            url = "https://www.douyin.com/aweme/v1/web/hot/search/list/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/hot"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            items = []
            if "data" in data and "word_list" in data["data"]:
                for idx, word in enumerate(data["data"]["word_list"][:50], 1):
                    item = HotTopicItem(
                        rank=idx,
                        title=word.get("word", ""),
                        heat=str(word.get("hot_value", "")),
                        url=f"https://www.douyin.com/hot/{word.get('sentence_id', '')}",
                        platform="douyin",
                        category=word.get("label", ""),
                        raw_data=word
                    )
                    items.append(item)
            return items
        except Exception as e:
            logger.warning(f"[抖音] API 采集失败: {e}")
            return []
    
    def _collect_from_web(self) -> List[HotTopicItem]:
        """
        通过网页 HTML 解析获取热点（备用方案）
        实际运行时可通过 CatDesk browser 获取渲染后的页面
        """
        try:
            import requests
            url = "https://www.douyin.com/hot"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            html = resp.text
            
            # 尝试从页面 script 中提取 JSON 数据
            pattern = r'<script id="RENDER_DATA" type="application/json">(.*?)</script>'
            match = re.search(pattern, html)
            if match:
                json_str = match.group(1)
                # 可能是 URL encoded
                from urllib.parse import unquote
                json_str = unquote(json_str)
                data = json.loads(json_str)
                # 解析数据...
                # 这里简化处理，实际根据数据结构提取
                return []
            return []
        except Exception as e:
            logger.warning(f"[抖音] 网页采集失败: {e}")
            return []
    
    def collect_via_catdesk(self) -> List[HotTopicItem]:
        """
        通过 CatDesk 浏览器自动化采集
        适用于 API 被封时使用
        """
        logger.info("[抖音] 使用 CatDesk Browser 采集...")
        try:
            import subprocess
            import json as json_mod
            
            # 使用 CatDesk browser-action 打开抖音热点页并提取数据
            cmd = [
                r"%USERPROFILE%\.catdesk\bin\catdesk.cmd",
                "browser-action",
                json_mod.dumps({
                    "action": "navigate",
                    "url": "https://www.douyin.com/hot"
                })
            ]
            # 实际执行需要更复杂的交互，这里提供接口框架
            logger.info("[抖音] CatDesk 采集接口已预留，需手动执行浏览器自动化")
            return []
        except Exception as e:
            logger.warning(f"[抖音] CatDesk 采集失败: {e}")
            return []
