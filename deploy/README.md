# 美团装备研究所 · 内容运营中心 - 部署指南

## 快速部署（推荐：Render + GitHub Pages）

这个方案完全免费，不需要维护服务器，部署一次后得到一个永久链接。

### 架构

```
用户浏览器
    ↓ HTTPS
GitHub Pages (前端静态页面)
    ↓ API 请求 (CORS)
Render (后端代理服务)
    ↓ 美境 CLI
美境 AI 生成图片
    ↓ 返回图片 URL
用户看到图片
```

---

## 第一步：创建 GitHub 仓库

### 1.1 注册 GitHub（如果还没有账号）

打开 https://github.com/signup，用邮箱注册。

### 1.2 创建新仓库

1. 打开 https://github.com/new
2. 仓库名称：`meituan-equipment-research`（可以改）
3. 选择 **Public**（免费版需要公开仓库）
4. 不要勾选 "Add a README file"（我们已经有了）
5. 点击 **Create repository**

### 1.3 推送本地代码到 GitHub

在你的电脑上打开 PowerShell，执行以下命令：

```powershell
# 进入项目目录
cd M:\social-media-marketing-auto

# 关联远程仓库（替换为你的用户名）
git remote add origin https://github.com/你的用户名/meituan-equipment-research.git

# 推送代码
git branch -M main
git push -u origin main
```

输入你的 GitHub 用户名和密码（或 token）。

---

## 第二步：部署前端到 GitHub Pages（永久免费）

### 2.1 启用 GitHub Pages

1. 打开你的仓库页面 → **Settings** → **Pages**（左侧菜单）
2. **Source** 选择 **GitHub Actions**
3. 等待 1-2 分钟，GitHub Actions 会自动部署
4. 访问 `https://你的用户名.github.io/meituan-equipment-research/`

### 2.2 验证前端部署

打开上面的链接，确认页面能正常显示。

---

## 第三步：部署后端到 Render（永久免费，但会休眠）

### 3.1 注册 Render

1. 打开 https://render.com
2. 用 GitHub 账号登录（推荐，方便导入仓库）

### 3.2 创建 Web Service

1. 登录后点击 **New +** → **Web Service**
2. 选择你的 GitHub 仓库 `meituan-equipment-research`
3. 配置：
   - **Name**: `meituan-equipment-proxy`（可以改）
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python standalone/proxy_server.py`
4. 选择 **Free** 计划（免费，但会休眠）
5. 点击 **Create Web Service**

### 3.3 等待部署完成

Render 会自动构建和部署，大约需要 2-3 分钟。

部署完成后，你会得到一个链接，如：
`https://meituan-equipment-proxy.onrender.com`

### 3.4 验证后端部署

访问 `https://你的-render-链接/health`，确认返回：
```json
{"status": "ok", "meigen_ready": true}
```

---

## 第四步：配置前端指向后端

### 4.1 在浏览器中设置后端地址

1. 打开 GitHub Pages 链接：`https://你的用户名.github.io/meituan-equipment-research/`
2. 按 F12 打开开发者工具 → Console
3. 输入以下命令（替换为你的 Render 链接）：

```javascript
localStorage.setItem('API_BASE_URL', 'https://你的-render-链接');
```

4. 刷新页面

### 4.2 永久修改（可选）

如果你不想每次都在控制台设置，可以修改 `standalone/index.html`：

找到这一行：
```javascript
var API_BASE_URL = localStorage.getItem('API_BASE_URL') || 'http://localhost:8081';
```

改为：
```javascript
var API_BASE_URL = localStorage.getItem('API_BASE_URL') || 'https://你的-render-链接';
```

然后提交并推送：
```bash
git add standalone/index.html
git commit -m "更新后端地址"
git push
```

GitHub Actions 会自动重新部署前端。

---

## 第五步：测试完整功能

1. 打开 GitHub Pages 链接
2. 在 **物料素材制作** 区域输入描述，点击 **生成素材**
3. 等待 30-90 秒，确认图片能正常生成和展示

---

## 常见问题

### Q1：Render 链接打不开？
**A**：Render 免费版会在 15 分钟无活动后休眠。首次访问需要 30-60 秒唤醒。等待一下即可。

### Q2：GitHub Pages 链接打不开？
**A**：
1. 确保仓库是 **Public**
2. 在 Settings → Pages 中确认 Source 是 **GitHub Actions**
3. 首次部署可能需要 1-2 分钟，请等待

### Q3：生成图片时报错？
**A**：
1. 检查 Render 后端是否正常运行（访问 `/health`）
2. 检查前端 `API_BASE_URL` 是否指向正确的 Render 地址
3. 检查 Render 日志（Render 控制台 → Logs）

### Q4：美境认证在 Render 上怎么做？
**A**：在 Render 的 Environment 中设置环境变量：
1. 打开 Render 控制台 → 你的服务 → Environment
2. 添加环境变量（如果美境需要的话）
3. 或者直接在 Render 的 Shell 中运行 `meigen login`

### Q5：不想用 Render，有其他选择吗？
**A**：
- **Vercel**：支持纯前端部署，但 Python 后端有限制
- **Railway**：类似 Render，支持完整 Python
- **Fly.io**：支持 Docker，需要配置
- **自托管**：在自己的服务器上运行

---

## 安全注意事项

1. **不要** 将美境的认证 token 提交到 GitHub 仓库
2. Render 后端建议配置 HTTPS（Render 默认已启用）
3. 如果后端部署在公网，建议添加访问控制

---

## 维护

- 更新前端内容：修改 `standalone/index.html` 后 `git push`，GitHub Actions 自动部署
- 更新后端代码：修改代码后 `git push`，Render 自动重新部署
- 监控后端状态：访问 `https://你的-render-链接/health`
