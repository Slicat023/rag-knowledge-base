[简体中文](README.md) | [English](README.en.md)

# 知库 RAG

知库是一个面向中文文档问答的知识库项目：使用 Unstructured 解析文件、LlamaIndex 串联检索流程、本地 BGE 模型生成向量并重排序、Chroma 持久化数据，再通过通义千问或 DeepSeek 流式生成回答。FastAPI 提供轻量 Web 界面，无需 Node.js 构建。

> 向量化和重排序在本地运行；生成回答时，检索到的文档片段会发送给所选云端模型。上传敏感文档前，请先阅读[数据与使用边界](#数据与使用边界)。

## 主要功能

- **知识问答**：流式输出、多轮对话，以及可点击的文件名、页码（如有）和原文片段引用。
- **文档管理**：拖拽上传、后台解析、状态查看、失败重试、下载原文和删除文件。
- **本地检索**：`BAAI/bge-base-zh-v1.5` 向量化，Chroma 持久化，`BAAI/bge-reranker-base` 重排序。
- **模型切换**：通过 OpenAI 兼容接口接入通义千问和 DeepSeek，可在页面中选择。
- **运行状态**：健康检查接口展示模型加载状态、文档数和向量数。

## 快速开始

使用 **Python 3.11**。依赖和本地模型需要数 GB 磁盘空间，建议至少 16 GB 内存。CPU 可以运行；`auto` 模式会在当前 PyTorch 能识别兼容 GPU 时使用 CUDA。以下命令均在 `RAG` 目录执行。

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

### Linux / macOS

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
```

编辑 `.env`，至少填写一个模型的 API Key：

```dotenv
QWEN_API_KEY=你的通义千问Key
# 也可以用 DASHSCOPE_API_KEY 代替 QWEN_API_KEY
DEEPSEEK_API_KEY=你的DeepSeekKey
```

只配置一家即可；两家都配置时可以在页面中切换。若需调整模型路径或下载镜像，也请在下载前修改 `.env`。建议用虚拟环境中的 Python 运行 `scripts/setup_spacy.py`，安装 Unstructured 使用的小型英语 spaCy 模型；未安装时应用会启用轻量回退处理。

下载本地模型并启动服务：

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe scripts/download_models.py
.\.venv\Scripts\python.exe run.py
```

```bash
# Linux / macOS
.venv/bin/python scripts/download_models.py
.venv/bin/python run.py
```

打开[问答页](http://127.0.0.1:8000/)、[知识库](http://127.0.0.1:8000/knowledge)或 [API 文档](http://127.0.0.1:8000/api/docs)。首次启动会在后台预热两个本地模型，首次提问可能等待模型加载。

Windows 也可运行 `start.bat`：它会在缺失时创建虚拟环境和 `.env`、安装依赖、下载模型并启动应用。首次运行后，请填写 `.env` 并重启服务。另有 `start.ps1` 可供 PowerShell 使用。

### 体验示例

1. 在知识库页面上传 `samples/` 中的任意一份 Markdown 文档。
2. 等待状态变为“已就绪”（API 中为 `ready`）。
3. 提问“差旅制度中的住宿标准是多少？”，点击回答下方的引用查看原文。

## 工作原理

```text
上传文件 -> Unstructured 解析 -> 章节与表格上下文 -> 按字符切分
         -> 本地 BGE 向量化 -> Chroma 持久化

用户提问 -> Chroma Top-K 召回 -> 本地 BGE 重排序 -> 带编号的参考片段
         -> 通义千问 / DeepSeek -> SSE 流式回答
```

解析器按元素顺序维护多级章节、表格标题和子标题，并在跨页时继承上下文。每个分块的 metadata 保存完整章节路径、表格信息、文件名和页码；参与向量化的文本只附加文档标题、最近几级章节和表格标签，避免完整路径挤占分块预算。`EMBED_CONTEXT_LEVELS` 控制附加的章节层数。默认分块大小为 420 字符、重叠 60 字符；向量召回 12 条，重排序后最多保留 6 条。

## 配置说明

复制 `.env.example` 为 `.env` 后修改配置。本地模型使用相对路径时，以项目目录为基准解析。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `QWEN_API_KEY` / `DASHSCOPE_API_KEY` | 空 | 通义千问 / DashScope Key |
| `QWEN_MODEL` | `qwen-plus` | 通义千问模型名 |
| `QWEN_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 通义千问接口地址 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek Key |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型名 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek 接口地址 |
| `DEFAULT_LLM` | `qwen` | 页面默认选择的模型 |
| `EMBEDDING_MODEL` | `models/bge-base-zh-v1.5` | 本地向量模型路径 |
| `RERANKER_MODEL` | `models/bge-reranker-base` | 本地重排序模型路径 |
| `EMBEDDING_DEVICE` / `RERANK_DEVICE` | `auto` | `auto`、`cpu` 或 CUDA 设备 |
| `RETRIEVAL_TOP_K` / `RERANKER_TOP_N` | `12` / `6` | 召回与重排序数量 |
| `RERANK_ENABLED` | `true` | 是否启用本地重排序 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `420` / `60` | 按字符切分的大小与重叠量 |
| `EMBED_CONTEXT_LEVELS` | `3` | 向量文本中保留的最近章节层数 |
| `MAX_UPLOAD_MB` | `50` | 单文件上传上限 |
| `WARMUP_MODELS` | `true` | 启动后是否预热本地模型 |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 服务监听地址与端口 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | 模型下载使用的 Hugging Face 镜像 |

模型下载脚本默认先尝试 ModelScope，失败后再尝试配置的 Hugging Face 镜像。可指定来源或只下载一个模型：

```bash
python scripts/download_models.py --source hf
python scripts/download_models.py --only embedding
```

未激活虚拟环境时，将上述 `python` 换成对应平台的虚拟环境 Python 路径。

## 文档格式与 API

支持上传 `.pdf`、`.docx`、`.pptx`、`.xlsx`、`.txt`、`.md`、`.markdown`、`.csv`、`.html`、`.htm`。文字版 PDF 可解析；扫描版 PDF 需要 OCR，本项目未内置。旧版 `.doc`、`.xls` 不在支持范围内。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 模型、文档和向量状态 |
| `GET` | `/api/documents` | 文件列表 |
| `POST` | `/api/documents` | 上传一个或多个文件（`multipart/form-data`，字段名 `files`） |
| `DELETE` | `/api/documents/{id}` | 删除文件及其向量 |
| `POST` | `/api/documents/{id}/retry` | 重试解析失败的文件 |
| `GET` | `/api/documents/{id}/download` | 下载原始文件 |
| `POST` | `/api/chat` | SSE 流式问答 |

`/api/chat` 的 JSON 请求示例（`provider`、`top_k`、`rerank_top_n` 均可省略）：

```json
{
  "message": "住宿标准是多少？",
  "history": [],
  "provider": "qwen",
  "top_k": 12,
  "rerank_top_n": 6
}
```

SSE 事件包括 `sources`（引用与检索统计）、`delta`（新增回答文本）、`done`（耗时）和 `error`（可读错误）。完整请求结构见 `/api/docs`。

## 目录结构

```text
RAG/
├── app/api/           # 问答、文档和健康检查接口
├── app/services/      # 解析、向量化、检索、重排序、入库
├── app/templates/     # Web 页面
├── app/static/        # 前端资源
├── data/              # 运行时文档、Chroma、清单与缓存
├── models/            # 下载的本地模型
├── samples/           # 示例文档
├── scripts/           # 模型下载和自检脚本
├── tests/
├── .env.example
├── requirements.txt
├── run.py
└── README.md / README.en.md
```

## 验证与排错

```bash
python -m pytest
python scripts/check_setup.py --load-models
python scripts/check_llm.py --provider qwen
```

请使用虚拟环境中的 Python 执行这些命令。单元测试不需要 API Key，也不会加载大模型。`check_setup.py --load-models` 会实际加载两个本地模型；`check_llm.py` 会真实调用云端接口，需要有效 Key。检查 DeepSeek 时改用 `--provider deepseek`。

- **模型下载失败**：尝试 `python scripts/download_models.py --source hf`，或按网络环境配置 `HTTP_PROXY` / `HTTPS_PROXY`。
- **没有 GPU**：`auto` 会回退到 CPU，首次加载和回答会更慢。
- **重排序模型不可用**：运行模型下载脚本；也可在 `.env` 中临时设置 `RERANK_ENABLED=false`，直接按向量相似度排序。
- **上传一直处于处理中**：刷新页面查看状态。服务重启后，未完成的任务会标记为失败，可点击重试。
- **数据存放位置**：原文在 `data/documents/`，向量在 `data/chroma/`，文件清单在 `data/registry.json`。请通过页面或 API 删除文件，以同时清理向量。

## 数据与使用边界

- 向量化、重排序、文件存储和 Web 界面在本地运行。问答时，所选通义千问或 DeepSeek 云端 API 会收到检索到的文档片段；请只上传允许发送给该服务商的文档。
- 项目未提供登录和用户权限隔离，默认监听 `127.0.0.1`。不要直接暴露在不可信网络中。
- 多轮历史会参与生成回答，但不会改写检索问题。“那经理呢？”等省略上下文的追问可能召回较差。
- 检索相关度仅供排序参考，不是答案正确概率。扫描版 PDF 和复杂版面在没有 OCR 时可能解析不佳。
- 请自行备份 `data/`。示例文档中的公司及联系方式均为虚构。已知问题和验证缺口见 [ISSUES.md](ISSUES.md)。
