# -*- coding: utf-8 -*-
"""
美境 AI 设计师 - 独立代理服务器
为 standalone/index.html 提供 /api/generate-material 接口

使用方法：
    python proxy_server.py

默认监听端口：8081
"""
import os
import sys
import uuid
import tempfile

# 把项目根目录加入路径
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from generators.meigen_material import (
    generate_material,
    start_generate_task,
    get_task_status,
    MEIGEN_SCRIPT_DIR,
    GENERATE_PY,
    LOCAL_IMAGE_DIR
)

app = Flask(__name__)
CORS(app)  # 允许跨域，前端在8080端口访问8081


@app.route("/api/generate-material", methods=["POST"])
def api_generate_material():
    """提交美境 AI 物料生成任务"""
    try:
        # 调试：打印接收到的表单数据
        print(f"[DEBUG] 收到 generate-material 请求")
        print(f"[DEBUG] form keys: {list(request.form.keys())}")
        print(f"[DEBUG] files keys: {list(request.files.keys())}")
        for k, v in request.form.items():
            print(f"[DEBUG] form[{k}] = {v[:50] if v else 'empty'}...")

        # 检查美境脚本是否存在
        if not os.path.exists(GENERATE_PY):
            return jsonify({
                "status": "failed",
                "error": f"美境服务未配置，请检查 meigen-cli 安装。脚本路径：{GENERATE_PY}"
            }), 200

        prompt = request.form.get("prompt", "")
        if not prompt:
            return jsonify({"error": "图片生成描述不能为空"}), 400

        # 其他参数
        width = request.form.get("width", "1080")
        height = request.form.get("height", "1920")
        title = request.form.get("title", "")
        subtitle = request.form.get("subtitle", "")
        style = request.form.get("style", "国漫风")

        # 生成任务ID
        task_id = "mat_" + uuid.uuid4().hex[:8]

        # 保存上传的图片（支持多张）
        image_paths = []
        if "image" in request.files:
            files = request.files.getlist("image")
            for file in files:
                if file.filename:
                    ext = os.path.splitext(file.filename)[1] or ".png"
                    temp_path = os.path.join(
                        tempfile.gettempdir(),
                        f"upload_{uuid.uuid4().hex}{ext}"
                    )
                    file.save(temp_path)
                    image_paths.append(temp_path)

        # 启动生成任务（后台线程）
        start_generate_task(task_id, width, height, title, subtitle, style, image_paths, prompt)

        return jsonify({
            "status": "started",
            "task_id": task_id,
            "msg": "美境AI物料生成任务已提交，正在生成中..."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-material/status/<task_id>")
def api_generate_material_status(task_id: str):
    """查询物料生成任务状态"""
    try:
        status = get_task_status(task_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 500


@app.route("/health")
def health_check():
    """健康检查"""
    meigen_ready = os.path.exists(GENERATE_PY)
    return jsonify({
        "status": "ok",
        "meigen_ready": meigen_ready,
        "meigen_script_dir": MEIGEN_SCRIPT_DIR
    })


@app.route("/static/images/generated/<path:filename>")
def serve_generated_image(filename):
    """提供生成的图片文件访问"""
    file_path = os.path.join(LOCAL_IMAGE_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "图片不存在"}), 404
    return send_file(file_path)


if __name__ == "__main__":
    print("=" * 60)
    print("美境 AI 设计师 - 独立代理服务器")
    print("=" * 60)
    print(f"美境脚本目录: {MEIGEN_SCRIPT_DIR}")
    print(f"美境脚本就绪: {os.path.exists(GENERATE_PY)}")
    print("=" * 60)
    port = int(os.environ.get("PORT", 8081))
    print(f"服务启动中，端口: {port}")
    print(f"健康检查: http://localhost:{port}/health")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
    print("-" * 60)
    print("API 端点:")
    print("  POST  http://localhost:8081/api/generate-material")
    print("  GET   http://localhost:8081/api/generate-material/status/<task_id>")
    print("  GET   http://localhost:8081/health")
    print("-" * 60)
    print("启动服务中...")
    print("=" * 60)
    app.run(host="0.0.0.0", port=8081, debug=False, use_reloader=False)
