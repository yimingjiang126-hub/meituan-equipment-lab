# -*- coding: utf-8 -*-
"""
小红书每日热点榜单生成器
每日生成 10 条前一天的小红书热梗话题、热点方向和热点BGM
"""
import json
import os
import random
from datetime import datetime, timedelta
from typing import List, Dict
from utils.logger import logger
from utils.paths import PROJECT_ROOT
from collectors.xiaohongshu_hot import XiaohongshuHotCollector


class XhsHotRankGenerator:
    """小红书热点榜单生成器"""
    
    # 骑手/装备领域相关的热梗库（用于 fallback）
    HOT_MEMES = [
        "骑手版\"APT\"魔性变装挑战",
        "\"您的骑手正在...\"系列梗",
        "送外卖最崩溃的10个瞬间",
        "骑手搞笑对话实录",
        "\"外卖到了\"名场面合集",
        "骑手与顾客的相爱相杀",
        "跑单时的神级操作",
        "骑手版\"我姓石\"喊麦",
        "送餐路上的显眼包",
        "骑手专属表情包大赛"
    ]
    
    HOT_TOPICS = [
        "沉浸式送单vlog怎么拍",
        "骑手夏日装备红黑榜",
        "骑手防晒装备真实测评",
        "骑手跑单Citywalk路线",
        "骑手手机支架选购攻略",
        "新人骑手避坑指南",
        "夜间跑单照明装备",
        "骑手雨衣真实测评",
        "夏季送单清凉神器",
        "骑手头盔选购全攻略"
    ]
    
    HOT_BGMS = [
        "送单专用BGM推荐合集",
        "跑单节奏感BGM推荐",
        "骑手专属解压神曲盘点",
        "骑手解压歌单分享",
        "适合跑单听的电子音乐",
        "骑手通勤必听歌单",
        "夏日骑行清凉歌单",
        "夜间跑单提神BGM",
        "骑手提神醒脑歌单",
        "雨天送单氛围感歌单"
    ]
    
    def __init__(self):
        self.data_dir = os.path.join(PROJECT_ROOT, "web", "static", "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.data_file = os.path.join(self.data_dir, "xhs_hot_rank.json")
    
    def generate(self) -> List[Dict]:
        """生成前一天的 Top10 热点榜单"""
        logger.info("[热点榜单] 开始生成昨日 Top10 热点榜单...")
        
        # 尝试采集真实小红书热搜
        collector = XiaohongshuHotCollector()
        real_hot = collector.collect()
        
        # 构建榜单：3热梗 + 4热点 + 3BGM
        rank_list = []
        used_titles = set()
        
        # 如果有真实数据，尝试匹配和筛选
        if real_hot and len(real_hot) > 0:
            logger.info(f"[热点榜单] 采集到 {len(real_hot)} 条真实热搜，进行筛选分类...")
            rank_list = self._categorize_from_real(real_hot[:30])
        
        # 补充缺失的条目
        rank_list = self._fill_missing(rank_list)
        
        # 按热度排序
        rank_list.sort(key=lambda x: self._heat_to_num(x["heat"]), reverse=True)
        
        # 重新编号
        for i, item in enumerate(rank_list, 1):
            item["rank"] = i
        
        # 保存
        self._save(rank_list)
        logger.info(f"[热点榜单] 生成完成: {len(rank_list)} 条")
        return rank_list
    
    def _categorize_from_real(self, real_hot: List) -> List[Dict]:
        """从真实热搜中筛选分类骑手相关的热点"""
        rank_list = []
        used_titles = set()
        
        # 骑手相关关键词
        rider_keywords = ["骑手", "外卖", "送餐", "跑单", "美团", "饿了么", "配送", "骑手装备", "头盔", "餐箱", "防晒", "雨衣"]
        
        for item in real_hot:
            title = item.title if hasattr(item, 'title') else item.get('title', '')
            if not title or title in used_titles:
                continue
            
            # 检查是否与骑手相关
            is_rider_related = any(kw in title for kw in rider_keywords)
            if not is_rider_related:
                continue
            
            # 根据内容分类
            tag = self._classify_tag(title)
            heat_str = self._format_heat(item.heat if hasattr(item, 'heat') else item.get('heat', ''))
            
            rank_list.append({
                "rank": 0,
                "title": title,
                "heat": heat_str,
                "tag": tag,
                "url": f"https://www.xiaohongshu.com/search_result?keyword={title}",
                "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            })
            used_titles.add(title)
            
            if len(rank_list) >= 10:
                break
        
        return rank_list
    
    def _classify_tag(self, title: str) -> str:
        """根据标题内容分类标签"""
        meme_keywords = ["梗", "搞笑", "魔性", "变装", "挑战", "名场面", "表情包", "崩溃", "瞬间", "对话"]
        bgm_keywords = ["BGM", "歌单", "音乐", "歌曲", "神曲", "听歌", "歌", "曲"]
        
        if any(kw in title for kw in bgm_keywords):
            return "BGM"
        elif any(kw in title for kw in meme_keywords):
            return "热梗"
        else:
            return "热点"
    
    def _fill_missing(self, rank_list: List[Dict]) -> List[Dict]:
        """补充缺失的条目，确保有3热梗+4热点+3BGM"""
        used_titles = {item["title"] for item in rank_list}
        target_counts = {"热梗": 3, "热点": 4, "BGM": 3}
        
        # 统计当前各类型数量
        current_counts = {"热梗": 0, "热点": 0, "BGM": 0}
        for item in rank_list:
            if item["tag"] in current_counts:
                current_counts[item["tag"]] += 1
        
        # 补充热梗
        while current_counts["热梗"] < target_counts["热梗"]:
            title = random.choice(self.HOT_MEMES)
            if title not in used_titles:
                rank_list.append(self._build_item(title, "热梗"))
                used_titles.add(title)
                current_counts["热梗"] += 1
        
        # 补充热点
        while current_counts["热点"] < target_counts["热点"]:
            title = random.choice(self.HOT_TOPICS)
            if title not in used_titles:
                rank_list.append(self._build_item(title, "热点"))
                used_titles.add(title)
                current_counts["热点"] += 1
        
        # 补充BGM
        while current_counts["BGM"] < target_counts["BGM"]:
            title = random.choice(self.HOT_BGMS)
            if title not in used_titles:
                rank_list.append(self._build_item(title, "BGM"))
                used_titles.add(title)
                current_counts["BGM"] += 1
        
        # 如果超过10条，取前10条
        return rank_list[:10]
    
    def _build_item(self, title: str, tag: str) -> Dict:
        """构建单条榜单数据"""
        heat_map = {"热梗": (8.0, 15.0), "热点": (5.0, 10.0), "BGM": (3.0, 8.0)}
        min_h, max_h = heat_map.get(tag, (3.0, 8.0))
        heat_val = round(random.uniform(min_h, max_h), 1)
        
        return {
            "rank": 0,
            "title": title,
            "heat": f"{heat_val}w",
            "tag": tag,
            "url": f"https://www.xiaohongshu.com/search_result?keyword={title}",
            "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        }
    
    def _format_heat(self, raw_heat) -> str:
        """格式化热度值"""
        try:
            if isinstance(raw_heat, str):
                # 尝试提取数字
                import re
                num_match = re.search(r'(\d+\.?\d*)', raw_heat)
                if num_match:
                    val = float(num_match.group(1))
                    if val >= 10000:
                        return f"{val/10000:.1f}w"
                    return f"{val:.1f}w"
            elif isinstance(raw_heat, (int, float)):
                if raw_heat >= 10000:
                    return f"{raw_heat/10000:.1f}w"
                return f"{raw_heat:.1f}w"
        except:
            pass
        return f"{random.uniform(3.0, 12.0):.1f}w"
    
    def _heat_to_num(self, heat_str: str) -> float:
        """将热度字符串转换为数字用于排序"""
        try:
            val = heat_str.replace("w", "").replace("W", "").replace(",", "")
            return float(val)
        except:
            return 0.0
    
    def _save(self, rank_list: List[Dict]):
        """保存榜单到本地 JSON"""
        data = {
            "items": rank_list,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "total": len(rank_list)
        }
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[热点榜单] 保存数据失败: {e}")
    
    def load(self) -> Dict:
        """加载已保存的榜单"""
        if not os.path.exists(self.data_file):
            return {"items": [], "last_updated": None, "date": None, "total": 0}
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[热点榜单] 加载数据失败: {e}")
            return {"items": [], "last_updated": None, "date": None, "total": 0}
    
    def get_rank(self) -> List[Dict]:
        """获取榜单（优先读取缓存，每日10点后更新）"""
        data = self.load()
        items = data.get("items", [])
        last_updated = data.get("last_updated")
        
        # 检查是否需要更新（每日10点后）
        today_10am = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        needs_update = False
        
        if not last_updated:
            needs_update = True
        else:
            try:
                last_dt = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
                if last_dt < today_10am and datetime.now() >= today_10am:
                    needs_update = True
            except:
                needs_update = True
        
        if needs_update or not items:
            items = self.generate()
        
        return items
