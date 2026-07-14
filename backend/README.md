# 网络舆情事件智能分析系统后端


## 技术栈


- FastAPI

- SQLAlchemy

- MySQL

- Pydantic



## 启动


创建虚拟环境


pip install -r requirements.txt



运行:


uvicorn backend_app.main:app --reload



## API


### 新闻采集


POST

/internal/articles



### NLP分析


POST

/internal/analysis



### 事件列表


GET

/api/events



### 事件详情


GET

/api/events/{id}



### AI问答


POST

/api/ai/ask



### AI报告


POST

/api/ai/report/{id}



### 登录


POST

/api/login



## 数据流


3号爬虫

↓

articles


4号NLP

↓

analysis


事件聚合

↓

events


5号AI

↓

ai_results


前端

↓

API

## 项目结构
backend
│
├── backend_app
│   │
│   ├── models
│   ├── schemas
│   ├── routers
│   ├── services
│   ├── utils
│   └── main.py
│
├── requirements.txt
│
├── database.sql
│
├── docker-compose.yml
│
└── README.md
