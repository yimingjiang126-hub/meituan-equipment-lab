# -*- coding: utf-8 -*-
"""
社交媒体内容营销自动化产品 - 主入口

用法:
    python main.py                    # 执行今日完整流程
    python main.py --date 2025-07-15  # 指定日期执行
    python main.py --mode collect      # 仅采集热点
    python main.py --mode generate     # 仅生成内容（基于已采集数据）
"""
import argparse
import sys
import os
from datetime import datetime

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import logger
from utils.file_manager import get_file_manager
from collectors.douyin_hot import DouyinHotCollector
from collectors.xiaohongshu_hot import XiaohongshuHotCollector
from collectors.ecommerce_trend import EcommerceTrendCollector
from generators.topic_selector import get_topic_selector
from generators.content_writer import get_content_writer
from generators.brief_generator import get_brief_generator
from outputs.excel_reporter import get_excel_reporter
from outputs.word_reporter import get_word_reporter


def parse_args():
    parser = argparse.ArgumentParser(description="社交媒体内容营销自动化")
    parser.add_argument("--date", type=str, default="today", help="执行日期 (YYYY-MM-DD 或 today)")
    parser.add_argument("--mode", type=str, default="full", choices=["full", "collect", "generate"], help="执行模式")
    return parser.parse_args()


def get_date_str(args) -> str:
    if args.date == "today":
        return datetime.now().strftime("%Y%m%d")
    return args.date.replace("-", "")


def run_collect(date_str: str) -> dict:
    """执行热点采集"""
    logger.info("=" * 50)
    logger.info(f"开始热点采集 - 日期: {date_str}")
    logger.info("=" * 50)
    
    all_hot_data = {}
    
    # 1. 抖音热点
    douyin = DouyinHotCollector()
    douyin_items = douyin.collect()
    all_hot_data["douyin"] = douyin_items
    douyin.save_raw(douyin_items, date_str)
    logger.info(f"[抖音] 采集到 {len(douyin_items)} 条热点")
    
    # 2. 小红书热搜
    xhs = XiaohongshuHotCollector()
    xhs_items = xhs.collect()
    all_hot_data["xiaohongshu"] = xhs_items
    xhs.save_raw(xhs_items, date_str)
    logger.info(f"[小红书] 采集到 {len(xhs_items)} 条热点")
    
    # 3. 电商趋势
    ec = EcommerceTrendCollector()
    ec_items = ec.collect()
    all_hot_data["ecommerce"] = ec_items
    ec.save_raw(ec_items, date_str)
    logger.info(f"[电商] 采集到 {len(ec_items)} 条趋势")
    
    # 合并所有热点
    all_items = douyin_items + xhs_items + ec_items
    logger.info(f"[总计] 采集到 {len(all_items)} 条热点/趋势")
    
    return all_hot_data, all_items


def run_generate(all_items: list, date_str: str):
    """执行内容生成"""
    logger.info("=" * 50)
    logger.info(f"开始内容生成 - 日期: {date_str}")
    logger.info("=" * 50)
    
    # 1. 选题匹配
    selector = get_topic_selector()
    selected_topics = selector.select_topics(all_items, top_n=10)
    
    if not selected_topics:
        logger.warning("[生成] 无匹配选题，跳过生成")
        return
    
    # 2. 内容生成
    writer = get_content_writer()
    contents = []
    
    for topic in selected_topics[:3]:  # 前3个选题生成详细内容
        # 小红书笔记
        xhs_content = writer.generate_xiaohongshu_note(topic)
        if xhs_content:
            contents.append(xhs_content)
        
        # 抖音脚本
        dy_content = writer.generate_douyin_copy(topic)
        if dy_content:
            contents.append(dy_content)
        
        # 电商活动
        event = topic.get("marketing_event")
        ec_content = writer.generate_ecommerce_activity(topic, event)
        if ec_content:
            contents.append(ec_content)
    
    # 3. 达人 Brief
    brief_gen = get_brief_generator()
    briefs = []
    for topic in selected_topics[:2]:
        topic_briefs = brief_gen.generate_batch_briefs(topic)
        briefs.extend(topic_briefs)
    
    # 4. 日报简报
    report_md = writer.generate_daily_report(selected_topics, date_str)
    
    # 5. 输出 Excel 排期表
    excel_reporter = get_excel_reporter()
    excel_path = excel_reporter.create_daily_schedule(selected_topics, contents, date_str)
    
    # 6. 输出 Word 活动策划案
    word_reporter = get_word_reporter()
    word_path = word_reporter.create_activity_plan(selected_topics, contents, briefs, date_str)
    
    # 7. 保存 Markdown 简报
    fm = get_file_manager()
    daily_dir = fm.get_daily_dir(date_str)
    md_path = os.path.join(daily_dir, f"{date_str}_热点营销简报.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    
    logger.info("=" * 50)
    logger.info(f"内容生成完成 - 日期: {date_str}")
    logger.info(f"输出文件:")
    logger.info(f"  - Excel: {excel_path}")
    logger.info(f"  - Word: {word_path}")
    logger.info(f"  - Markdown: {md_path}")
    logger.info("=" * 50)
    
    return {
        "excel": excel_path,
        "word": word_path,
        "markdown": md_path,
        "topics": selected_topics,
        "contents": contents,
        "briefs": briefs
    }


def main():
    args = parse_args()
    date_str = get_date_str(args)
    
    logger.info(f"\n{'='*60}")
    logger.info(f"社交媒体内容营销自动化 - 启动")
    logger.info(f"模式: {args.mode} | 日期: {date_str}")
    logger.info(f"{'='*60}\n")
    
    try:
        if args.mode == "collect":
            _, all_items = run_collect(date_str)
            logger.info(f"[完成] 仅采集模式，共 {len(all_items)} 条热点已归档")
            
        elif args.mode == "generate":
            # 读取已采集的数据
            import json
            hot_dir = os.path.join("data", "hot_data")
            all_items = []
            for platform in ["douyin", "xiaohongshu", "ecommerce"]:
                filepath = os.path.join(hot_dir, f"{date_str}_{platform}_hot.json")
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        from collectors.base import HotTopicItem
                        for item in data.get("items", []):
                            all_items.append(HotTopicItem(
                                rank=item["rank"],
                                title=item["title"],
                                heat=item["heat"],
                                url=item["url"],
                                platform=item["platform"],
                                category=item["category"],
                                raw_data=item.get("raw_data", {})
                            ))
            if not all_items:
                logger.error(f"[错误] 未找到 {date_str} 的采集数据，请先执行 --mode collect")
                return 1
            run_generate(all_items, date_str)
            
        else:  # full
            _, all_items = run_collect(date_str)
            run_generate(all_items, date_str)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"执行完成 ✅")
        logger.info(f"{'='*60}\n")
        return 0
        
    except Exception as e:
        logger.exception(f"[错误] 执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
