# tests/test_chunker.py
# 职责：测试 Chunker 的切块逻辑

import pytest
from rag.chunker import Chunker, TextChunk


@pytest.fixture
def chunker() -> Chunker:
    """默认切块器：每块 300 字，重叠 50 字"""
    return Chunker(chunk_size=300, overlap=50)


# ═══════════════════════════════════════════════
# 基本切块测试
# ═══════════════════════════════════════════════

class TestChunkText:
    """chunk_text 核心功能测试"""

    def test_empty_text_returns_empty(self, chunker: Chunker):
        """空文本应该返回空列表"""
        assert chunker.chunk_text("", {}) == []
        assert chunker.chunk_text("  ", {}) == []
        assert chunker.chunk_text("\n\n", {}) == []

    def test_short_text_one_chunk(self, chunker: Chunker):
        """短文（小于 chunk_size）应该只切出一块"""
        text = "Hello World"
        chunks = chunker.chunk_text(text, {"source": "test"})
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].metadata["source"] == "test"

    def test_text_split_by_headers(self, chunker: Chunker):
        """按 ## 标题切分"""
        text = """## 标题一
内容区块A的内容区块A的内容区块A的内容区块A

## 标题二
内容区块B的内容区块B的内容区块B的内容区块B

## 标题三
内容区块C的内容区块C的内容区块C的内容区块C"""
        chunks = chunker.chunk_text(text, {"source": "test"})
        assert len(chunks) == 3
        assert "内容区块A" in chunks[0].text
        assert "内容区块A" in chunks[0].text
        assert chunks[0].metadata["header"] == "## 标题一"

    def test_text_with_three_level_headers(self, chunker: Chunker):
        """### 三级标题也应该被识别"""
        text = """### 三级标题
三级内容三级内容三级内容

### 另一个三级标题
另一个三级内容"""
        chunks = chunker.chunk_text(text, {"source": "test"})
        assert len(chunks) == 2
        assert chunks[0].metadata["header"] == "### 三级标题"
        assert chunks[1].metadata["header"] == "### 另一个三级标题"

    def test_text_without_headers(self, chunker: Chunker):
        """没有标题的文本应该作为一整块"""
        text = "这是一段没有标题的普通文本。"
        chunks = chunker.chunk_text(text, {"source": "test"})
        assert len(chunks) == 1
        assert chunks[0].text == text

    def test_content_between_headers_correct(self, chunker: Chunker):
        """每个标题下的内容应该正确对应中间的文本"""
        text = """## 标题A
内容A

## 标题B
内容B"""
        chunks = chunker.chunk_text(text, {"source": "test"})
        assert len(chunks) == 2
        assert "内容A" in chunks[0].text
        assert "内容B" not in chunks[0].text
        assert "内容B" in chunks[1].text
        assert "内容A" not in chunks[1].text

    def test_metadata_carried_through(self, chunker: Chunker):
        """每个块都应该保留传入的 metadata"""
        text = """## 标题一
内容

## 标题二
内容"""
        meta = {"source": "notes.md", "topic": "java"}
        chunks = chunker.chunk_text(text, meta)
        for chunk in chunks:
            assert chunk.metadata["source"] == "notes.md"
            assert chunk.metadata["topic"] == "java"
            assert "header" in chunk.metadata


# ═══════════════════════════════════════════════
# 长文本切块测试
# ═══════════════════════════════════════════════

class TestLongText:
    """长文本的细分逻辑"""

    def test_long_section_split_by_paragraphs(self, chunker: Chunker):
        """超过 chunk_size 的章节应该按段落进一步切分"""
        text = "## 超长章节\n" + ("这是第一段。" * 80) + "\n\n" + ("这是第二段。" * 80)
        chunks = chunker.chunk_text(text, {"source": "test"})
        # 应该切成多块
        assert len(chunks) > 1

    def test_each_chunk_within_size_limit(self, chunker: Chunker):
        """每个块的长度不应该超过 chunk_size 的 2 倍（标题切分有 1.5 倍缓冲）"""
        text = "## 标题\n" + "内容内容。" * 200  # 约 1000 字
        chunks = chunker.chunk_text(text, {"source": "test"})
        for chunk in chunks:
            assert len(chunk.text) <= 600  # chunk_size * 2

    def test_fixed_length_splitting(self, chunker: Chunker):
        """超长无格式文本应该按固定长度切块"""
        text = "ABCDEFGHIJ" * 100  # 1000 字符
        chunks = chunker._split_fixed_length(text, {"source": "test"})
        # 每块最多 300 字，1000 字应该至少有 3 块
        assert len(chunks) >= 3

    def test_fixed_length_each_chunk_bound(self, chunker: Chunker):
        """固定长度切的块不应该超过 chunk_size"""
        text = "X" * 1000
        chunks = chunker._split_fixed_length(text, {"source": "test"})
        for chunk in chunks:
            assert len(chunk.text) <= 300


# ═══════════════════════════════════════════════
# 重叠切块测试
# ═══════════════════════════════════════════════

class TestOverlap:
    """相邻块之间的重叠"""

    def test_fixed_length_has_overlap(self, chunker: Chunker):
        """固定长度切块应该有重叠"""
        text = ("1234567890" * 40)  # 400 字
        chunks = chunker._split_fixed_length(text, {"source": "test"})
        if len(chunks) >= 2:
            # 相邻块应该有重叠内容
            overlap_text = chunks[-2].text[-50:]  # 前一块的后 50 字
            assert overlap_text in chunks[-1].text  # 在后一块中出现

    def test_overlap_size_matches_config(self, chunker: Chunker):
        """重叠字数应该等于配置的 overlap"""
        assert chunker.overlap == 50

    def test_no_overlap_when_only_one_chunk(self):
        """只有一个块时不需要重叠"""
        c = Chunker(chunk_size=500, overlap=50)
        text = "短文本"
        chunks = c.chunk_text(text, {"source": "test"})
        assert len(chunks) == 1


