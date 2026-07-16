# 网络舆情事件智能分析系统

本项目是一套面向网络新闻与舆情信息的采集、NLP 分析、事件聚合、风险评估和可视化展示系统。系统将多篇相关报道聚合为事件，并展示时间线、趋势、热度、生命周期、情感、AI 报告和真实性分析结果。

## 系统架构

```text
crawler
   ↓
backend
   ↓
analysis / NLP
   ↓
event aggregation
   ↓
AI service
   ↓
frontend
```

实际运行时，爬虫将文章提交给后端；后端调用 NLP 服务生成分析结果，完成事件聚合和事件级指标更新；AI 服务为问答、报告和真实性分析提供增强能力；前端通过后端 API 展示结果。

## 模块说明

1. **数据采集层（`crawler/`）**
   抓取新闻数据，完成清洗、去重和提交。爬虫不由统一启动脚本自动启动，需要时单独运行。

2. **NLP 分析层（`analysis/`）**
   提供摘要、关键词、情感、风险、热度和文本向量等分析结果，通过 HTTP 接口与后端联动。

3. **事件聚合层（`backend/backend_app/services/`）**
   先使用 embedding 进行语义候选召回，再结合 fingerprint、实体、动作和标题等信号辅助判断。符合条件的文章进入已有事件簇；无匹配事件时创建新事件并生成 `event_id`。

4. **热度与生命周期计算**
   后端根据已有文章和分析结果更新事件热度、风险等级和生命周期阶段，并保留热度历史供趋势展示。

5. **AI 增强分析层（`ai_service/`）**
   提供事件问答、AI 报告、真实性分析和证据关系分析。支持 Fake Provider 用于离线测试，也可通过环境变量配置 DeepSeek。

6. **前端展示层（`frontend/`）**
   展示热点事件、新闻、事件详情、时间线、趋势、情感、事件报告和真实性分析结果。

## 运行环境

- Python 3.11 或更高版本
- Node.js 20 或更高版本
- pnpm（推荐）或 npm
- MySQL 8

## 默认端口

| 服务 | 端口 | 地址 |
|---|---:|---|
| Backend | 8000 | `http://127.0.0.1:8000` |
| Frontend | 5173 | `http://127.0.0.1:5173` |
| NLP | 9000 | `http://127.0.0.1:9000/nlp/analyze` |
| AI Service | 8005 | `http://127.0.0.1:8005` |

## 配置与安装

仓库不包含真实 `.env` 或密钥。先根据示例文件创建本地配置：

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item ai_service/.env.example ai_service/.env
Copy-Item frontend/.env.example frontend/.env
```

然后分别安装依赖：

```powershell
python -m pip install -r backend/requirements.txt
python -m pip install -r analysis/requirements.txt
python -m pip install -e ai_service
Set-Location frontend
pnpm install
Set-Location ..
```

MySQL 数据库和用户需要提前创建，并在 `backend/.env` 中填写连接信息。仓库中的迁移 SQL 需按实际部署情况手动执行，启动脚本不会自动修改数据库。

## 启动顺序

```text
MySQL
  ↓
AI service
  ↓
NLP service
  ↓
backend
  ↓
frontend
```

### Windows 统一启动

确保 MySQL 已启动且环境文件已配置，然后在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start_system.ps1
```

[start_system.ps1](start_system.ps1) 会检查 Python、Node.js 和前端包管理器，优先使用各模块的 `.venv`，并按 AI、NLP、Backend、Frontend 的顺序打开独立 PowerShell 窗口。脚本不启动 MySQL、不安装依赖、不修改数据库，也不自动启动爬虫。

### 手动启动

```powershell
# AI service - 8005
Set-Location ai_service
python -m uvicorn app.main:app --host 127.0.0.1 --port 8005

# NLP service - 9000（仓库根目录）
Set-Location ..
python -m analysis.nlp_api_server --host 127.0.0.1 --port 9000

# Backend - 8000
Set-Location backend
python -m uvicorn backend_app.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend - 5173
Set-Location ../frontend
pnpm run dev
```

### 单独运行爬虫

确保 Backend 可用后，在仓库根目录运行：

```powershell
python -m crawler.run
```

## 常用检查

```powershell
# Backend 测试
Set-Location backend
python -m unittest discover -s tests

# AI service 测试
Set-Location ../ai_service
python -m pytest

# Frontend 测试与构建
Set-Location ../frontend
pnpm test
pnpm run build
```

## 安全说明

- 不要提交 `backend/.env`、`ai_service/.env`、`frontend/.env` 或任何真实 API Key。
- `backup/`、`debug_html/`、`data/`、`output/`、日志、虚拟环境、依赖和构建产物均已通过 `.gitignore` 排除。
- AI 结果只能作为当前输入材料范围内的辅助分析，不代表最终权威认定。
