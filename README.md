<<<<<<< HEAD
# 宝宝成长记录应用

轻量级 Flask 网页应用，用于记录宝宝喂奶、辅食、排便、睡眠、照片、里程碑等日常活动。

## 功能特性

- 🍼 **喂奶记录** - 记录奶量、类型和时间
- 🍚 **辅食记录** - 记录食物类型和食量
- 💩 **排便记录** - 记录形状、颜色
- 😴 **睡眠记录** - 记录睡眠时长
- 📸 **照片上传** - 直传到 Google Drive
- 🎯 **里程碑** - 记录成长重要时刻
- 📏 **成长测量** - 体重、身高、头围曲线
- 📊 **今日概览** - 快速查看今日统计

## 技术栈

- **后端**: Flask + Gunicorn
- **存储**: Google Sheets + Google Drive
- **前端**: 纯 HTML/CSS/JS (内联)
- **部署**: Render (免费 tier)

## 快速开始

### 1. 克隆项目

```bash
cd baby-tracker
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填入实际值：

```bash
cp .env.example .env
```

### 4. 运行应用

```bash
python app.py
```

访问 `http://localhost:5000`，使用用户名 `family` 和设置的密码登录。

## Google 服务配置

### 1. 创建 Google Cloud 项目

- 访问 [Google Cloud Console](https://console.cloud.google.com/)
- 创建新项目或选择现有项目
- 启用 APIs: Google Sheets API, Google Drive API

### 2. Service Account (用于 Sheets)

1. 创建 Service Account
2. 下载 JSON 密钥
3. 分享 Google Sheet 给 Service Account 的邮箱 (有编辑权限)
4. 将 JSON 内容填入 `GOOGLE_SERVICE_ACCOUNT_JSON`

### 3. OAuth 应用 (用于 Drive 上传)

1. 创建 OAuth 2.0 客户端 ID (桌面应用类型)
2. 获取 Client ID 和 Client Secret
3. 使用 [OAuth Playground](https://developers.google.com/oauthplayground) 获取 Refresh Token:
   - 选择 scope: `https://www.googleapis.com/auth/drive.file`
   - 使用自己的客户端凭据
   - 授权后复制 Refresh Token

### 4. 创建 Google Sheet

1. 创建新表格
2. 从 URL 复制 Sheet ID
3. 分享给 Service Account (编辑权限)
4. 填入 `SHEET_ID`

## 部署到 Render

1. 在 [Render](https://render.com/) 创建 Web Service
2. 选择 Python 环境
3. 设置环境变量:
   - `BIRTH_DATE`
   - `APP_PASSWORD`
   - `SHEET_ID`
   - `GOOGLE_SERVICE_ACCOUNT_JSON`
   - `GOOGLE_OAUTH_CLIENT_ID`
   - `GOOGLE_OAUTH_CLIENT_SECRET`
   - `GOOGLE_OAUTH_REFRESH_TOKEN`
4. 部署后获得公开 URL，分享给家人

## 数据存储结构

### Google Sheets

- **Sheet1**: 成长测量 (`date`, `weight_kg`, `height_cm`, `head_cm`, `note`)
- **milk**: 喂奶记录 (`timestamp`, `amount_ml`, `type`, `note`)
- **food**: 辅食记录 (`timestamp`, `food_type`, `amount`, `note`)
- **poop**: 排便记录 (`timestamp`, `type`, `color`, `note`)
- **sleep**: 睡眠记录 (`start_time`, `end_time`, `duration_min`, `note`)
- **photo**: 照片记录 (`timestamp`, `drive_url`, `caption`)
- **milestone**: 里程碑 (`date`, `category`, `description`)
- **other**: 其他记录 (`timestamp`, `category`, `content`)

### Google Drive

照片文件上传到用户个人 Drive，文件名格式: `YYYYMMDD_HHMMSS_original_filename.jpg`

## 注意事项

- 所有时间使用新加坡时区 (UTC+8)
- 密码使用 HTTP Basic Auth 保护
- 移动端优先的响应式设计
- 照片上传需要 OAuth 授权

## 许可证

MIT License - 仅供家庭使用
=======
# baby-tracker
>>>>>>> 25f8ea38cb3634b8f22e4235405ce08a05b8bf7e
