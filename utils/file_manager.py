# -*- coding: utf-8 -*-
"""文件归档管理"""
import os
import shutil
from datetime import datetime
from pathlib import Path


class FileManager:
    """管理每日输出文件的创建与归档"""
    
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(__file__), "..", "outputs_daily")
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
    
    def get_daily_dir(self, date_str: str = None) -> str:
        """获取指定日期的输出目录"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y%m%d")
        daily_dir = os.path.join(self.base_dir, date_str)
        os.makedirs(daily_dir, exist_ok=True)
        return daily_dir
    
    def get_filename(self, date_str: str, prefix: str, ext: str) -> str:
        """生成标准文件名: 20250707_热点内容营销_抖音.xlsx"""
        daily_dir = self.get_daily_dir(date_str)
        filename = f"{date_str}_{prefix}{ext}"
        return os.path.join(daily_dir, filename)
    
    def archive_hot_data(self, date_str: str, data: dict, platform: str):
        """归档原始热点数据到 data/hot_data/"""
        import json
        hot_dir = os.path.join(os.path.dirname(__file__), "..", "data", "hot_data")
        os.makedirs(hot_dir, exist_ok=True)
        filepath = os.path.join(hot_dir, f"{date_str}_{platform}_hot.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath


# 单例
_fm = None

def get_file_manager() -> FileManager:
    global _fm
    if _fm is None:
        _fm = FileManager()
    return _fm
