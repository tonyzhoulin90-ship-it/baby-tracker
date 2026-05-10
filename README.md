# 宝宝成长记录应用 (MengxiaApp)

轻量级 Flask 单页应用 (SPA)，用于记录和追踪宝宝日常活动：喂奶、辅食、排便、睡眠、照片上传、里程碑、成长数据等。

---

## 一、系统架构

### 1.1 总体架构

本项目采用 **前后端分离** 架构：

```
┌─────────────────────────────────────────────────────────┐
│                      客户端 (浏览器)                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │  单页应用 (SPA) - templates/index.html           │   │
│  │  • 纯 HTML/CSS/JavaScript (无前端框架)          │   │
│  │  • iOS 风格 UI 设计                               │   │
│  │  • 移动端优先的响应式布局                          │   │
│  └─────────────────────────────────────────────────┘   │
│                          ↑↓ HTTP                        │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│                      服务端 (Flask)                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │  app.py - Flask 应用主入口                        │   │
│  │  • RESTful API 端点                              │   │
│  │  • HTTP Basic Auth 认证保护                       │   │
│  │  • Google Sheets API 数据读写                     │   │
│  │  • Google Drive API 照片上传                      │   │
│  └─────────────────────────────────────────────────┘   │
│                          ↑↓ API                         │
└─────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────┐
│                   Google 云服务层                        │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │ Google Sheets│    │ Google Drive │                  │
│  │ • 结构化数据  │    │ • 照片文件   │                  │
│  │ • 多张工作表  │    │ • 公开分享   │                  │
│  └──────────────┘    └──────────────┘                  │
└─────────────────────────────────────────────────────────┘
```

### 1.2 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | HTML5 + CSS3 + Vanilla JS | 无框架依赖，单文件内联 |
| 后端 | Flask (Python 3) | 轻量级 Web 框架 |
| WSGI | Gunicorn | 生产环境服务器 |
| 数据存储 | Google Sheets API | 结构化记录存储 |
| 文件存储 | Google Drive API | 照片文件存储 |
| 认证 | HTTP Basic Auth | 简单的用户名/密码保护 |
| 部署 | Render | 免费 tier 托管 |

---

## 二、前端架构详解

### 2.1 单页应用 (SPA) 设计

`templates/index.html` 是一个完整的单页应用，包含四个主要页面：

- **今日 (today)** - 显示今日概览、时间轴、照片缩略图
- **输入 (input)** - 快捷操作按钮，点击弹出输入表单模态框
- **日历 (calendar)** - 月度日历视图，带照片标记
- **成长 (growth)** - 成长曲线图表、喝奶量统计

页面切换通过 JavaScript `switchPage()` 函数实现 CSS class 的显示/隐藏，无页面刷新。

### 2.2 UI 组件

| 组件 | 实现方式 | 说明 |
|------|----------|------|
| 底部导航栏 | CSS fixed 定位 + 图标 | iOS 风格 Tab 切换 |
| 时间选择器 | CSS scroll-snap 滚动轮 | 模拟 iOS 滚轮选择器 |
| 日期选择器 | CSS Grid 日历 + 模态框 | 月份导航，today/selected 高亮 |
| 输入模态框 | CSS fixed 全屏遮罩 | 动态生成表单内容 |
| 图片查看器 | CSS fixed 全屏遮罩 | 点击照片放大查看 |
| Toast 提示 | CSS fixed + transition | 操作反馈消息 |
| 图表 | HTML5 Canvas 2D API | 喝奶量柱状图、成长曲线 |

### 2.3 前端数据流

```
用户操作 → 表单提交 → submitRecord() → fetch('/api/add') → 显示 Toast
                                              ↓
                              成功后 → fetchData() → 刷新所有页面数据
```

---

## 三、后端架构详解

### 3.1 Flask 路由结构

| 端点 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 返回主页 (index.html) |
| `/api/data` | GET | 获取所有数据 (所有工作表) |
| `/api/add` | POST | 添加记录 |
| `/api/update` | POST | 更新记录 (删除旧行+追加新行) |
| `/api/delete` | POST | 删除记录 |
| `/api/upload` | POST | 上传照片到 Google Drive |
| `/api/who` | GET | 获取 WHO 成长参考数据 |
| `/api/stats` | GET | 获取今日统计数据 |

### 3.2 认证机制

