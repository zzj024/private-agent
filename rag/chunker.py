# 职责：将长文档切成适合向量检索的小块
# 策略：优先按 Markdown 标题切，其次按段落切，最后按固定长度切

import re
from pathlib import Path

class TextChunk:
    """一个文本块"""
    def __init__(self, text: str, metadata: dict):
        self.text = text
        self.metadata = metadata # text的出处

    def __repr__(self):
        return f"<Chunk {self.metadata.get('source', '?')}[{len(self.text)}字]>"


class Chunker:
    """文档切块器"""

    def __init__(self, chunk_size: int = 300, overlap: int = 50):
        """
        chunk_size: 每块目标字数（字符数）
        overlap:    相邻块之间的重叠字数
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, metadata: dict) -> list[TextChunk]:
        """
        将一段文本切成多个块。

        切分顺序：
        1. 先按 Markdown 二级标题 (## ) 分割
        2. 如果某段还是太长，按空行分割
        3. 如果还是太长，按句子分割
        4. 最后按固定长度切
        """

        if not text or not text.strip():
            return []

        # 第 1 步：按 ## 标题分割
        sections = self._split_by_headers(text)
        chunks = []

        for section_text, header in sections:
            section_meta = {**metadata, "header": header}
            # 跳过空块（标题之间只有空白）
            if not section_text.strip():
                continue
            # 如果这节足够短，直接作为一个块
            if len(section_text) <= self.chunk_size * 1.5:
                chunks.append(TextChunk(section_text.strip(), section_meta))
            else:
                # 太长，继续细分
                sub_chunks = self._split_long_section(section_text, section_meta)
                chunks.extend(sub_chunks)

        return chunks

    def _split_by_headers(self, text: str) -> list[tuple[str, str]]:
        """
        按 Markdown 标题分割文本。
        返回 [(标题下内容, 标题名), ...]
        """
        # 匹配 ## 或 ### 标题
        pattern = re.compile(r'^(#{2,4})\s+(.+)$', re.MULTILINE)
        matches = list(pattern.finditer(text))

        if not matches:
            return [(text, "")]

        sections = []
        for i, match in enumerate(matches):
            header_text = f"{match.group(1)} {match.group(2)}"
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            sections.append((content, header_text))

        return sections

    def _split_long_section(self, text: str, metadata: dict) ->list[TextChunk]:
        """处理过长的段落：先按空行切，再按长度切"""
        # 按空行分割
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

        chunks = []
        buffer = ""
        for para in paragraphs:
            if len(buffer) + len(para) < self.chunk_size:
                buffer += "\n\n" + para if buffer else para
            else:
                if buffer:
                    chunks.append(TextChunk(buffer, metadata))
                # 如果单个段落超长，按固定长度切
                if len(para) > self.chunk_size:
                    sub_chunks = self._split_fixed_length(para, metadata)
                    chunks.extend(sub_chunks)
                    buffer = ""
                else:
                    buffer = para

        if buffer:
            chunks.append(TextChunk(buffer, metadata))

        return chunks

    def _split_fixed_length(self, text: str, metadata: dict) -> list[TextChunk]:
        """按固定长度切块（带重叠）"""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk_text = text[start:end]
            chunks.append(TextChunk(chunk_text, metadata))
            start += self.chunk_size - self.overlap
            if end == len(text):
                break
        return chunks

    def chunk_file(self, file_path: str | Path) -> list[TextChunk]:
        """读取文件并切块"""
        path = Path(file_path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        metadata = {
            "source": path.name,
            "file_path": str(path),
            "topic": path.parent.name,
        }
        return self.chunk_text(text, metadata)