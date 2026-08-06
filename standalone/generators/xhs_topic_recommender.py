# -*- coding: utf-8 -*-
"""
小红书每日话题推荐生成器
每日生成 10 条与美团骑手装备相关的小红书话题方向
"""
import json
import os
import random
from datetime import datetime
from typing import List, Dict
from utils.ai_client import get_ai_client
from utils.logger import logger
from utils.paths import PROJECT_ROOT, config_path as get_config_path


class XhsTopicRecommender:
    """小红书话题推荐引擎"""
    
    # 装备品类库
    CATEGORIES = [
        {"name": "头盔", "items": ["智能头盔", "夏盔", "通风头盔", "轻量头盔"], "seasons": ["四季", "夏季"]},
        {"name": "服装", "items": ["防晒衣", "冰丝裤", "透气T恤", "POLO衫", "冬装"], "seasons": ["夏季", "冬季", "四季"]},
        {"name": "餐箱", "items": ["大容量餐箱", "磁吸餐箱", "保温餐箱", "腰靠餐箱"], "seasons": ["四季"]},
        {"name": "防护用品", "items": ["雨衣", "防晒袖", "手套", "护膝", "面罩"], "seasons": ["夏季", "雨季", "冬季"]},
        {"name": "智能装备", "items": ["蓝牙耳机", "手机支架", "导航设备"], "seasons": ["四季"]},
    ]
    
    # 内容角度模板（红线：不硬广、不聊价格，侧重实用/互动/幽默）
    ANGLES = [
        "测评", "对比", "攻略", "清单", "开箱", "穿搭", "搭配",
        "避坑", "新人指南", "日常", "Vlog", "好物分享", "冷知识", "趣测"
    ]
    
    # 小红书热门前缀/后缀模式（红线：不出现价格、不做硬广推销）
    PATTERNS = [
        "{adj}的{item}种草，骑手用了回不去",
        "{item}测评｜{num}款对比，{result}",
        "骑手{item}怎么选？{angle}全攻略",
        "{item}开箱｜{feature}真的好用吗？",
        "{season}骑行{item}清单，{benefit}",
        "{item}穿搭｜{style}风格也能送外卖",
        "新人骑手{item}避坑指南",
        "{item}隐藏功能｜{time}天使用后才发现",
        "{item}搭配公式｜{scene}场景全覆盖",
        "骑手{item}冷知识，{result}"
    ]
    
    ADJ_WORDS = ["实用", "高颜值", "轻量化", "透气", "防水", "防晒", "耐磨", "被低估"]
    FEATURE_WORDS = ["透气", "轻量化", "大容量", "防水", "防晒", "智能", "速干", "隐藏设计"]
    BENEFIT_WORDS = ["告别闷热", "风雨无阻", "安全升级", "效率翻倍", "颜值在线", "少走弯路"]
    STYLE_WORDS = ["潮流", "简约", "运动", "工装", "机能"]
    TIME_WORDS = ["30", "60", "90"]
    SCENE_WORDS = ["日常", "雨天", "高温", "夜间", "冬季", "爆单"]
    RESULT_WORDS = ["第3款真香", "老骑手都懂", "新手别踩坑", "用了回不去"]
    
    def __init__(self):
        self.ai = None
        self.data_dir = os.path.join(PROJECT_ROOT, "web", "static", "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.data_file = os.path.join(self.data_dir, "xhs_recommended_topics.json")
    
    def generate(self, use_ai: bool = True) -> List[Dict]:
        """生成 10 条话题推荐"""
        logger.info("[话题推荐] 开始生成小红书话题...")
        
        # 优先尝试 AI 生成
        if use_ai:
            try:
                ai_topics = self._generate_by_ai()
                if ai_topics and len(ai_topics) >= 10:
                    self._save_topics(ai_topics)
                    logger.info(f"[话题推荐] AI 生成成功: {len(ai_topics)} 条")
                    return ai_topics
            except Exception as e:
                logger.warning(f"[话题推荐] AI 生成失败， fallback 到规则生成: {e}")
        
        # 规则生成兜底
        rule_topics = self._generate_by_rules()
        self._save_topics(rule_topics)
        logger.info(f"[话题推荐] 规则生成完成: {len(rule_topics)} 条")
        return rule_topics
    
    def _generate_by_ai(self) -> List[Dict]:
        """使用 AI 生成话题"""
        if self.ai is None:
            self.ai = get_ai_client()
        
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().month
        season = self._get_season(month)
        
        prompt = f"""你是小红书内容运营专家，专注于美团骑手装备领域。

请为「美团装备研究所」小红书账号生成今日（{today}）的 10 个话题方向。

要求：
1. 每个话题必须与小红书骑手装备相关（头盔、服装、餐箱、防护用品、智能装备等）
2. 结合当前季节（{season}）和骑手实际工作场景
3. 话题要符合小红书平台风格（带 # 标签、有种草属性、有互动性）
4. 每个话题包含：标题（不超过20字）、核心标签（1-2个）、关联装备、预估热度（1-10000）、推荐理由（一句话）
5. 话题类型多样化：测评、穿搭、攻略、清单、对比、开箱、日常、冷知识、趣测等

红线原则（必须遵守）：
- 坚决不聊价格：标题和内容中不要出现任何价格、多少钱、省钱、平价、性价比等字眼
- 不做硬广推销：不用"必买""赶紧入""冲冲冲"等推销语气，不做直接的产品推销
- 风格导向：实用干货（让骑手看了能用上）、互动提问（引发评论区讨论）、幽默有趣（轻松活泼不枯燥）
- 表达方式：用种草/分享/测评/体验的口吻，像骑手老哥们互相交流，而不是商家卖货

当前热门方向参考：
- 夏季防晒、轻量化装备、智能装备、颜值装备、实用技巧、新人避坑、骑手日常

请严格按以下 JSON 数组格式返回，不要包含其他文字：
[
  {{
    "title": "话题标题",
    "tag": "#标签",
    "product": "关联装备",
    "heat": 8500,
    "category": "测评",
    "reason": "推荐理由"
  }}
]
"""
        
        result = self.ai.generate_content(prompt, temperature=0.8, max_tokens=3000)
        
        # 解析 JSON
        try:
            # 提取 JSON 部分
            start_idx = result.find("[")
            end_idx = result.rfind("]")
            if start_idx != -1 and end_idx != -1:
                json_str = result[start_idx:end_idx + 1]
                topics = json.loads(json_str)
                # 补充 ID 和排序
                for i, t in enumerate(topics, 1):
                    t["id"] = i
                    t["heat"] = int(t.get("heat", random.randint(3000, 9500)))
                return topics[:10]
        except Exception as e:
            logger.warning(f"[话题推荐] AI 返回解析失败: {e}")
        
        return []
    
    def _generate_by_rules(self) -> List[Dict]:
        """基于规则生成话题"""
        month = datetime.now().month
        season = self._get_season(month)
        topics = []
        used_combinations = set()
        
        # 按季节筛选合适的品类
        available_cats = []
        for cat in self.CATEGORIES:
            if season in cat["seasons"] or "四季" in cat["seasons"]:
                available_cats.append(cat)
        
        # 确保多样性：每个品类至少出现一次
        cat_idx = 0
        angle_idx = 0
        
        while len(topics) < 10:
            # 轮询品类和角度
            cat = available_cats[cat_idx % len(available_cats)]
            angle = self.ANGLES[angle_idx % len(self.ANGLES)]
            item = random.choice(cat["items"])
            
            # 生成标题（避免重复）
            key = f"{item}_{angle}"
            if key in used_combinations:
                angle_idx += 1
                cat_idx += 1
                continue
            used_combinations.add(key)
            
            title = self._build_title(item, angle, season)
            tag = f"#{item.replace(' ', '')}"
            heat = random.randint(3000, 9800)
            
            topics.append({
                "id": len(topics) + 1,
                "title": title,
                "tag": tag,
                "product": item,
                "heat": heat,
                "category": angle,
                "reason": f"{season}骑手{item}{angle}，实用干货+互动拉满"
            })
            
            cat_idx += 1
            angle_idx += 1
        
        # 按热度排序
        topics.sort(key=lambda x: x["heat"], reverse=True)
        # 重新编号
        for i, t in enumerate(topics, 1):
            t["id"] = i
        
        return topics
    
    def _build_title(self, item: str, angle: str, season: str) -> str:
        """构建话题标题（红线：不硬广、不聊价格，实用/互动/幽默）"""
        if angle == "测评":
            return f"{item}真实测评｜骑手{random.choice(['30', '60'])}天使用体验"
        elif angle == "对比":
            return f"{item}对比｜{random.randint(2, 5)}款热门产品怎么选"
        elif angle == "攻略":
            return f"{season}骑行{item}选购攻略"
        elif angle == "清单":
            return f"{season}骑手{item}清单，{random.choice(self.BENEFIT_WORDS)}"
        elif angle == "开箱":
            return f"{item}开箱｜{random.choice(self.FEATURE_WORDS)}真的好用吗？"
        elif angle == "穿搭":
            return f"{item}穿搭｜{random.choice(self.STYLE_WORDS)}风骑手也能很潮"
        elif angle == "搭配":
            return f"{item}搭配公式｜{random.choice(self.SCENE_WORDS)}场景全覆盖"
        elif angle == "避坑":
            return f"新人骑手{item}避坑，{random.choice(self.RESULT_WORDS)}"
        elif angle == "新人指南":
            return f"新手骑手{item}怎么选？看这篇就够了"
        elif angle == "日常":
            return f"骑手{item}日常｜{random.choice(self.SCENE_WORDS)}送单实录"
        elif angle == "冷知识":
            return f"{item}冷知识｜{random.choice(['老骑手都懂', '新手别踩坑', '用了回不去'])}"
        elif angle == "趣测":
            return f"{item}趣味测试｜{random.choice(['哪款最适合你', '你能猜对几个'])}"
        elif angle == "好物分享":
            return f"{random.choice(self.ADJ_WORDS)}的{item}，骑手用了回不去"
        elif angle == "Vlog":
            return f"骑手{item}Vlog｜{random.choice(self.SCENE_WORDS)}送单真实记录"
        else:
            return f"{item}{angle}｜骑手专属{random.choice(self.FEATURE_WORDS)}版"
    
    def _get_season(self, month: int) -> str:
        """根据月份获取季节"""
        if month in [3, 4, 5]:
            return "春季"
        elif month in [6, 7, 8]:
            return "夏季"
        elif month in [9, 10, 11]:
            return "秋季"
        else:
            return "冬季"
    
    def _save_topics(self, topics: List[Dict]):
        """保存话题到本地 JSON"""
        data = {
            "topics": topics,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "ai" if self.ai else "rule",
            "total": len(topics)
        }
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[话题推荐] 保存数据失败: {e}")
    
    def load_topics(self) -> Dict:
        """加载已保存的话题"""
        if not os.path.exists(self.data_file):
            return {"topics": [], "last_updated": None, "source": "empty", "total": 0}
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[话题推荐] 加载数据失败: {e}")
            return {"topics": [], "last_updated": None, "source": "error", "total": 0}
    
    def get_topics(self, use_ai: bool = True) -> List[Dict]:
        """获取话题列表（优先读取缓存，每日更新）"""
        data = self.load_topics()
        topics = data.get("topics", [])
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
        
        if needs_update or not topics:
            topics = self.generate(use_ai=use_ai)
        
        return topics
