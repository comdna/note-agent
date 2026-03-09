# NoteAgent

一个面向学习/知识管理场景的 AI Agent 笔记系统：

- 项目级会话管理
- 普通文件上传、读取、更新、删除
- PDF 知识库检索问答（RAG）
- Agent 工具调度（文件工具 / 知识库工具 / Web 搜索）
- 流式回复、引用来源、提案式文件修改（Apply/Reject）
- 会话级“背景文件”上下文（可指定普通文本文件作为持续参考）

---

## 功能概览

### 1) 项目与会话
- 创建/删除项目
- 多会话管理
- 会话消息持久化

### 2) 普通文件工作流
- 支持上传 `txt/md/json/py/js/html/css/jpg/png/gif/pdf`
- 对文本文件支持读取与版本化更新
- Agent 可调用文件工具完成 `list/read/update/delete`

### 3) 知识库问答（PDF）
- 上传 PDF 构建项目知识库
- 向量检索 + LLM 生成回答
- 返回引用来源（文档名、页码、分数）

### 4) Agent 与意图识别
- 基于 LLM 的意图分类
- LangGraph 工作流：`decide <-> tool` 多轮，直到 `final`
- 工具结果可回传步骤（tool steps），便于可解释

### 5) 会话背景文件
- 支持给会话绑定 `background_file_ids`
- 将选中文本文件拼接为上下文参与回答
- 自动过滤无效/非文本/知识库文件

---

## 技术栈

- 后端：`Flask`, `Flask-CORS`
- Agent 编排：`langgraph`
- LLM 调用：`DeepSeek API`（`requests`）
- RAG：`PyPDF`, `sentence-transformers`, `faiss-cpu`, `numpy`
- 配置：`python-dotenv`
- 测试：`unittest`

---

## 项目结构

```text
app/
  routes/
    api.py
    main.py
  services/
    agent_service.py
    chat_service.py
    file_service.py
    kb_service.py
    llm_service.py
    project_service.py
static/
templates/
tests/
main.py
```

---

## 快速开始

### 1. 环境要求
- Python `>= 3.12`

### 2. 安装依赖

使用 `uv`（推荐）：

```bash
uv sync
```

或使用 `pip`：

```bash
pip install -e .
```

### 3. 配置环境变量

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=your_api_key_here
SERPAPI_KEY=your_serpapi_key_here
SECRET_KEY=your_secret_key_here
```

### 4. 启动服务

```bash
python main.py
```

默认地址：`http://127.0.0.1:5000`

---

## 关键 API（节选）

- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/<project_id>/files`
- `POST /api/projects/<project_id>/files`
- `GET /api/projects/<project_id>/kb/files`
- `POST /api/projects/<project_id>/kb/files`
- `POST /api/projects/<project_id>/chats/<chat_id>/messages`
- `POST /api/projects/<project_id>/chats/<chat_id>/stream`
- `PUT /api/projects/<project_id>/chats/<chat_id>/background-files`

> 详细参数可参考 `app/routes/api.py`。

---

## 测试

已包含部分核心单元测试（工具执行、意图识别、背景文件上下文）：

```bash
python -m unittest tests/test_agent_service.py
python -m unittest tests/test_intent_detection.py
python -m unittest tests/test_chat_background_context.py
```

---
