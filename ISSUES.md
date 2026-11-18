# 本次 RAG 项目问题清单

复盘范围：`D:\workwork\RAG` 的代码、依赖安装、模型下载、文档解析、Chroma 读写、前后端链路和本次测试记录。

结论：核心链路已经跑通，但本次构建过程中确实出现过若干会直接影响正确性的问题。下面分为 **已修复**、**仍存在**、**验证缺口** 三部分。严重度定义：

- **P0**：会导致数据错误、功能不可用或启动失败
- **P1**：影响回答正确性、安全性或交付可用性
- **P2**：体验、可维护性、扩展性问题

## 一、已修复的问题

### P0-1 删除文档后，旧向量仍会被检索到

- **现象**：知识库页面显示删除成功，但问答引用里仍出现已删除的文件，Chroma 向量数量也没有归零。
- **根因**：LlamaIndex 的 Chroma adapter 会把顶层 metadata 的 `doc_id` 占用为自己的 `ref_doc_id`。代码用 `where={"doc_id": 业务ID}` 删除时匹配不到任何记录，而且异常被吞掉。
- **修复**：解析时额外写入 `kb_id`；删除时先按 `kb_id` 查出显式 ID，再 `delete(ids=...)`；删除失败不再假装成功，接口返回 503 并保留记录。
- **验证**：上传 → 查询 → 删除后 `/api/health` 的 `vectors=0`。
- **位置**：`app/services/parser.py`、`app/services/vector_store.py`、`app/services/ingestion.py`。

### P0-2 Windows + Python 3.11 下 PDF 完全无法解析

- **现象**：上传 PDF 后状态变为 failed，报 `No module named 'unstructured_inference'`。
- **根因**：Unstructured 的 `pdf` extra 在 Windows + Python 3.11 下不会自动安装 `unstructured-inference`，但 PDF partitioner 会无条件 import 它。
- **修复**：在 `requirements.txt` 显式加入 `unstructured-inference`；PDF 解析实测通过，页码进入引用。
- **位置**：`requirements.txt`。

### P1-3 启动时缓存目录初始化崩溃

- **现象**：`AttributeError: 'str' object has no attribute 'mkdir'`，服务无法启动。
- **根因**：缓存初始化把目录路径和普通环境变量值放在同一个字典里，统一调用了 `.mkdir()`。
- **修复**：目录路径和字符串环境变量分开处理。
- **位置**：`app/config.py`。

### P1-4 默认分块超过 BGE 的 512 token 上限

- **现象**：默认 `CHUNK_SIZE=700` 字，中文约等于 700 token；`bge-base-zh-v1.5` 最大长度 512，超出部分会被静默截断，块尾内容实际没有参与向量化。
- **验证**：BGE tokenizer 实测 700 字 = 702 token；调整后 420 字块最大约 380 token。
- **修复**：默认改为 `CHUNK_SIZE=420`、`CHUNK_OVERLAP=60`，并同步 `.env`、`.env.example`、README。
- **位置**：`app/config.py`。

### P1-5 Unstructured 首次解析时联网下载 spaCy 模型失败

- **现象**：第一次解析文档时报 `Remote end closed connection` / GitHub release 超时，解析失败。
- **根因**：Unstructured 0.27 在缺少 `en_core_web_sm` 时会从 GitHub 下载模型，网络不通时直接阻断解析。
- **修复**：增加 `scripts/setup_spacy.py`（官方源 + 两个镜像，20 秒超时）；解析器增加空白 spaCy 分句器 fallback，模型缺失时仍能解析中文。
- **位置**：`scripts/setup_spacy.py`、`app/services/parser.py`。

### P1-6 删除向量失败时静默删除文件记录

- **现象**：Chroma 暂时不可用时，页面显示删除成功，但旧向量还在，后续仍可能被召回。
- **修复**：向量删除失败时抛出错误，接口返回 503，保留文件记录供重试；新增两个单元测试覆盖“删除成功”和“向量失败”。
- **位置**：`app/services/ingestion.py`、`app/api/documents.py`。

### P1-7 前端在流式回答中清空对话，旧消息会“复活”

- **原因**：清空时只清空了数组和 DOM，但未取消的 SSE 回调仍持有 assistant 对象，之后又把它追加回列表。
- **修复**：`updateMessage` 先检查消息是否还在 `state.messages` 中；清空时同时 abort 当前请求。
- **位置**：`app/static/js/chat.js`。

