# -*- coding: utf-8 -*-
"""
小红书账号趋势数据采集器
支持第三方数据平台 API（新榜/千瓜/蝉妈妈/灰豚）
"""
import json
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests
from utils.logger import logger
from utils.paths import PROJECT_ROOT


class XhsTrendData:
    """趋势数据点"""
    def __init__(self, timestamp: str, heat: int, likes: int = 0, 
                 collects: int = 0, comments: int = 0, follows: int = 0,
                 notes: int = 0, raw: dict = None):
        self.timestamp = timestamp  # ISO 格式或 HH:MM
        self.heat = heat
        self.likes = likes
        self.collects = collects
        self.comments = comments
        self.follows = follows
        self.notes = notes
        self.raw = raw or {}
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "heat": self.heat,
            "likes": self.likes,
            "collects": self.collects,
            "comments": self.comments,
            "follows": self.follows,
            "notes": self.notes,
            "raw": self.raw
        }


class XiaohongshuTrendCollector:
    """小红书趋势数据采集器"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.platform = self.config.get("platform", "custom")
        self.base_url = self.config.get("base_url", "").rstrip("/")
        self.api_key = self.config.get("api_key", "")
        self.api_secret = self.config.get("api_secret", "")
        self.account_id = self.config.get("account_id", "672e12dc000000001c01aef0")
        self.granularity = self.config.get("granularity", "hourly")
        self.lookback_days = self.config.get("lookback_days", 1)
        self.logger = logger
        
        # 数据存储路径
        self.data_dir = os.path.join(PROJECT_ROOT, "web", "static", "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.data_file = os.path.join(self.data_dir, "xhs_trend.json")
    
    def collect(self) -> Dict:
        """采集趋势数据，返回完整数据集"""
        self.logger.info("[XHS趋势] 开始采集账号趋势数据...")
        
        # 如果配置了第三方 API，优先调用
        if self.base_url and self.api_key:
            data = self._fetch_from_api()
            if data and data.get("hourly_data"):
                self._save_data(data)
                self.logger.info(f"[XHS趋势] 第三方 API 采集成功: {len(data['hourly_data'])} 条")
                return data
        
        # 如果没有 API 或采集失败，尝试加载已有数据
        existing = self._load_existing()
        if existing and existing.get("hourly_data"):
            self.logger.info("[XHS趋势] 使用已缓存的历史数据")
            return existing
        
        # 兜底：生成模拟数据（基于账号画像的合理推测）
        self.logger.warning("[XHS趋势] 未配置 API，生成模拟趋势数据")
        data = self._generate_fallback_data()
        self._save_data(data)
        return data
    
    def _fetch_from_api(self) -> Optional[Dict]:
        """从第三方 API 获取趋势数据"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(days=self.lookback_days)
            
            # 通用 API 请求参数（不同平台需按文档调整）
            params = {
                "account_id": self.account_id,
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "granularity": self.granularity
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            if self.api_secret:
                headers["X-Secret"] = self.api_secret
            
            # 根据平台选择 endpoint（示例，需按实际文档调整）
            endpoint = self._get_endpoint()
            url = f"{self.base_url}{endpoint}"
            
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            
            # 解析不同平台的返回格式（这里用通用映射）
            return self._parse_api_response(result)
            
        except Exception as e:
            self.logger.error(f"[XHS趋势] API 请求失败: {e}")
            return None
    
    def _get_endpoint(self) -> str:
        """根据平台获取 API endpoint"""
        endpoints = {
            "newrank": "/api/xhs/account/trend",
            "qiangua": "/api/v1/account/trend",
            "chanmama": "/api/xhs/account/analytics",
            "huitun": "/api/account/trend",
            "custom": "/api/trend"
        }
        return endpoints.get(self.platform, "/api/trend")
    
    def _parse_api_response(self, result: dict) -> Optional[Dict]:
        """解析第三方 API 响应为统一格式"""
        try:
            # 通用映射：假设 API 返回 data.list 包含时间序列
            data_list = result.get("data", {}).get("list", []) or result.get("data", [])
            if not data_list:
                return None
            
            hourly_data = []
            for item in data_list:
                # 尝试多种字段名映射（不同平台字段名不同）
                ts = item.get("time") or item.get("timestamp") or item.get("date")
                heat = item.get("heat") or item.get("score") or item.get("index") or item.get("interaction_count", 0)
                
                hourly_data.append({
                    "timestamp": str(ts),
                    "heat": int(heat) if heat else 0,
                    "likes": int(item.get("likes", 0) or item.get("like_count", 0)),
                    "collects": int(item.get("collects", 0) or item.get("collect_count", 0)),
                    "comments": int(item.get("comments", 0) or item.get("comment_count", 0)),
                    "follows": int(item.get("follows", 0) or item.get("follow_count", 0)),
                    "notes": int(item.get("notes", 0) or item.get("note_count", 0)),
                    "raw": item
                })
            
            return {
                "account_id": self.account_id,
                "platform": self.platform,
                "granularity": self.granularity,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "hourly_data": hourly_data,
                "source": "api"
            }
        except Exception as e:
            self.logger.error(f"[XHS趋势] API 响应解析失败: {e}")
            return None
    
    def _generate_fallback_data(self) -> Dict:
        """生成模拟趋势数据（基于真实账号画像的合理推测）"""
        now = datetime.now()
        # 12 个时间点：覆盖近 24 小时，每2小时一个点
        base_values = [3200, 2800, 2100, 3800, 5200, 6100, 5800, 6500, 7200, 6800, 7856, 5400]
        data_points = []
        
        for i, base in enumerate(base_values):
            hour = now - timedelta(hours=(11 - i) * 2)
            data_points.append({
                "timestamp": hour.strftime("%H:%M"),
                "heat": base,
                "likes": int(base * 0.15),
                "collects": int(base * 0.08),
                "comments": int(base * 0.03),
                "follows": int(base * 0.01),
                "notes": 0,
                "raw": {}
            })
        
        return {
            "account_id": self.account_id,
            "platform": "fallback",
            "granularity": "hourly",
            "last_updated": now.strftime("%Y-%m-%d %H:%M:%S"),
            "hourly_data": data_points,
            "source": "fallback",
            "note": "未配置第三方 API，当前为模拟数据。请在 settings.yaml 中配置 xhs_trend_api 参数以接入真实数据。"
        }
    
    def _save_data(self, data: Dict):
        """保存数据到本地 JSON"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"[XHS趋势] 数据已保存: {self.data_file}")
        except Exception as e:
            self.logger.error(f"[XHS趋势] 保存数据失败: {e}")
    
    def _load_existing(self) -> Optional[Dict]:
        """加载已存在的本地数据"""
        if not os.path.exists(self.data_file):
            return None
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"[XHS趋势] 加载已有数据失败: {e}")
            return None
    
    def get_chart_data(self) -> Dict:
        """获取前端图表所需格式"""
        data = self.collect()
        hourly = data.get("hourly_data", [])
        
        if not hourly:
            return {"hours": [], "values": [], "peak": 0, "source": "empty"}
        
        hours = [h["timestamp"] for h in hourly]
        values = [h["heat"] for h in hourly]
        peak = max(values) if values else 0
        
        return {
            "hours": hours,
            "values": values,
            "peak": peak,
            "source": data.get("source", "unknown"),
            "last_updated": data.get("last_updated", ""),
            "note": data.get("note", "")
        }
