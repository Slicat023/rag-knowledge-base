# 知库 RAG

一个可以直接运行的中文 RAG 知识库项目：本地 BGE 向量化 + Chroma 检索 + BGE 重排序 + 通义千问 / DeepSeek 生成，并附带一个轻量的 Web 界面，用于问答和知识库文件管理。

> 前端不需要 Node.js 构建，Python 服务启动即可使用。

> 本次构建过程中发现的问题、已修复项和仍存在的风险，见 [ISSUES.md](ISSUES.md)。

## 功能

- **知识问答**：流式输出、多轮对话、引用来源可追溯（文件名 / 页码 / 原文片段）。
- **知识库管理**：拖拽上传、后台解析、处理状态、失败重试、下载原文、删除文件。
- **本地模型**：`BAAI/bge-base-zh-v1.5` 做向量，`BAAI/bge-reranker-base` 做重排序。
- **双模型切换**：通义千问、DeepSeek 通过 OpenAI 兼容接口接入，前端可切换。
- **离线优先**：模型、数据、界面资源都在本地；不依赖任何 CDN。
- **可观测**：健康检查展示模型加载状态、文档数量、向量数量。

## 技术栈

| 模块 | 选型 |
| --- | --- |
| RAG 框架 | LlamaIndex |
| 大模型 | 通义千问（DashScope）/ DeepSeek |
| Embedding | BAAI/bge-base-zh-v1.5（本地） |
| 向量数据库 | Chroma（PersistentClient） |
| 文档解析 | Unstructured（开源库，`strategy="fast"`） |
| 重排序 | BAAI/bge-reranker-base（CrossEncoder） |
| 后端 | FastAPI + Uvicorn |
| 前端 | 原生 HTML / CSS / JavaScript，Jinja2 模板 |

## 处理流程

```
上传文件
  └─ Unstructured 解析（按元素顺序遍历，维护多级章节树 / 表格上下文）
       └─ 跨页继承章节、表格标题、季节子表
            └─ SentenceSplitter 切分（中文按字符计数，420 字 / 60 字重叠，控制在 BGE 512 token 内）
                 └─ bge-base-zh-v1.5 向量化
                      └─ Chroma 持久化（metadata 带完整章节路径 / 表格标题 / 页码）

用户提问
  └─ Chroma 向量召回 Top-K（默认 12）
       └─ bge-reranker-base 重排序（默认保留 6 条）
            └─ 拼接带编号的资料上下文
                 └─ Qwen / DeepSeek 流式生成
                      └─ SSE 推送来源与 token
```

### 章节树与跨页表格

解析器不再先按页拼接，而是按 Unstructured 元素顺序维护一个章节栈：

- 支持 `第X章`、`一、`、`（一）`、`1.1` 等编号层级；
- 新标题出现时自动关闭同级/更深层级，形成多级路径；
- 页面结束时保留章节和当前表格上下文，后续页自动继承；
- `表 3.6 …` 识别为表格标题，`春季食谱 1`/`夏季食谱 1` 识别为表格子标题；
- 字体样式不可靠的 PDF 只使用编号规则，避免把表格单元格误判为标题。

每个 chunk 的 metadata 保存完整路径，例如：

```text
section_path = 成人肥胖食养指南 > 六、西南地区
full_path    = 成人肥胖食养指南 > 六、西南地区 > 表 3.6 西南地区四季食谱示例 > 夏季食谱 1
```

真正参与 embedding 的文本只拼：

```text
文档：成人肥胖食养指南
章节：六、西南地区
表格：表 3.6 西南地区四季食谱示例 / 夏季食谱 1
```

完整路径仍在 metadata 中，可通过 `EMBED_CONTEXT_LEVELS` 控制拼入 embedding 的最近章节层数（默认 3）。

## 目录结构

```text
RAG/
├─ app/
│  ├─ main.py                 # FastAPI 入口、页面路由
│  ├─ config.py               # .env 配置
│  ├─ deps.py                 # 服务单例
│  ├─ api/                    # chat / documents / system 接口
│  ├─ services/
│  │  ├─ parser.py            # Unstructured 解析 + 切分
│  │  ├─ embeddings.py        # BGE 向量模型
│  │  ├─ reranker.py          # BGE 重排序
│  │  ├─ vector_store.py      # Chroma + LlamaIndex Index
│  │  ├─ ingestion.py         # 上传后的处理生命周期
│  │  ├─ rag.py               # 检索、Prompt、流式回答
│  │  └─ registry.py          # 文件清单与状态
│  ├─ templates/              # 问答页 / 知识库页
│  └─ static/                 # CSS / JS
├─ data/                      # 运行时生成：文档、Chroma、registry.json
├─ models/                    # 下载的本地模型
├─ samples/                   # 两份可直接上传体验的中文示例文档
├─ scripts/download_models.py
├─ tests/
├─ .env.example
├─ requirements.txt
├─ run.py / start.bat / start.ps1
└─ README.md
```