### P1-8 venv 重命名导致大量命令行入口失效

- **原因**：开发时先在 `.venv2` 安装，后重命名为 `.venv`，`Scripts/*.exe` 内的 shebang 仍指向 `.venv2`，执行时无输出或直接退出。
- **修复**：重新生成 `pip.exe`、`uvicorn.exe`；激活脚本和 `pyvenv.cfg` 中的路径已改。
- **仍残留**：其余 59 个 `.exe` 入口仍可能指向旧路径；项目文档统一使用 `python -m ...`，不依赖这些入口。

### P1-9 start.bat 在中文 Windows 上逐行丢字符，无法启动

- **现象**：双击后出现 `'p' 不是内部或外部命令`、`'local'`、`'/d'`、`'not'`、`'cho'` 等错误，随后误报“Failed to create .venv”。
- **根因**：`start.bat` 被写成 **UTF-8 + 纯 LF 换行**，且脚本内有 `chcp 65001`。`cmd.exe` 在切换代码页后重新读取批处理，行首字符被吞掉，`if`、`setlocal`、`cd`、`echo` 等命令被截断。
- **修复**：改为 **ASCII-only + CRLF**，移除 `chcp 65001`；增加 `py`/`python` 回退、依赖缺失检测、双模型检查。
- **验证**：`cmd /c start.bat` 实测可启动服务并返回 `/api/health` 200。
- **位置**：`start.bat`。

### P1-10 跨页表格只召回第一页，后续季节页丢失

- **现象**：查询“西南地区四季食谱”只召回第 52 页春季内容，53–56 页的夏/秋/冬季食谱没有进入上下文。
- **根因**：
  - 按页分组后，53–56 页的 chunk 只有“夏季食谱 1”等子标题，没有“西南地区”“表 3.6”等章节锚点；
  - 默认 `RERANKER_TOP_N=4`，即使夏季页排第 5 也会被截掉；
  - 第 52 页有多个 chunk 占据靠前名次。
- **修复**：
  - 解析器按元素顺序维护多级章节栈，跨页继承章节标题、表格标题和季节子表；
  - metadata 保存 `section_path` / `full_path` / `table_caption` / `table_subtitle`；
  - embedding 只拼“文档标题 + 最近 3 级章节 + 表格标题/季节”；
  - `RERANKER_TOP_N` 默认调为 6，并拆分 metadata-aware 切分，避免完整路径挤占 420 字预算。
- **验证**：重索引后 240 chunks；默认 Top-6 下“西南地区四季食谱”召回页 `52,52,28,55,53,54`，春季/冬季/夏季/秋季均已进入结果；`夏季/秋季/冬季` 查询也能命中对应页。
- **位置**：`app/services/parser.py`、`app/services/rag.py`、`app/config.py`。

### P2-10 其他已修正的小问题

- 关闭重排序时仍对向量分数做 sigmoid，导致“相关度”语义错误。
- 引用下载使用 `doc_id`，在 Chroma adapter 改写 metadata 后可能 404；现在优先使用 `kb_id`。
- 最后一层 SSE 异常处理会把内部异常文本直接返回浏览器，存在信息泄漏风险；现在只返回通用错误。
- 模型下载脚本首次从 ModelScope 同时下载 `safetensors` 和 `pytorch_model.bin`，占 3.2 GB；现在自动清理重复权重，当前约 1.1 GB。
- `start.bat` 只检查 embedding 模型，不检查 reranker；现在两个模型都检查。
- README 原先写的分块参数与实际不一致，已同步。

## 二、仍存在的问题 / 风险

### P1-1 多轮追问没有检索 query 改写

当前只把历史消息交给生成模型，检索仍然使用用户最后一句话。用户问“那经理呢？”时，向量检索可能召回不到“经理住宿标准”的相关段落。

**建议**：在检索前用 LLM 把“历史 + 当前问题”改写成独立问题，或至少把上一轮问题拼接到检索 query。

### P1-2 没有最低相关度阈值

重排序后固定保留 Top-N，低分片段也会进入 Prompt。知识库没有答案时，模型可能被弱相关内容误导。

**建议**：对 rerank 分数设置阈值，或至少把低分来源标记为“低置信度”。

### P1-3 没有登录和权限控制