# ═══════════════════════════════════════════════
# 文件读取测试
# ═══════════════════════════════════════════════

class TestChunkFile:
    """chunk_file 从文件读取并切块"""

    def test_chunk_file_returns_chunks(self, chunker: Chunker, tmp_path):
        """读取一个临时 .md 文件并切块"""
        file_path = tmp_path / "test.md"
        file_path.write_text("## 第一章\n内容\n## 第二章\n更多内容", encoding="utf-8")
        chunks = chunker.chunk_file(str(file_path))
        assert len(chunks) == 2
        assert chunks[0].metadata["source"] == "test.md"

    def test_chunk_file_metadata(self, chunker: Chunker, tmp_path):
        """chunk_file 应该自动生成 source/file_path/topic 元数据"""
        file_path = tmp_path / "java" / "notes.md"
        file_path.parent.mkdir()
        file_path.write_text("## 标题\n内容", encoding="utf-8")
        chunks = chunker.chunk_file(str(file_path))
        assert chunks[0].metadata["source"] == "notes.md"
        assert chunks[0].metadata["topic"] == "java"
        assert "file_path" in chunks[0].metadata

    def test_chunk_file_invalid_encoding(self, chunker: Chunker, tmp_path):
        """非 UTF-8 文件不应该崩溃"""
        file_path = tmp_path / "binary.dat"
        file_path.write_bytes(b"\x80\x81\x82")
        chunks = chunker.chunk_file(str(file_path))
        assert chunks == []


# ═══════════════════════════════════════════════
# 边界情况测试
# ═══════════════════════════════════════════════

class TestEdgeCases:
    """边界情况"""

    def test_only_headers_no_content(self, chunker: Chunker):
        """只有标题没有内容"""
        text = "## 标题一\n\n## 标题二\n\n## 标题三"
        chunks = chunker.chunk_text(text, {"source": "test"})
        # 标题之间的内容为空，应该被去除
        assert len(chunks) == 0
        for chunk in chunks:
            assert chunk.text.strip() != "" or chunk.text == ""

    def test_repr_shows_length(self):
        """TextChunk 的 repr 应该显示字数"""
        chunk = TextChunk("Hello World", {"source": "test.md"})
        rep = repr(chunk)
        assert "test.md" in rep
        assert "11字" in rep  # "Hello World" is 11 chars

    def test_chunk_size_config(self):
        """应该能配置不同的 chunk_size"""
        c = Chunker(chunk_size=100, overlap=20)
        text = ("X" * 50) + "\n\n" + ("Y" * 50)
        chunks = c.chunk_text(text, {"source": "test"})
        assert len(chunks) >= 1

    def test_mixed_header_levels(self, chunker: Chunker):
        """混合不同级别的标题"""
        text = """## 二级标题
二级内容

### 三级标题
三级内容

## 另一个二级标题
另一个二级内容"""
        chunks = chunker.chunk_text(text, {"source": "test"})
        # 应该正确识别所有标题
        headers = [c.metadata["header"] for c in chunks]
        assert "## 二级标题" in headers
        assert "### 三级标题" in headers
        assert "## 另一个二级标题" in headers


# ═══════════════════════════════════════════════
# 真实文档测试（用面试1.0.md）
# ═══════════════════════════════════════════════

class TestRealDocument:
    """用真实的面试文档测试"""

    def test_chunk_interview_doc(self, chunker: Chunker):
        """面试1.0.md 应该被正常切块"""
        import os
        doc_path = os.path.join(
            os.path.dirname(__file__),
            "..", "knowledge", "面试1.0.md"
        )
        if not os.path.exists(doc_path):
            pytest.skip("面试1.0.md 不存在，跳过")
        chunks = chunker.chunk_file(doc_path)
        assert len(chunks) > 0
        # 每块都有内容
        for chunk in chunks:
            assert len(chunk.text) > 0
        # metadata 正确
        assert chunks[0].metadata["source"] == "面试1.0.md"
        assert "topic" in chunks[0].metadata

    def test_interview_doc_chunk_count_reasonable(self, chunker: Chunker):
        """1019 行的文档不应该切出过多小块"""
        import os
        doc_path = os.path.join(
            os.path.dirname(__file__),
            "..", "knowledge", "面试1.0.md"
        )
        if not os.path.exists(doc_path):
            pytest.skip("面试1.0.md 不存在，跳过")
        chunks = chunker.chunk_file(doc_path)
        # 1019 行约 30-50 个小题，每道题一块，不应该超过 150 块
        assert len(chunks) < 150, f"块数过多：{len(chunks)}"
        assert len(chunks) > 3, f"块数过少：{len(chunks)}"

    def test_each_chunk_has_header_in_interview(self, chunker: Chunker):
        """面试文档的每个块都应该有对应的标题"""
        import os
        doc_path = os.path.join(
            os.path.dirname(__file__),
            "..", "knowledge", "面试1.0.md"
        )
        if not os.path.exists(doc_path):
            pytest.skip("面试1.0.md 不存在，跳过")
        chunks = chunker.chunk_file(doc_path)
        for chunk in chunks:
            assert "header" in chunk.metadata
            assert chunk.metadata["header"] != ""