使用 **HTTP Basic Auth** 保护所有端点：
- 用户名: `family` (固定)
- 密码: `APP_PASSWORD` (通过环境变量配置)
- 装饰器: `@requires_auth`

### 3.3 Google 服务集成

后端使用两种不同的 Google 认证方式：

#### Service Account (服务账号) - 用于 Google Sheets

```
GOOGLE_SERVICE_ACCOUNT_JSON → JSON 凭据 → gspread 授权 → 读写 Sheets
```

- 用途: 读写 Google Sheets 数据
- 权限: 需要 Sheet 的编辑权限 (分享邮箱给 Service Account)
- 配置: `GOOGLE_SERVICE_ACCOUNT_JSON` 环境变量

#### OAuth 2.0 - 用于 Google Drive 照片上传

```
Client ID + Client Secret + Refresh Token → 刷新 Access Token → Drive API 上传
```

- 用途: 上传照片到用户的 Google Drive
- 权限: `drive.file` scope
- 配置: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`

### 3.4 数据存储结构

Google Sheets 中的工作表布局：

| 工作表名 | 用途 | 列头 |
|----------|------|------|
| **Sheet1** | 成长数据 | `date`, `weight_kg`, `height_cm`, `head_cm`, `note` |
| **milk** | 喂奶记录 | `timestamp`, `amount_ml`, `type`, `note` |
| **food** | 辅食记录 | `timestamp`, `food_type`, `amount`, `note` |
| **poop** | 排便记录 | `timestamp`, `type`, `color`, `note` |
| **sleep** | 睡眠记录 | `start_time`, `end_time`, `duration_min`, `note` |
| **photo** | 照片记录 | `timestamp`, `drive_url`, `caption` |
| **milestone** | 里程碑 | `date`, `category`, `description` |
| **other** | 其他记录 | `timestamp`, `category`, `content` |

---

## 四、配置文件详解

### 4.1 .env 文件

```bash
# 宝宝出生日期 (格式: YYYY-MM-DD)
BIRTH_DATE=2025-12-31

# 登录密码
APP_PASSWORD=mengxia2025

# Google Sheet ID (从 URL 中提取)
SHEET_ID=1A-KXtLnh3Lepor9REDG5wP8mfcpXvqyiV4bFO21858s

# Service Account 邮箱 (用于分享 Sheet)
OWNER_EMAIL=baby-tracker-sheets@baby-tracker-495809.iam.gserviceaccount.com

# Service Account JSON 凭据 (完整 JSON 字符串)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...","private_key":"...","client_email":"..."}

# OAuth 应用凭据 (用于 Drive 上传)
GOOGLE_OAUTH_CLIENT_ID=599606804561-xxx.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_OAUTH_REFRESH_TOKEN=1//04M8ZYtYkbheICgYIARAAGAQSNwF-xxx
```

### 4.2 环境变量说明

| 变量名 | 必填 | 获取方式 |
|--------|------|----------|
| `BIRTH_DATE` | 是 | 宝宝实际出生日期 |
| `APP_PASSWORD` | 是 | 自定义登录密码 |
| `SHEET_ID` | 是 | Google Sheet URL 中的 ID |
| `OWNER_EMAIL` | 否 | Service Account 的邮箱地址 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | 是 | Google Cloud Console 下载的 JSON 密钥 |
| `GOOGLE_OAUTH_CLIENT_ID` | 是 (如需上传照片) | Google Cloud OAuth 2.0 凭据 |
| `GOOGLE_OAUTH_CLIENT_SECRET` | 是 (如需上传照片) | Google Cloud OAuth 2.0 凭据 |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | 是 (如需上传照片) | OAuth Playground 获取 |

---

## 五、本地开发指南

### 5.1 环境准备

```bash
# 1. 克隆项目
cd MengxiaApp

# 2. 创建虚拟环境 (推荐)
python -m venv venv
venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt
```

### 5.2 配置文件

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env，填入实际值
```

### 5.3 运行应用

```bash
# 开发模式
python app.py

# 访问 http://localhost:5000
# 用户名: family
# 密码: APP_PASSWORD 中设置的值
```

---

## 六、部署指南 (Render)

### 6.1 创建 Web Service