上传、删除、问答、原文下载都没有鉴权；默认只监听 `127.0.0.1`，但不能直接暴露到公网。如果修改 `HOST=0.0.0.0`，任何能访问端口的人都可以删除知识库。

### P1-4 文档内容会发送到云端 LLM

本地只负责向量和重排序；问答时检索到的原文片段会发给 Qwen / DeepSeek。README 已补充隐私提示，但产品层面仍需要用户自行确认数据合规。

### P1-5 依赖版本没有锁定

`requirements.txt` 只有下限，没有锁文件。当前组合（LlamaIndex 0.14.26、Chroma 1.5.9、Unstructured 0.27.37、Transformers 5.23）实测可用，但未来重新安装可能拉到不兼容的大版本。

**建议**：生成并提交 `requirements.lock`，或在 CI 中固定并验证版本。

### P1-6 Registry 与 Chroma 可能不一致

- `registry.json` 损坏时，`DocumentRegistry._load` 会静默从空列表开始，Chroma 里已有向量会变成“孤儿”。
- 文件删除失败时，记录仍会被移除，可能留下 `data/documents` 里的孤儿文件。
- 没有“重建索引 / 清理孤儿向量”的管理命令。

### P2-1 上传校验偏弱

只按扩展名校验，没有检查 MIME / 文件头；没有内容 hash 去重；没有单次请求总大小限制。重复上传同一文件会产生重复分块和重复引用。

### P2-2 后台上传任务与并发限制

使用 FastAPI `BackgroundTasks` + 进程内全局锁：

- 一个大 PDF 会阻塞后续上传和删除。
- 服务重启后处理中任务会被标记失败，不会自动续跑。
- 多 worker 部署时，registry 和 Chroma 没有跨进程协调。
- 没有取消正在解析任务的入口。

### P2-3 SSE 没有心跳和断连取消

客户端断开后，后端生成器不一定会立即停止，LLM 请求可能继续消耗 token；部分反向代理可能因无数据超时而断开。

### P2-4 相关度百分比不是校准概率

页面显示的“相关度 70%”是对 reranker logit 做 sigmoid 的结果，只适合做相对排序，不应理解为“70% 正确概率”。

### P2-5 多轮历史 token 预算偏乐观

服务端保留 6 轮（12 条）消息，每条截断 2000 字，再加 6000 字资料；接近 32k 上下文上限，长对话可能触发模型截断或报错。

### P2-6 Markdown 表格不能渲染

前端 `renderMarkdown` 支持标题、列表、代码、粗体、引用，但**不支持 Markdown 表格**；如果模型输出表格，页面会显示原始 `|` 文本。

### P2-7 扫描 PDF / 复杂版面能力有限

使用 Unstructured `strategy="fast"`，没有 OCR；扫描件、双栏 PDF、复杂表格的抽取质量有限。README 已说明，但这是能力边界，不是 bug。

### P2-8 其他 UI / 运维缺口

- 文件列表没有分页，知识库很大时页面会变慢。
- 没有文件预览、重命名、替换、批量删除。
- 没有 RAG 评测集，回答质量无法量化。
- 59 个 venv 命令行入口仍可能指向 `.venv2`；请统一用 `.venv\Scripts\python.exe -m ...`。

## 三、本次验证的缺口

1. **真实 Qwen / DeepSeek 调用未执行**：没有拿到真实 Key，只用本地 OpenAI 兼容 mock 验证了流式协议和 RAG 链路；`scripts/check_llm.py` 已提供，填入 Key 后可自检。
2. **真实浏览器视觉未验证**：当前环境无法启动 headless Chrome/Edge（沙箱禁止浏览器命名管道），只验证了 HTML 返回 200、CSS/JS 加载和 JS 语法。
3. **没有并发/压力测试**：多用户同时上传、删除、问答时的锁竞争和内存占用未测。
4. **没有 RAG 质量评测**：未计算 Recall@K、MRR、答案忠实度等指标，只用示例文档做了人工抽查。

## 四、建议修复优先级

1. 多轮 query 改写 + 相关度阈值（直接影响问答质量）。
2. 固定依赖版本，补一个可重复安装的 lock 文件。
3. 如果可能暴露到局域网/公网，先加登录鉴权。
4. 增加“清理孤儿向量 / 重建 registry”的维护命令。
5. 上传增加 MIME、hash 去重、单次总大小限制。
6. 补真实 Chroma/API 集成测试和浏览器端到端测试。