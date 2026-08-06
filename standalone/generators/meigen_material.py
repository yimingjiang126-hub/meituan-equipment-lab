# -*- coding: utf-8 -*-
"""
美境 AI 设计师 - 物料生成器
封装 meigen-designer skill 的 generate.py + poll.py 流程
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Optional, Dict
from urllib.request import urlopen
from utils.logger import logger

# meigen-designer scripts 目录
MEIGEN_SCRIPT_DIR = os.path.join(
    os.path.expanduser("~"), ".catpaw", "skills", "skills-market", "meigen-designer", "scripts"
)
GENERATE_PY = os.path.join(MEIGEN_SCRIPT_DIR, "generate.py")
POLL_PY = os.path.join(MEIGEN_SCRIPT_DIR, "poll.py")

# 嵌入版 Python 解释器路径（确保使用与 proxy_server 相同的 Python）
# 兼容 standalone 和 deploy 两种目录结构
_here = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = os.path.join(os.path.dirname(_here), "python", "python.exe")
if not os.path.exists(PYTHON_EXE):
    # 尝试 standalone/python 路径
    PYTHON_EXE = os.path.join(os.path.dirname(os.path.dirname(_here)), "standalone", "python", "python.exe")
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable  # fallback 到当前解释器

# 本地图片保存目录
LOCAL_IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "static", "images", "generated")
os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)

# 任务存储（内存中，单进程场景够用）
task_store: Dict[str, dict] = {}


def _parse_json_lines(stdout: str) -> list:
    """解析 JSON Lines 输出"""
    if not stdout:
        return []
    results = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return results


def _upload_image_to_s3(local_path: str) -> str:
    """调用 upload-to-s3.py 上传本地图片到 S3，返回远程 URL"""
    upload_script = os.path.join(MEIGEN_SCRIPT_DIR, "upload-to-s3.py")
    if not os.path.exists(upload_script):
        logger.error(f"[美境] upload-to-s3.py 不存在: {upload_script}")
        return ""
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = MEIGEN_SCRIPT_DIR + (os.pathsep + existing_pypath if existing_pypath else "")
    node_bin_dir = r"M:\social-media-marketing-auto\standalone\node-v20.11.0-win-x64"
    existing_path = env.get("PATH", "")
    env["PATH"] = node_bin_dir + os.pathsep + existing_path
    
    try:
        result = subprocess.run(
            [PYTHON_EXE, upload_script, local_path],
            cwd=MEIGEN_SCRIPT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120
        )
    except subprocess.TimeoutExpired:
        logger.error(f"[美境] 上传图片超时: {local_path}")
        return ""
    except Exception as e:
        logger.error(f"[美境] 上传图片异常: {e}")
        return ""
    
    # upload-to-s3.py 成功时 stdout 最后一行是 URL
    stdout = result.stdout.strip()
    if stdout.startswith("http"):
        logger.info(f"[美境] 图片上传成功: {stdout[:80]}...")
        return stdout
    
    # 尝试从 stdout 中找到 URL
    for line in reversed(stdout.split("\n")):
        line = line.strip()
        if line.startswith("http"):
            logger.info(f"[美境] 图片上传成功: {line[:80]}...")
            return line
    
    logger.error(f"[美境] 上传图片失败，stdout={stdout[:200]}, stderr={result.stderr[:200]}")
    return ""


def _run_generate(prompt: str, image_paths: list = None) -> dict:
    """
    运行 generate.py 提交任务
    返回: {success: bool, session_id: int, assistant_message_id: int, error: str}
    """
    image_paths = image_paths or []
    image_urls = []
    
    # 1. 上传本地图片到 S3，获取远程 URL
    for local_path in image_paths:
        if local_path and os.path.exists(local_path):
            url = _upload_image_to_s3(local_path)
            if url:
                image_urls.append(url)
    
    # 2. 组装 prompt：插入图片占位符 + 末尾追加引用行
    assembled_prompt = prompt
    file_args = []
    for idx, url in enumerate(image_urls, start=1):
        assembled_prompt += f" [@image:#{idx}]"
        file_args.extend(["--file", url])
    if image_urls:
        assembled_prompt += "\n"
        for idx, url in enumerate(image_urls, start=1):
            assembled_prompt += f"For Image #{idx}: URL: {url}\n"
    
    # 3. 构造命令：generate.py <prompt> [--file <url>]...
    cmd = [PYTHON_EXE, GENERATE_PY, assembled_prompt]
    cmd.extend(file_args)
    
    logger.info(f"[美境] 提交任务: prompt={assembled_prompt[:80]}..., files={len(file_args)//2}")
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # 将 meigen script 目录加入 PYTHONPATH，确保 common 模块可被找到
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = MEIGEN_SCRIPT_DIR + (os.pathsep + existing_pypath if existing_pypath else "")
    # 将 Node.js 目录加入 PATH，确保 meigen 命令可被找到
    node_bin_dir = r"M:\social-media-marketing-auto\standalone\node-v20.11.0-win-x64"
    existing_path = env.get("PATH", "")
    env["PATH"] = node_bin_dir + os.pathsep + existing_path
    
    try:
        result = subprocess.run(
            cmd,
            cwd=MEIGEN_SCRIPT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "提交任务超时（60秒）"}
    except Exception as e:
        return {"success": False, "error": f"提交任务异常: {str(e)}"}
    
    logger.info(f"[美境] generate.py stdout: {result.stdout[:500]}")
    if result.stderr:
        logger.info(f"[美境] generate.py stderr: {result.stderr[:500]}")
    
    lines = _parse_json_lines(result.stdout)
    
    # 查找 submitted 终态
    for line in lines:
        if line.get("_action") == "submitted":
            return {
                "success": True,
                "session_id": line.get("sessionId"),
                "user_message_id": line.get("userMessageId"),
                "assistant_message_id": line.get("assistantMessageId")
            }
        if line.get("_action") == "failed":
            msg = line.get("msg", "提交失败")
            if "meigen status" in msg or "token" in msg.lower() or "认证" in msg:
                return {"success": False, "error": "美境未登录，请运行 meigen login 认证后重试"}
            return {"success": False, "error": msg}
    
    # 如果没有找到 submitted，检查是否有失败信息
    for line in lines:
        if line.get("status") == "failed":
            msg = line.get("msg", "提交失败")
            if "meigen status" in msg or "token" in msg.lower() or "认证" in msg:
                return {"success": False, "error": "美境未登录，请运行 meigen login 认证后重试"}
            return {"success": False, "error": msg}
    
    return {"success": False, "error": "未能获取提交结果，请检查 meigen 配置"}


def _run_poll(session_id: int, assistant_message_id: int) -> dict:
    """
    运行 poll.py 轮询结果
    返回: {success: bool, url: str, error: str}
    """
    cmd = [PYTHON_EXE, POLL_PY, str(session_id), str(assistant_message_id)]
    
    logger.info(f"[美境] 开始轮询: session_id={session_id}, assistant_message_id={assistant_message_id}")
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # 将 meigen script 目录加入 PYTHONPATH
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = MEIGEN_SCRIPT_DIR + (os.pathsep + existing_pypath if existing_pypath else "")
    # 将 Node.js 目录加入 PATH，确保 meigen 命令可被找到
    node_bin_dir = r"M:\social-media-marketing-auto\standalone\node-v20.11.0-win-x64"
    existing_path = env.get("PATH", "")
    env["PATH"] = node_bin_dir + os.pathsep + existing_path
    
    try:
        result = subprocess.run(
            cmd,
            cwd=MEIGEN_SCRIPT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=600  # 10分钟超时
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "轮询超时（10分钟）"}
    except Exception as e:
        return {"success": False, "error": f"轮询异常: {str(e)}"}
    
    logger.info(f"[美境] poll.py stdout length: {len(result.stdout)}")
    logger.info(f"[美境] poll.py stdout (first 2000): {result.stdout[:2000]}")
    if result.stderr:
        logger.info(f"[美境] poll.py stderr (first 1000): {result.stderr[:1000]}")
    
    lines = _parse_json_lines(result.stdout)
    logger.info(f"[美境] 解析到 {len(lines)} 行 JSON")
    for idx, line in enumerate(lines):
        logger.info(f"[美境] line[{idx}] type={line.get('type')} action={line.get('_action')} url={line.get('url', 'N/A')[:60]}")
    
    # 查找图片结果（优先 show_images）
    for line in lines:
        if line.get("_action") == "show_images":
            url = line.get("url")
            if url:
                return {"success": True, "url": url}
            content = line.get("content", "")
            if isinstance(content, list) and len(content) > 0:
                first = content[0]
                if isinstance(first, dict):
                    url = first.get("url") or first.get("imageUrl")
                    if url:
                        return {"success": True, "url": url}
            if isinstance(content, str):
                import re
                urls = re.findall(r'https?://[^\s<>"{}|\\^`[\]]+', content)
                if urls:
                    return {"success": True, "url": urls[0]}
    
    # 兜底：检查所有 line 中的 url 字段
    for line in lines:
        if line.get("type") in ("Image", "ImageList"):
            url = line.get("url")
            if url:
                return {"success": True, "url": url}
            content = line.get("content", [])
            if isinstance(content, list) and len(content) > 0:
                first = content[0]
                if isinstance(first, dict) and first.get("url"):
                    return {"success": True, "url": first.get("url")}
    
    # 再次兜底：如果 poll.py 成功退出（exit code 0）且 message_status 为 DONE，
    # 在所有 line 的字符串中查找图片 URL
    if result.returncode == 0:
        for line in lines:
            if line.get("type") == "message_status" and line.get("_action") in ("notify_done", "done"):
                # 在所有 lines 中搜索任何 URL
                for l in lines:
                    # 检查 line 中的任何字段
                    for key in ["url", "imageUrl", "content"]:
                        val = l.get(key)
                        if isinstance(val, str) and val.startswith("http"):
                            return {"success": True, "url": val}
                        if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                            for item in val:
                                for k in ["url", "imageUrl"]:
                                    if item.get(k) and str(item.get(k)).startswith("http"):
                                        return {"success": True, "url": item.get(k)}
    
    # 检查用户询问
    for line in lines:
        if line.get("_action") == "ask_user":
            return {"success": False, "error": "美境需要确认生成参数，请直接前往 https://aidesign.meituan.com/ 生成"}
    
    # 检查失败
    for line in lines:
        if line.get("_action") in ("notify_failed", "failed"):
            return {"success": False, "error": line.get("msg", "生成失败")}
        if line.get("_action") == "notify_timeout":
            return {"success": False, "error": "生成超时，请稍后重试"}
    
    return {"success": False, "error": "未能获取生成结果，请前往 https://aidesign.meituan.com/ 查看"}


def _download_image(url: str) -> str:
    """下载图片到本地，返回本地相对路径"""
    try:
        ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
        filename = f"gen_{uuid.uuid4().hex[:8]}{ext}"
        local_path = os.path.join(LOCAL_IMAGE_DIR, filename)
        
        with urlopen(url, timeout=30) as resp:
            with open(local_path, "wb") as f:
                f.write(resp.read())
        
        return f"http://localhost:8081/static/images/generated/{filename}"
    except Exception as e:
        logger.error(f"[美境] 下载图片失败: {e}")
        return url  # 回退到原 URL


def generate_material(
    width: str,
    height: str,
    title: str,
    subtitle: str,
    style: str,
    image_paths: list = None,
    prompt: Optional[str] = None
) -> dict:
    """
    生成物料图片
    返回: {success: bool, url: str, error: str}
    """
    # 检查脚本是否存在
    if not os.path.exists(GENERATE_PY):
        logger.error(f"[美境] generate.py 不存在: {GENERATE_PY}")
        return {"success": False, "error": "美境服务未配置，请检查 meigen-cli 安装"}
    
    # 使用传入的 prompt，如果没有则自动构造
    if not prompt:
        prompt = f"生成一张{style}风格的图片"
        if width and height:
            prompt += f"，尺寸为{width}x{height}"
        if title:
            prompt += f"，主标题：{title}"
        if subtitle:
            prompt += f"，副标题：{subtitle}"
        prompt += "，小红书海报风格"
    
    # 第一步：提交任务
    submit_result = _run_generate(prompt, image_paths)
    if not submit_result["success"]:
        return submit_result
    
    # 第二步：轮询结果
    poll_result = _run_poll(
        submit_result["session_id"],
        submit_result["assistant_message_id"]
    )
    
    return poll_result


def start_generate_task(
    task_id: str,
    width: str,
    height: str,
    title: str,
    subtitle: str,
    style: str,
    image_paths: list = None,
    prompt: Optional[str] = None
) -> None:
    """在后台线程中启动生成任务"""
    task_store[task_id] = {"status": "running", "url": None, "error": None}
    
    def _do_generate():
        try:
            result = generate_material(width, height, title, subtitle, style, image_paths, prompt)
            if result["success"]:
                # 下载图片到本地
                local_url = _download_image(result.get("url", ""))
                task_store[task_id] = {"status": "done", "url": local_url, "error": None}
            else:
                task_store[task_id] = {"status": "failed", "url": None, "error": result.get("error", "未知错误")}
        except Exception as e:
            logger.error(f"[美境] 生成任务异常: {e}")
            task_store[task_id] = {"status": "failed", "url": None, "error": f"生成异常: {str(e)}"}
    
    thread = threading.Thread(target=_do_generate, daemon=False)
    thread.start()


def get_task_status(task_id: str) -> dict:
    """获取任务状态"""
    return task_store.get(task_id, {"status": "not_found", "url": None, "error": "任务不存在"})