1. 访问 [Render Dashboard](https://dashboard.render.com/)
2. 点击 **New +** → **Web Service**
3. 连接 GitHub 仓库

### 6.2 配置环境变量

在 Render Dashboard → Environment 中添加：

- `BIRTH_DATE`
- `APP_PASSWORD`
- `SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (完整 JSON 字符串)
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REFRESH_TOKEN`

### 6.3 配置文件

`render.yaml` 已包含在项目中，Render 会自动读取：

```yaml
services:
  - type: web
    name: baby-tracker
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
```

---

## 七、Google 服务配置步骤

### 7.1 创建 Google Cloud 项目

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目 (例如 `baby-tracker`)
3. 启用以下 API：
   - **Google Sheets API**
   - **Google Drive API**

### 7.2 配置 Service Account (用于 Sheets)

1. 进入 **IAM & Admin** → **Service Accounts**
2. 点击 **Create Service Account**
3. 名称: `baby-tracker-sheets`
4. 角色: `Editor` (或自定义)
5. 创建后进入该 Service Account → **Keys** → **Add Key** → **JSON**
6. 下载 JSON 文件，将内容完整复制到 `GOOGLE_SERVICE_ACCOUNT_JSON`

### 7.3 创建 Google Sheet

1. 访问 [Google Sheets](https://sheets.new)
2. 创建空白表格
3. 从 URL 复制 `SHEET_ID`:
   ```
   https://docs.google.com/spreadsheets/d/SHEET_ID/edit
   ```
4. 点击 **Share** → 添加 Service Account 邮箱 → 权限选 **Editor**

### 7.4 配置 OAuth (用于 Drive 照片上传)

1. 进入 **APIs & Services** → **Credentials**
2. 点击 **Create Credentials** → **OAuth client ID**
3. 应用类型选择 **Desktop app**
4. 复制 `Client ID` 和 `Client Secret`

获取 Refresh Token：

1. 访问 [OAuth Playground](https://developers.google.com/oauthplayground)
2. 点击设置图标 (右上角) → 勾选 **Use your own OAuth credentials**
3. 填入 Client ID 和 Client Secret
4. 在左侧选择 scope: `https://www.googleapis.com/auth/drive.file`
5. 点击 **Authorize APIs** → 登录授权
6. 点击 **Exchange authorization code for tokens**
7. 复制 **Refresh Token**

---

## 八、项目文件结构

```
MengxiaApp/
├── app.py                 # Flask 后端主文件
├── requirements.txt       # Python 依赖
├── .env                   # 环境变量 (本地使用，不提交到 Git)
├── .env.example           # 环境变量示例
├── render.yaml            # Render 部署配置
├── test_app.py            # 后端 API 测试脚本
├── templates/
│   └── index.html         # 前端单页应用 (HTML + CSS + JS)
└── README.md              # 本文档
```

---

## 九、常见问题与修复记录

### 9.1 时间选择器首尾值无法选中

**问题**: 滚轮选择器无法选中 00:00 和 23:59。

**根因**: 每个滚轮仅有 1 个空 padding 项，导致首尾项无法滚动到可视区域中心。

**修复**: 将 padding 项从 1 个增加到 2 个 (每端)，确保所有值都能被 `scroll-snap-align: center` 捕获。

### 9.2 照片上传失败

**可能原因**:
1. Google Drive API 未启用
2. OAuth 凭据过期或配置错误
3. Service Account 没有 Drive API 权限

**修复建议**:
- 检查 `GOOGLE_OAUTH_REFRESH_TOKEN` 是否有效
- 确认 Google Drive API 已在 Cloud Console 启用
- 查看 Render 日志获取具体错误信息

### 9.3 成长数据保存失败

**根因**: `submitRecord()` 调用 `/api/add`，后端 `add_record()` 对 `growth` 类型使用 `Sheet1` 工作表。

**排查**: 
- 确认 Sheet1 存在且 Service Account 有编辑权限
- 检查 Sheet1 第一行是否有表头 `date,weight_kg,height_cm,head_cm,note`

### 9.4 日历日期显示 "开发中"

**根因**: `showDateDetails()` 函数仅显示 Toast，未实现详情弹窗。

**状态**: 功能占位，可扩展为显示当日所有记录的详情面板。

---

## 十、时区说明

- 所有时间使用 **新加坡时区 (UTC+8)**
- 后端通过 `SINGAPORE_TZ = timezone(timedelta(hours=8))` 定义
- 前端通过 `getNowStr()` 使用浏览器本地时间 (需确保设备时区为 +8)

---

## 许可证

MIT License - 仅供家庭使用
