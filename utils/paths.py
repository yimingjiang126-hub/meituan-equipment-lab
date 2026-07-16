# -*- coding: utf-8 -*-
"""统一路径工具，解决 Flask 从 web/app.py 运行时路径错误"""
import os

# 项目根目录（social-media-marketing-auto 文件夹）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path(filename: str) -> str:
    """获取 config 目录下文件的绝对路径"""
    return os.path.join(PROJECT_ROOT, "config", filename)


def data_path(filename: str) -> str:
    """获取 data 目录下文件的绝对路径"""
    return os.path.join(PROJECT_ROOT, "data", filename)


def outputs_path(filename: str = "") -> str:
    """获取 outputs_daily 目录下文件的绝对路径"""
    return os.path.join(PROJECT_ROOT, "outputs_daily", filename)