## 快速开始

### 1. 环境要求

- Python **3.11**（Windows / Linux / macOS 均可）
- 首次安装依赖约 2–4 GB（含 PyTorch CPU 版）
- 建议 16 GB 内存；有 NVIDIA GPU 会自动使用 CUDA

```bash
cd D:\workwork\RAG

# 创建虚拟环境（Windows）
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -U pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果 PyPI 较慢，可使用国内镜像（把下面命令合成一行执行）：

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Linux / macOS 把 `.venv\Scripts\python.exe` 换成 `.venv/bin/python` 即可。

### 2. 下载本地模型

```bash
.venv\Scripts\python.exe scripts/download_models.py
```

脚本默认从 **ModelScope** 下载，失败时自动尝试 HuggingFace 镜像（`HF_ENDPOINT`）。也可以指定：

```bash
python scripts/download_models.py --source hf
python scripts/download_models.py --only embedding
```

模型默认保存到：

- `models/bge-base-zh-v1.5`
- `models/bge-reranker-base`

Unstructured 在解析时会用到一个小型英文 spaCy 模型。安装它（可选，但推荐）：

```bash
.venv\Scripts\python.exe scripts/setup_spacy.py
```

脚本会从官方地址或镜像下载 `en_core_web_sm`（约 12 MB）。如果网络不允许，应用会自动退化为轻量分句器，不影响中文文档解析。

### 3. 配置 API Key

```bash
copy .env.example .env
```

编辑 `.env`，至少填写一个：

```dotenv
QWEN_API_KEY=sk-你的千问Key
# 或者
DEEPSEEK_API_KEY=sk-你的DeepSeek Key
```

也支持把千问 Key 写成 `DASHSCOPE_API_KEY`。两家都填时，前端可以随时切换。

### 4. 启动

```bash
.venv\Scripts\python.exe run.py
```

或者 Windows 双击 `start.bat`（首次会自动安装依赖、下载模型并创建 `.env`）。

打开：

- 问答页：<http://127.0.0.1:8000/>
- 知识库：<http://127.0.0.1:8000/knowledge>
- API 文档：<http://127.0.0.1:8000/api/docs>

首次启动会在后台预热两个本地模型，页面右上角/侧边栏会显示加载状态。首次查询如果模型尚未加载完成，会等待模型加载，属于正常现象。

### 5. 体验

1. 进入“知识库文件”，把 `samples/` 下的示例 Markdown 拖进上传区。
2. 等状态变为“已就绪”（通常几秒到十几秒）。
3. 回到“知识问答”，问：
   - “差旅制度中的住宿标准是多少？”
   - “云舟平台知识库更新后多久生效？”
   - “出差补贴怎么计算？”

回答下方的引用 chip 可以打开原文片段，`[1]` 这样的角标也可以点击。

## 配置说明

所有配置都在 `.env` 中，常用项：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `QWEN_API_KEY` | 空 | 千问 / DashScope Key |
| `DASHSCOPE_API_KEY` | 空 | 千问 Key 的别名 |
| `QWEN_MODEL` | `qwen-plus` | 千问模型名 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek Key |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型名 |
| `DEFAULT_LLM` | `qwen` | 默认模型 |
| `EMBEDDING_MODEL` | `models/bge-base-zh-v1.5` | 本地路径或 HF 仓库 id |
| `RERANKER_MODEL` | `models/bge-reranker-base` | 本地路径或 HF 仓库 id |
| `EMBEDDING_DEVICE` | `auto` | `cpu` / `cuda` / `cuda:0` |
| `RETRIEVAL_TOP_K` | `12` | 向量召回数量 |
| `RERANKER_TOP_N` | `6` | 重排序后进入 Prompt 的数量 |
| `RERANK_ENABLED` | `true` | 关闭后跳过重排序 |
| `CHUNK_SIZE` | `420` | 分块字符数（小于 BGE 512 token 上限） |
| `CHUNK_OVERLAP` | `60` | 重叠字符数 |
| `EMBED_CONTEXT_LEVELS` | `3` | embedding 前缀中保留的最近章节层数 |
| `MAX_UPLOAD_MB` | `50` | 单文件上限 |
| `WARMUP_MODELS` | `true` | 启动后后台预热模型 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HF 镜像 |

`EMBEDDING_MODEL` / `RERANKER_MODEL` 写相对路径时，相对于项目根目录解析。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 模型、文档、向量库状态 |
| `GET` | `/api/documents` | 文件列表 |
| `POST` | `/api/documents` | 上传文件（multipart，字段名 `files`，可多个） |
| `DELETE` | `/api/documents/{id}` | 删除文件、向量和记录 |
| `POST` | `/api/documents/{id}/retry` | 重新解析失败文件 |
| `GET` | `/api/documents/{id}/download` | 下载原始文件 |
| `POST` | `/api/chat` | SSE 流式问答 |

`POST /api/chat` 请求体：

```json
{
  "message": "住宿标准是多少？",
  "history": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好，请问有什么可以帮你？"}
  ],
  "provider": "qwen",
  "top_k": 12,
  "rerank_top_n": 4
}
```

SSE 事件：

- `sources`：引用列表与检索统计
- `delta`：增量 token
- `done`：耗时
- `error`：可读的错误信息

## 文档支持

Unstructured 使用 `strategy="fast"`，支持：

`.pdf` `.docx` `.pptx` `.xlsx` `.txt` `.md` `.markdown` `.csv` `.html` `.htm`

- 文本型 PDF 可直接解析；扫描版 PDF 需要 OCR，本项目默认不包含 OCR 模型。
- PDF 解析依赖 `unstructured-inference`（已写入 `requirements.txt`）。在 Windows + Python 3.11 上，Unstructured 的 `pdf` extra 不会自动安装它，所以这里单独列出。
- 旧版 `.doc` / `.xls` 需要额外系统组件，未列入支持范围。
- 解析结果按 PDF 页码 / PPT 幻灯片聚合，再切分；每个 chunk 的 metadata 带文件名和页码，用于引用展示。
- 表格会尽量转换为 `列 | 列 | 列` 的文本，保留行列关系，提升表格问答准确率。
- 为避免 NLTK 在线下载，中文切分使用字符计数 + 正则断句，离线可用。

## 测试

```bash
.venv\Scripts\python.exe -m pytest
```

单元测试不需要 API Key，也不会加载大模型；覆盖文件登记、切分、Prompt、页面和错误处理。

### 环境与 Key 自检

```bash
# 依赖、模型路径、目录检查；--load-models 会实际跑一次向量和重排
.venv\Scripts\python.exe scripts/check_setup.py --load-models

