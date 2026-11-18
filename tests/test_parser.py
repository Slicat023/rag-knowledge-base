from __future__ import annotations

from llama_index.core import Document
from llama_index.core.schema import MetadataMode

from app.services.parser import _heading_level, build_nodes, split_sentences


def test_split_sentences_handles_chinese():
    parts = split_sentences("第一句话。第二句话！第三句话？")
    assert parts == ["第一句话。", "第二句话！", "第三句话？"]


def test_heading_level_heuristics():
    assert _heading_level("六、西南地区", "Title", False, False) == 2
    assert _heading_level("（一）一般人群", "Title", False, True) == 3
    assert _heading_level("1.1 总则", "Title", False, True) == 4
    assert _heading_level("早餐", "Title", True, False) is None
    assert _heading_level("夏季食谱 1", "Title", False, False) is None
    assert _heading_level("西南地区居民主要以大米", "Title", False, False) is None


def test_embed_context_uses_recent_sections_and_full_metadata():
    docs = [
        Document(
            text="夏季食谱正文",
            metadata={
                "doc_id": "doc-2",
                "kb_id": "doc-2",
                "doc_title": "食养指南",
                "file_name": "食养指南.pdf",
                "file_type": "pdf",
                "section_path": "食养指南 > 一级 > 二级 > 三级 > 四级",
                "section_path_ids": "doc-2 > s1 > s2 > s3 > s4",
                "section_level": 5,
                "full_path": "食养指南 > 一级 > 二级 > 三级 > 四级 > 表 3.6 > 夏季食谱",
                "table_caption": "表 3.6 西南地区四季食谱示例",
                "table_subtitle": "夏季食谱 1",
                "page": 53,
            },
        )
    ]
    node = build_nodes(docs, "doc-2")[0]
    assert node.metadata["full_path"].startswith("食养指南 > 一级")
    embed_text = node.get_content(MetadataMode.EMBED)
    assert "文档：食养指南" in embed_text
    assert "二级 > 三级 > 四级" in embed_text
    assert "一级 > 二级" not in embed_text
    assert "表 3.6 西南地区四季食谱示例 / 夏季食谱 1" in embed_text
    assert node.get_content(MetadataMode.NONE) == "夏季食谱正文"


def test_build_nodes_metadata_and_ids():
    docs = [
        Document(
            text=("云舟平台支持知识库问答。" * 40) + "\n\n" + ("部署时需要配置向量数据库。" * 40),
            metadata={
                "doc_id": "doc-1",
                "file_name": "手册.md",
                "file_type": "md",
                "page": 1,
            },
        )
    ]
    nodes = build_nodes(docs, "doc-1")
    assert nodes
    assert all(node.metadata["doc_id"] == "doc-1" for node in nodes)
    assert all(node.metadata["kb_id"] == "doc-1" for node in nodes)
    assert all(node.node_id.startswith("doc-1:") for node in nodes)
    assert all(isinstance(node.metadata["chunk_index"], int) for node in nodes)
    assert all(node.get_content().strip() for node in nodes)
    # Chroma metadata must remain scalar.
    for node in nodes:
        assert all(isinstance(value, (str, int, float, bool)) for value in node.metadata.values())