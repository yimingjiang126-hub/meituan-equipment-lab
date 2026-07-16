# 美团装备研究所 · 内容运营中心 - 部署指南

## 概述

本项目包含两部分：
1. **前端页面**（GitHub Pages 永久托管）
2. **后端代理服务**（需要持续运行的服务器）

---

## 一、前端部署（GitHub Pages - 永久免费）

### 1. 创建 GitHub 仓库

1. 打开 https://github.com/new
2. 仓库名称：`meituan-equipment-research`
3. 设置为 **Public**（GitHub Pages 免费版需要公开仓库）
4. 点击 **Create repository**

### 2. 推送代码到 GitHub

在本地项目根目录执行：

```bash
# 初始化 Git 仓库
git init

# 添加所有文件
git add .

# 提交
git commit -m "Initial commit"

# 关联远程仓库（替换为你的用户名）
git remote add origin https://github.com/你的用户名/meituan-equipment-research.git

# 推送
git push -u origin main
```

如果没有安装 Git，先下载安装：https://git-scm.com/downloads

### 3. 启用 GitHub Pages

1. 打开仓库页面 → **Settings** → **Pages**
2. **Source** 选择 **GitHub Actions**
3. 首次推送后，GitHub Actions 会自动部署
4. 等待几分钟后，访问 `https://你的用户名.github.io/meituan-equipment-research/`

---

## 二、后端部署（美境代理服务）

后端需要一台**持续运行的服务器**（VPS / 云服务器 / 内部服务器）。

### 方案 A：Docker 部署（推荐）

**前提**：服务器已安装 Docker 和 Docker Compose

```bash
# 1. 克隆项目到服务器
git clone https://github.com/你的用户名/meituan-equipment-research.git
cd meituan-equipment-research

# 2. 确保 meigen 脚本在服务器上可用
# 需要将 ~/.catpaw/skills/skills-market/meigen-designer/scripts 目录复制到服务器
# 或者修改 docker-compose.yml 中的挂载路径

# 3. 启动服务
cd deploy
docker-compose up -d

# 4. 查看日志
docker-compose logs -f
```

### 方案 B：直接 Python 运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 确保 meigen CLI 已安装并认证
meigen status --json

# 3. 启动代理服务
python standalone/proxy_server.py
```

### 方案 C：美团内部服务器部署

如果美团内部有服务器资源：
1. 联系运维申请一台服务器（建议 2核4G 以上）
2. 将代码部署到服务器
3. 申请一个内部域名（如 `equipment-research.sankuai.com`）
4. 配置 Nginx 反向代理到 8081 端口

---

## 三、配置前端指向后端

部署完成后，需要告诉前端页面后端地址在哪里。

### 方法 1：浏览器控制台设置（临时，适合测试）

1. 打开部署后的前端页面
2. 按 F12 打开开发者工具 → Console
3. 输入：
   ```javascript
   localStorage.setItem('API_BASE_URL', 'https://你的后端地址.com');
   ```
4. 刷新页面

### 方法 2：修改代码（永久生效）

编辑 `standalone/index.html`，找到：
```javascript
var API_BASE_URL = localStorage.getItem('API_BASE_URL') || 'http://localhost:8081';
```

改为：
```javascript
var API_BASE_URL = localStorage.getItem('API_BASE_URL') || 'https://你的后端地址.com';
```

然后提交并推送代码。

---

## 四、完整部署架构

```
用户浏览器
    ↓
GitHub Pages (https://你的用户名.github.io/meituan-equipment-research/)
    ↓ API 请求 (CORS)
你的后端服务器 (https://你的后端地址.com)
    ↓
美境 AI 服务 (meituan.net)
    ↓
生成图片 URL
    ↓
用户看到图片
```

---

## 五、常见问题

### Q1：为什么前端能打开但生成功能用不了？
**A**：后端代理服务没有启动或没有正确配置。检查：
1. 后端服务器是否运行 `proxy_server.py`
2. 前端 `API_BASE_URL` 是否指向正确的后端地址
3. 后端服务器是否安装了 `meigen` CLI 并已完成认证

### Q2：GitHub Pages 链接打不开？
**A**：
1. 确保仓库是 **Public**
2. 在 Settings → Pages 中确认 Source 是 **GitHub Actions**
3. 首次部署可能需要 1-2 分钟，请等待

### Q3：meigen 认证在服务器上怎么做？
**A**：在服务器上运行 `meigen login` 或 `meigen status --json` 确认 token 有效。如果服务器没有浏览器，可以先在本机登录，然后把 token 文件复制到服务器。

### Q4：没有服务器怎么办？
**A**：
1. 短期使用：用 `ngrok` 把本地 8081 暴露到公网（免费但 URL 会变化）
2. 长期使用：申请一台云服务器（阿里云/腾讯云/华为云，约 50-100元/月）
3. 或者联系公司 IT 申请内部服务器资源

---

## 六、安全注意事项

1. **不要** 将 meigen 的认证 token 提交到 GitHub 仓库
2. 后端服务器建议配置 HTTPS（使用 Let's Encrypt 免费证书）
3. 如果后端部署在公网，建议添加访问控制（IP 白名单或 Basic Auth）

---

## 七、维护

- 更新前端内容：修改 `standalone/index.html` 后 `git push`，GitHub Actions 自动部署
- 更新后端代码：修改代码后重新部署 Docker 容器或重启 Python 进程
- 监控后端状态：访问 `https://你的后端地址.com/health` 查看健康状态