# 真实调用一次千问 / DeepSeek，验证 Key、Base URL 和网络
.venv\Scripts\python.exe scripts/check_llm.py --provider qwen
.venv\Scripts\python.exe scripts/check_llm.py --provider deepseek
```

## 常见问题

**模型下载失败？**
项目默认走 ModelScope。也可以设置 `HF_ENDPOINT=https://hf-mirror.com` 并执行 `python scripts/download_models.py --source hf`。如果公司网络需要代理，请在启动前设置 `HTTP_PROXY` / `HTTPS_PROXY`。

**没有 GPU 可以跑吗？**
可以。`EMBEDDING_DEVICE=auto` 会自动选择 CPU。CPU 上首次加载模型约十几秒到几十秒，单次问答会增加几秒检索耗时。

**重排序模型太大，想先跑通？**
在 `.env` 中设置 `RERANK_ENABLED=false`，系统会直接使用向量相似度排序。正式使用建议开启。

**Chroma 数据在哪里？**
`data/chroma/`。文件原始副本在 `data/documents/`，文件清单在 `data/registry.json`。删除文件请通过页面操作，这样会同时清理向量。

**上传后一直“处理中”？**
刷新页面会看到最新状态；如果服务重启，未完成的任务会被标记为“失败”，点击重试即可。大文件首次向量化需要一些时间。

**API Key 会不会泄露？**
Key 只保存在本机 `.env`，后端不会通过接口返回；`.gitignore` 已排除 `.env`。本项目没有登录鉴权，默认只监听 `127.0.0.1`，不要直接暴露到公网。

**如何换成其他 OpenAI 兼容模型？**
修改 `.env` 中的 `QWEN_BASE_URL` / `QWEN_MODEL` 或 `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`。如果模型名和 Key 不是这两家，建议在 `app/services/llm.py` 中新增 provider。

## 说明

- 本项目面向单机 / 小团队使用，未实现用户体系、权限隔离和分布式任务队列。
- **数据外发提示**：BGE 向量化和重排序在本地完成；但问答时，检索到的文档片段会随请求发送给所选的 Qwen / DeepSeek 云端 API。请不要把不允许外发的文档放入知识库，或改用可私有化部署的 OpenAI 兼容模型。
- 多轮追问目前只把历史消息交给生成模型，**不会改写检索 query**；像“那经理呢？”这类指代型追问，召回效果可能下降。
- 上传的文档会保存在本地，请自行做好备份和敏感信息管理。
- 示例文档中的公司、电话、邮箱均为虚构，仅用于演示检索效果。