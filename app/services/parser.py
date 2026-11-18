"""Unstructured-based document parsing and LlamaIndex node splitting.

The parser keeps a lightweight document outline while walking Unstructured
elements in reading order. Headings are inherited across pages, so a table
that continues on the next page still knows which chapter/table it belongs to.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".html",
    ".htm",
}

_SKIP_CATEGORIES = {"PageBreak", "Header", "Footer", "PageNumber"}

_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])\s*|(?<=[.!?])\s+|\n+")

_IGNORED_HEADING_LABELS = {
    "早餐",
    "中餐",
    "午餐",
    "晚餐",
    "加餐",
    "油、盐",
    "油盐",
    "备注",
    "注",
    "合计",
    "小计",
    "食物名称",
    "能量",
    "重量",
}

# (pattern, level). Level is absolute-ish; Arabic numeric headings are
# adjusted relative to their dot depth.
_HEADING_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"^第[一二三四五六七八九十百千万零〇两]+[章篇部分]"), 1),
    (re.compile(r"^第[一二三四五六七八九十百千万零〇两]+[节]"), 2),
    (re.compile(r"^[一二三四五六七八九十百千万零〇两]+、"), 2),
    (re.compile(r"^[（(][一二三四五六七八九十百千万零〇两]+[）)]"), 3),
    (re.compile(r"^[（(]\d+[）)]"), 4),
]

_TABLE_CAPTION_RE = re.compile(r"^(?:表|Table)\s*\d+(?:[.．]\d+)*", re.IGNORECASE)
_CONTINUED_TABLE_RE = re.compile(r"^续\s*表", re.IGNORECASE)
_TABLE_SUBTITLE_RE = re.compile(r"^(?:春|夏|秋|冬)季食谱\s*\d*")
_SEASON_SUBTITLE_RE = re.compile(r"(?:春|夏|秋|冬)季食谱\s*\d+")
_ARABIC_HEADING_RE = re.compile(r"^(\d+(?:[.．]\d+){0,3})[.、．\s]\s*")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")

_NLP_READY = False


@dataclass
class _Section:
    id: str
    title: str
    level: int
    parent: "_Section | None"
    path: list[str]
    path_ids: list[str]


@dataclass
class _Table:
    id: str
    caption: str
    subtitle: str | None = None


@dataclass
class _Block:
    page: int
    section: _Section | None
    table: _Table | None
    texts: list[str] = field(default_factory=list)


def split_sentences(text: str) -> list[str]:
    """Cheap, language-agnostic sentence splitter (avoids NLTK downloads)."""
    parts = [part.strip() for part in _SENTENCE_BOUNDARY.split(text or "")]
    return [part for part in parts if part]


def _element_page(element) -> int | None:
    metadata = getattr(element, "metadata", None)
    if metadata is None:
        return None
    for attr in ("page_number", "slide_number"):
        value = getattr(metadata, attr, None)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _element_text(element) -> str:
    """Preserve table row/column structure for better LLM answers."""
    category = getattr(element, "category", "") or ""
    if category == "Table":
        metadata = getattr(element, "metadata", None)
        html = getattr(metadata, "text_as_html", None) if metadata else None
        if html:
            try:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html, "html.parser")
                rows = []
                for tr in soup.find_all("tr"):
                    cells = [
                        cell.get_text(" ", strip=True)
                        for cell in tr.find_all(["th", "td"])
                    ]
                    if cells:
                        rows.append(" | ".join(cells))
                if rows:
                    header_cols = len(rows[0].split(" | "))
                    if len(rows) > 1:
                        rows.insert(1, " | ".join(["---"] * header_cols))
                    return "\n".join(rows)
            except Exception:
                logger.debug("Could not convert table HTML to text", exc_info=True)
    return str(element)


def _ensure_unstructured_nlp() -> None:
    """Avoid Unstructured's runtime GitHub download on first use.

    Unstructured 0.27 lazily installs the English ``en_core_web_sm`` spaCy
    model from GitHub. That is fragile behind firewalls. If the model is not
    installed we fall back to a blank English pipeline with a sentencizer:
    tokenization and sentence boundaries still work, which is all this
    project needs for Chinese/mixed documents.
    """
    global _NLP_READY
    if _NLP_READY:
        return
    try:
        import spacy
        from unstructured.nlp import tokenize
    except Exception:
        _NLP_READY = True
        return

    try:
        spacy.load("en_core_web_sm")
        _NLP_READY = True
        return
    except Exception:
        pass

    nlp = spacy.blank("en")
    if "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer")
    tokenize._load_spacy_model = lambda: nlp  # type: ignore[attr-defined]
    tokenize._get_nlp.cache_clear()  # type: ignore[attr-defined]
    _NLP_READY = True
    logger.warning(
        "en_core_web_sm 未安装，Unstructured 使用轻量英文分句器（不影响中文解析）。"
    )


def _document_title(display_name: str, elements: list) -> str:
    """Prefer a real title on the first page, fall back to the filename."""
    stem = Path(display_name).stem.strip() or display_name
    for element in elements[:8]:
        category = getattr(element, "category", "") or ""
        text = _element_text(element).strip()
        if (
            category in {"Title", "SectionHeader"}
            and 4 <= len(text) <= 60
            and not _is_table_caption(text)
            and not _has_explicit_heading_pattern(text)
            and not _looks_like_table_row(text)
        ):
            return text
    return stem


def _has_explicit_heading_pattern(text: str) -> bool:
    if any(pattern.match(text) for pattern, _ in _HEADING_PATTERNS):
        return True
    match = _ARABIC_HEADING_RE.match(text)
    return bool(match and (match.group(1).count(".") or match.group(1).count("．")))


def _is_table_caption(text: str) -> bool:
    return bool(_TABLE_CAPTION_RE.match(text) or _CONTINUED_TABLE_RE.match(text))


def _is_table_subtitle(text: str) -> bool:
    return bool(_TABLE_SUBTITLE_RE.match(text))


def _looks_like_table_row(text: str) -> bool:
    """Avoid treating short table cells/notes as section headings."""
    if len(text) > 80:
        return False
    if text in _IGNORED_HEADING_LABELS:
        return True
    if text.startswith(("注：", "注:", "注 ", "*", "2.*", "全天总用量")):
        return True
    if text.endswith(("。", "；", ";", "，", ",")):
        return True
    if _PAGE_NUMBER_RE.match(text):
        return True
    return False


def _heading_level(
    text: str,
    category: str,
    in_table: bool,
    allow_style_headings: bool,
) -> int | None:
    """Return a heading level, 0 for a style-only heading, or None.

    Unstructured's fast PDF output marks many table cells and wrapped
    paragraph lines as ``Title``, so category alone is not a reliable heading
    signal. Explicit numbering wins; style-only titles are accepted only for
    formats where Unstructured has real style information.
    """
    if not text or len(text) > 80:
        return None
    if _is_table_caption(text) or _is_table_subtitle(text):
        return None
    if _looks_like_table_row(text):
        return None

    for pattern, level in _HEADING_PATTERNS:
        if pattern.match(text):
            return level

    if not allow_style_headings:
        return None

    match = _ARABIC_HEADING_RE.match(text)
    if match and category in {"Title", "SectionHeader"}:
        depth = match.group(1).replace("．", ".").count(".")
        return min(5, 3 + depth)

    if category in {"Title", "SectionHeader"} and not in_table:
        # Unnumbered title, e.g. a DOCX Heading 1. Attach below the current
        # section rather than guessing an absolute level.
        return 0
    return None


def _table_id(caption: str, counter: int) -> str:
    match = re.search(r"(\d+(?:[.．]\d+)*)", caption)
    if match:
        return "table-" + match.group(1).replace("．", ".")
    return f"table-{counter}"


def _split_table_caption(text: str) -> tuple[str, str | None]:
    """Separate "表 3.6 ..." from a season subtitle if present."""
    match = _SEASON_SUBTITLE_RE.search(text)
    if not match:
        return text, None
    base = text[: match.start()].strip(" ：:，,")
    return (base or text), match.group(0)


def _block_to_document(block: _Block, doc_id: str, doc_title: str, display_name: str, file_type: str) -> Document:
    section = block.section
    section_titles = section.path if section else []
    section_ids = section.path_ids if section else []

    section_path = " > ".join([doc_title, *section_titles])
    section_path_ids = " > ".join([doc_id, *section_ids])
    full_parts = [doc_title, *section_titles]
    table_caption = block.table.caption if block.table else ""
    table_subtitle = block.table.subtitle if block.table else ""
    if table_caption:
        full_parts.append(table_caption)
    if table_subtitle and table_subtitle not in table_caption:
        full_parts.append(table_subtitle)

    metadata = {
        "doc_id": doc_id,
        "kb_id": doc_id,
        "doc_title": doc_title,
        "file_name": display_name,
        "file_type": file_type,
        "section_path": section_path,
        "section_path_ids": section_path_ids,
        "section_level": section.level if section else 0,
        "full_path": " > ".join(full_parts),
        "table_id": block.table.id if block.table else "",
        "table_caption": table_caption,
        "table_subtitle": table_subtitle,
    }
    if block.page:
        metadata["page"] = block.page

    text = "\n\n".join(part for part in block.texts if part).strip()
    return Document(text=text, metadata=metadata)


def parse_file(path: Path, doc_id: str, display_name: str) -> list[Document]:
    """Parse one file into page/context blocks with a propagated outline.

    Tables that continue across pages inherit the current section and table
    caption. The returned Documents carry a full path in metadata; the
    embedding-only prefix is assembled later in :func:`build_nodes`.
    """
    _ensure_unstructured_nlp()
    from unstructured.partition.auto import partition

    file_type = path.suffix.lower().lstrip(".")
    try:
        partition_kwargs = {
            "filename": str(path),
            "metadata_filename": display_name,
            "strategy": "fast",
            "include_page_breaks": True,
        }
        if path.suffix.lower() == ".pdf":
            partition_kwargs["languages"] = ["chi_sim", "eng"]
        elements = list(partition(**partition_kwargs))
    except Exception as exc:
        logger.exception("Unstructured failed to parse %s", path)
        raise RuntimeError(f"Unstructured 解析失败：{exc}") from exc

    doc_title = _document_title(display_name, elements)
    allow_style_headings = path.suffix.lower() in {
        ".docx",
        ".md",
        ".markdown",
        ".html",
        ".htm",
        ".pptx",
        ".txt",
    }
    documents: list[Document] = []
    section_stack: list[_Section] = []
    section_counter = 0
    table_counter = 0
    current_table: _Table | None = None
    current_page = 0
    block: _Block | None = None
    title_consumed = False

    def flush() -> None:
        nonlocal block
        if block is not None and block.texts:
            documents.append(
                _block_to_document(block, doc_id, doc_title, display_name, file_type)
            )
        block = None

    def new_block(page: int) -> _Block:
        nonlocal block
        block = _Block(
            page=page,
            section=section_stack[-1] if section_stack else None,
            table=current_table,
        )
        return block

    for element in elements:
        page = _element_page(element) or current_page or 1
        if page != current_page:
            flush()
            current_page = page

        category = getattr(element, "category", "") or ""
        if category in _SKIP_CATEGORIES:
            if category == "PageBreak":
                flush()
            continue

        text = _element_text(element).strip()
        if not text:
            continue
        if category == "UncategorizedText" and _PAGE_NUMBER_RE.match(text):
            continue

        # The document title itself should not become a second-level heading.
        if (
            not title_consumed
            and not section_stack
            and current_table is None
            and text == doc_title
        ):
            title_consumed = True
            new_block(page).texts.append(text)
            continue

        # A table caption starts a new table context.
        if _is_table_caption(text):
            flush()
            table_counter += 1
            caption, subtitle = _split_table_caption(text)
            current_table = _Table(
                id=_table_id(caption, table_counter),
                caption=caption,
                subtitle=subtitle,
            )
            new_block(page).texts.append(text)
            continue

        # "夏季食谱 1" etc. changes the current sub-table, not the chapter.
        subtitle_match = _TABLE_SUBTITLE_RE.match(text)
        if subtitle_match and current_table is not None:
            flush()
            current_table.subtitle = subtitle_match.group(0)
            new_block(page).texts.append(text)
            continue

        level = _heading_level(
            text,
            category,
            current_table is not None,
            allow_style_headings,
        )
        if level is not None:
            flush()
            if level == 0:
                level = (section_stack[-1].level + 1) if section_stack else 2
            while section_stack and section_stack[-1].level >= level:
                section_stack.pop()
            parent = section_stack[-1] if section_stack else None
            section_counter += 1
            section = _Section(
                id=f"s{section_counter}",
                title=text,
                level=level,
                parent=parent,
                path=(parent.path if parent else []) + [text],
                path_ids=(parent.path_ids if parent else []) + [f"s{section_counter}"],
            )
            section_stack.append(section)
            current_table = None
            new_block(page).texts.append(text)
            continue

        if block is None or block.page != page:
            if block is not None:
                flush()
            new_block(page)
        block.texts.append(text)

    flush()
    if not documents:
        raise RuntimeError("未能从文件中提取到可用文本（可能是扫描件或空文件）。")
    return documents


def _build_embed_context(metadata: dict) -> str:
    """Build the short prefix used only for embedding.

    Full hierarchy stays in metadata. The embedding prefix deliberately keeps
    only the document title plus the last N section levels (default 3) and the
    current table caption/subtitle, to avoid diluting the vector.
    """
    doc_title = str(metadata.get("doc_title") or "").strip()
    if not doc_title:
        file_name = str(metadata.get("file_name") or "未命名文档")
        doc_title = Path(file_name).stem

    section_path = str(metadata.get("section_path") or "")
    parts = [part.strip() for part in section_path.split(" > ") if part.strip()]
    # section_path starts with the document title; only recent headings go in.
    recent = parts[1:][-max(1, settings.embed_context_levels) :]

    lines = [f"文档：{doc_title}"]
    if recent:
        lines.append("章节：" + " > ".join(recent))

    table_caption = str(metadata.get("table_caption") or "").strip()
    table_subtitle = str(metadata.get("table_subtitle") or "").strip()
    if table_caption:
        table_line = "表格：" + table_caption
        if table_subtitle and table_subtitle not in table_caption:
            table_line += " / " + table_subtitle
        lines.append(table_line)
    return "\n".join(lines)


def build_nodes(documents: list[Document], doc_id: str) -> list:
    splitter = SentenceSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        paragraph_separator="\n\n",
        tokenizer=list,  # count characters; robust for Chinese and offline
        chunking_tokenizer_fn=split_sentences,
        include_metadata=False,  # full path stays in metadata, not chunk text
    )
    clean_nodes = []
    index = 0
    for document in documents:
        if not document.text.strip():
            continue
        source_metadata = dict(document.metadata or {})
        # Split with an empty metadata dict: metadata-aware splitting would
        # otherwise subtract the full path from the 420-character budget.
        temp_document = Document(text=document.text)
        split_nodes = splitter.get_nodes_from_documents([temp_document])
        for node in split_nodes:
            text = node.get_content().strip()
            if not text:
                continue

            metadata = dict(source_metadata)
            metadata["doc_id"] = doc_id
            metadata["kb_id"] = doc_id
            metadata["chunk_index"] = index
            metadata["embed_context"] = _build_embed_context(metadata)

            # Chroma only accepts scalar metadata values.
            node.metadata = {
                key: value
                for key, value in metadata.items()
                if isinstance(value, (str, int, float, bool)) and value is not None
            }
            # Only the short embed_context participates in the embedding. The
            # full path and all other fields remain available as metadata.
            node.metadata_template = "{value}"
            node.excluded_embed_metadata_keys = [
                key for key in node.metadata if key != "embed_context"
            ]
            node.excluded_llm_metadata_keys = list(node.metadata.keys())
            # Keep all chunks from one uploaded file under one source document.
            node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(
                node_id=doc_id
            )
            node.id_ = f"{doc_id}:{index}"
            clean_nodes.append(node)
            index += 1
    return clean_nodes