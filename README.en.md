[简体中文](README.md) | [English](README.en.md)

# Zhiku RAG

Zhiku is a Chinese-language knowledge-base app for document Q&A. Unstructured parses files, LlamaIndex orchestrates retrieval, local BGE models create embeddings and rerank passages, and Chroma persists the vectors. Qwen or DeepSeek streams answers through a lightweight FastAPI web interface that needs no Node.js build.

> Embedding and reranking run locally. Answer generation uses a configured cloud API and sends retrieved document passages to that provider. See [Data and limitations](#data-and-limitations) before uploading sensitive files.

## Features

- Streamed, multi-turn answers with clickable citations showing the source file, page (when available), and excerpt.
- Drag-and-drop uploads, background parsing, processing status, retry, original-file download, and deletion.
- Local `BAAI/bge-base-zh-v1.5` embeddings and `BAAI/bge-reranker-base` reranking, with persistent Chroma storage.
- Qwen and DeepSeek via OpenAI-compatible APIs, selectable in the web UI.
- A health endpoint reporting model state and document and vector counts.

## Quick start

Use **Python 3.11**. Allow several gigabytes for dependencies and downloaded models; 16 GB of RAM is recommended. CPU works, and `auto` selects CUDA when the installed PyTorch build detects a compatible GPU. Run the commands from the `RAG` directory.

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

Edit `.env` and set at least one API key:

```dotenv
QWEN_API_KEY=your-qwen-key
# Or use DASHSCOPE_API_KEY instead of QWEN_API_KEY.
DEEPSEEK_API_KEY=your-deepseek-key
```

Either provider is enough. If both are configured, you can switch between them in the UI. Set any custom model paths or download mirror in `.env` before downloading models. To improve Unstructured's element classification, optionally run `scripts/setup_spacy.py` with your virtual environment's Python; the app has a lightweight fallback when the model is absent.

Download the local models and start the server:

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

Open [Chat](http://127.0.0.1:8000/), [Knowledge base](http://127.0.0.1:8000/knowledge), or [API docs](http://127.0.0.1:8000/api/docs). On first startup, the two local models warm up in the background; an initial query may wait for them.

On Windows, `start.bat` is an alternative that creates the environment and `.env` if missing, installs dependencies, downloads models, and starts the app. After its first run, fill in `.env` and restart the server. `start.ps1` provides a PowerShell launcher.

### Try it

1. Upload either Markdown file from `samples/` on the Knowledge base page.
2. Wait until its status is “已就绪” (`ready` in the API).
3. Ask a question such as “差旅制度中的住宿标准是多少？” and open a citation below the answer.

The app's interface and answer prompt are currently in Chinese.

## How it works

```text
Upload -> Unstructured parsing -> section/table context -> character-based chunks
       -> local BGE embeddings -> persistent Chroma collection

Question -> Chroma top-K retrieval -> local BGE reranking -> cited context
         -> Qwen or DeepSeek -> SSE answer stream
```

The parser preserves heading hierarchy, table captions, and subtitles across page boundaries. Each chunk's metadata retains its full section path, table context, file name, and page number. The embedding text uses the document title, the most recent section levels, and table labels; `EMBED_CONTEXT_LEVELS` controls how many section levels are included. Defaults are 420 characters per chunk with 60-character overlap, 12 retrieval candidates, and 6 reranked passages.

## Configuration

Copy `.env.example` to `.env` before changing settings. Relative local model paths resolve from the project directory.

| Variable | Default | Purpose |
| --- | --- | --- |
| `QWEN_API_KEY` / `DASHSCOPE_API_KEY` | empty | Qwen/DashScope credentials |
| `QWEN_MODEL` | `qwen-plus` | Qwen model name |
| `QWEN_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Qwen endpoint |
| `DEEPSEEK_API_KEY` | empty | DeepSeek credentials |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek model name |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek endpoint |
| `DEFAULT_LLM` | `qwen` | Initially selected provider |
| `EMBEDDING_MODEL` | `models/bge-base-zh-v1.5` | Local embedding model path |
| `RERANKER_MODEL` | `models/bge-reranker-base` | Local reranker path |
| `EMBEDDING_DEVICE` / `RERANK_DEVICE` | `auto` | `auto`, `cpu`, or a CUDA device |
| `RETRIEVAL_TOP_K` / `RERANKER_TOP_N` | `12` / `6` | Retrieval and reranking limits |
| `RERANK_ENABLED` | `true` | Enable local reranking |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `420` / `60` | Character-based chunking |
| `EMBED_CONTEXT_LEVELS` | `3` | Recent heading levels in embedding text |
| `MAX_UPLOAD_MB` | `50` | Maximum size of one file |
| `WARMUP_MODELS` | `true` | Preload local models on startup |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Listening address and port |
| `HF_ENDPOINT` | `https://hf-mirror.com` | Hugging Face mirror used by the downloader |

The model downloader uses ModelScope first, then the configured Hugging Face endpoint. To select a source or one model explicitly:

```bash
python scripts/download_models.py --source hf
python scripts/download_models.py --only embedding
```

Use the virtual environment's Python in place of `python` if it is not active.

## Supported files and API

Supported uploads: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.txt`, `.md`, `.markdown`, `.csv`, `.html`, and `.htm`. Text-based PDFs are supported; scanned PDFs need OCR, which this project does not include. Legacy `.doc` and `.xls` files are outside the supported formats.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Model, document, and vector status |
| `GET` | `/api/documents` | List documents |
| `POST` | `/api/documents` | Upload one or more files (`multipart/form-data`, field `files`) |
| `DELETE` | `/api/documents/{id}` | Delete a document and its vectors |
| `POST` | `/api/documents/{id}/retry` | Retry failed parsing |
| `GET` | `/api/documents/{id}/download` | Download the original file |
| `POST` | `/api/chat` | Stream a RAG answer over SSE |

Example `/api/chat` JSON body (`provider`, `top_k`, and `rerank_top_n` are optional):

```json
{
  "message": "住宿标准是多少？",
  "history": [],
  "provider": "qwen",
  "top_k": 12,
  "rerank_top_n": 6
}
```

The SSE stream emits `sources` (citations and retrieval counts), `delta` (answer text), `done` (elapsed time), or `error` (readable error). Full request schemas are available at `/api/docs`.

## Project layout

```text
RAG/
├── app/api/           # Chat, document, and health endpoints
├── app/services/      # Parsing, embeddings, retrieval, reranking, ingestion
├── app/templates/     # Web pages
├── app/static/        # Frontend assets
├── data/              # Runtime documents, Chroma, registry, caches
├── models/            # Downloaded local models
├── samples/           # Sample documents
├── scripts/           # Model download and diagnostic helpers
├── tests/
├── .env.example
├── requirements.txt
├── run.py
└── README.md / README.en.md
```

## Checks and troubleshooting

```bash
python -m pytest
python scripts/check_setup.py --load-models
python scripts/check_llm.py --provider qwen
```

Run these with the virtual environment's Python. Tests do not need an API key or load the large models. `check_setup.py --load-models` actually loads both local models; `check_llm.py` makes a real provider request and needs a valid key. Use `--provider deepseek` to check DeepSeek.

- **Model download fails:** Try `python scripts/download_models.py --source hf`, or configure `HTTP_PROXY` / `HTTPS_PROXY` for your network.
- **No GPU:** `auto` falls back to CPU; the first model load and answers will take longer.
- **Reranker unavailable:** Run the model downloader or set `RERANK_ENABLED=false` in `.env` to use vector ranking temporarily.
- **Upload stays in processing:** Refresh the page. Interrupted jobs are marked failed after a server restart and can be retried.
- **Where is the data?** Originals are in `data/documents/`, vectors in `data/chroma/`, and the registry in `data/registry.json`. Use the UI or API for deletion so vectors are removed too.

## Data and limitations

- Embeddings, reranking, stored files, and the web UI are local. During chat, the selected Qwen or DeepSeek API receives retrieved document excerpts. Only upload documents that may be sent to that provider.
- The app has no login or per-user access control and listens on `127.0.0.1` by default. Do not expose it directly to an untrusted network.
- Conversation history informs answer generation but does not rewrite the retrieval query. Short follow-up questions can therefore retrieve weaker matches.
- Retrieval scores are useful for ranking, not calibrated answer probabilities. Scanned PDFs and complex layouts can parse poorly without OCR.
- Back up `data/` yourself. Sample company names and contact details are fictional. See [ISSUES.md](ISSUES.md) for known issues and validation gaps.
