# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Discord 自动营销机器人系统 - 基于 Tauri + Python 的跨平台桌面应用。支持多 Discord 账号管理，自动发送微店商品链接到指定频道，具备账号轮换、定时发送等功能。

### 技术栈
- **前端**: Tauri + React + TypeScript + Tailwind CSS + shadcn/ui
- **后端**: Python (Flask) + discord.py-self
- **数据库**: SQLite
- **构建**: GitHub Actions (Windows exe)

## 项目结构

```
DiscordSend/
├── backend/                    # Python 后端
│   ├── app.py                  # Flask API 入口
│   ├── bot.py                  # Discord 机器人客户端
│   ├── database.py             # SQLite 数据库管理
│   ├── weidian_scraper.py      # 微店商品抓取
│   ├── auto_sender.py          # 自动发送任务调度
│   ├── config.py               # 配置文件
│   └── requirements.txt        # Python 依赖
├── src/                        # Tauri 前端 (React)
│   ├── components/             # UI 组件
│   ├── pages/                  # 页面组件
│   └── App.tsx                 # 主应用
├── src-tauri/                  # Tauri Rust 核心
│   ├── src/main.rs
│   └── tauri.conf.json
├── .github/workflows/          # GitHub Actions
│   └── build.yml               # Windows 构建流程
└── CLAUDE.md
```

## 核心架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     Tauri Desktop App                             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    React Frontend                           │  │
│  │  - 账号管理页面 (AccountsView)                              │  │
│  │  - 店铺管理页面 (ShopsView)                                 │  │
│  │  - 自动发送控制台 (AutoSenderView)                          │  │
│  └──────────────────────┬─────────────────────────────────────┘  │
│                         │ HTTP API                                │
│  ┌──────────────────────▼─────────────────────────────────────┐  │
│  │                 Python Sidecar (Flask)                      │  │
│  │  - /api/accounts      账号管理                              │  │
│  │  - /api/shops         店铺管理                              │  │
│  │  - /api/sender/start  启动自动发送                          │  │
│  │  - /api/sender/stop   停止自动发送                          │  │
│  └──────────────────────┬─────────────────────────────────────┘  │
└─────────────────────────┼────────────────────────────────────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    ▼                     ▼                     ▼
┌─────────┐      ┌──────────────┐      ┌──────────────┐
│ bot.py  │      │ database.py  │      │ auto_sender  │
│ Discord │◄────►│   SQLite     │◄────►│  任务调度     │
│ 多账号   │      │  metadata.db │      │  轮换发送     │
└─────────┘      └──────────────┘      └──────────────┘
                          │
                          ▼
              ┌──────────────────────────┐
              │   weidian_scraper.py     │
              │   微店 API 商品抓取       │
              └──────────────────────────┘
```

## 核心模块

### backend/bot.py
- `DiscordBotClient`: Discord 客户端类，继承自 `discord.Client`
- `bot_clients`: 全局列表，存储所有活跃的机器人实例
- `bot_loop`: 全局事件循环，供跨线程调用
- 账号角色: `listener`(只监听)、`sender`(只发送)、`both`(两者)
- 冷却机制: `account_last_sent` 字典管理发送冷却

### backend/database.py
- `Database` 类: SQLite 数据库管理
- 数据库路径: `backend/data/metadata.db`
- 主要表: `products`, `shops`, `discord_accounts`, `send_tasks`
- 使用 WAL 模式提高并发性能

### backend/auto_sender.py
- `auto_send_loop()`: 异步发送循环
- `stop_sender_event`: asyncio.Event 控制任务停止
- Round Robin 轮换算法: `bot_idx % len(active_bots)`
- 支持可中断的间隔等待

### backend/weidian_scraper.py
- `WeidianScraper` 类: 微店商品抓取器
- 使用微店官方 API 获取商品信息
- 多线程图片下载 (线程池)

## 常用命令

### 开发

```bash
# 安装 Python 依赖
cd backend && pip install -r requirements.txt

# 启动后端 (开发模式)
cd backend && python app.py

# 安装前端依赖
npm install

# 启动 Tauri 开发服务器
npm run tauri dev
```

### 构建

```bash
# 构建 Python 后端为可执行文件 (PyInstaller)
cd backend && pyinstaller --onefile app.py

# 构建 Tauri 应用
npm run tauri build
```

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/accounts` | GET | 获取所有 Discord 账号 |
| `/api/accounts` | POST | 添加新账号 (token) |
| `/api/accounts/<id>` | DELETE | 删除账号 |
| `/api/accounts/<id>/start` | POST | 启动账号连接 |
| `/api/accounts/<id>/stop` | POST | 停止账号连接 |
| `/api/shops` | GET | 获取所有店铺 |
| `/api/shops` | POST | 添加新店铺 |
| `/api/shops/<id>/scrape` | POST | 抓取店铺商品 |
| `/api/sender/start` | POST | 启动自动发送任务 |
| `/api/sender/stop` | POST | 停止自动发送任务 |
| `/api/sender/status` | GET | 获取发送任务状态 |

## 配置说明 (config.py)

```python
BACKEND_API_URL = "http://127.0.0.1:5001"  # 后端 API 地址
FLASK_PORT = 5001                           # Flask 端口
DISCORD_SIMILARITY_THRESHOLD = 0.6          # 图片相似度阈值
DOWNLOAD_THREADS = 4                        # 下载线程数
```

## 注意事项

- 使用 `discord.py-self` 而非官方 `discord.py`，用于用户账号而非 Bot 账号
- Flask 与 Discord.py 运行在不同线程，使用 `asyncio.run_coroutine_threadsafe()` 跨线程调用
- Tauri Sidecar 使用 PyInstaller 打包 Python 后端
- GitHub Actions 在 Windows 环境构建 exe 文件
