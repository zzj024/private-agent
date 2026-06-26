# tests/test_chroma_store.py
# 职责：测试 ChromaStore 的增删改查功能

import pytest
import numpy as np
from pathlib import Path
from rag.chroma_store import ChromaStore


class SimpleEmbedding:
    """轻量测试用 embedding——返回随机 384 维向量，不依赖模型"""

    def __call__(self, input: list[str]):
        return [np.random.randn(384).astype(np.float32) for _ in input]


# 所有测试共享一个 Chroma 实例（避免频繁创建销毁，Windows 下慢）
@pytest.fixture(scope="session")
def chroma_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("chroma")


@pytest.fixture
def store(chroma_dir: Path) -> ChromaStore:
    """每个测试函数共用一个目录，测试间数据隔离通过不同 collection 名"""
    return ChromaStore(chroma_dir, embedding_function=SimpleEmbedding())


# ═══════════════════════════════════════════════
# 初始化测试
# ═══════════════════════════════════════════════

class TestInit:
    def test_init_creates_directory(self, tmp_path: Path):
        db_path = tmp_path / "my_chroma"
        assert not db_path.exists()
        ChromaStore(db_path, embedding_function=SimpleEmbedding())
        assert db_path.exists()

    def test_init_loads_existing(self, tmp_path: Path):
        db_path = tmp_path / "existing"
        ef = SimpleEmbedding()
        s1 = ChromaStore(db_path, embedding_function=ef)
        s1.add_documents(["内容"], [{"source": "test"}], ["id_1"],
                         collection_name="load_test")
        assert s1.count("load_test") == 1
        del s1
        s2 = ChromaStore(db_path, embedding_function=ef)
        assert s2.count("load_test") == 1


# ═══════════════════════════════════════════════
# 写入测试
# ═══════════════════════════════════════════════

class TestAddDocuments:
    def test_add_one_document(self, store: ChromaStore):
        store.add_documents(
            texts=["测试内容"],
            metadatas=[{"source": "test.md"}],
            ids=["add_1"],
            collection_name="test_add",
        )
        assert store.count("test_add") == 1

    def test_add_multiple_documents(self, store: ChromaStore):
        store.add_documents(
            texts=["内容A", "内容B", "内容C"],
            metadatas=[{"source": "a"}, {"source": "b"}, {"source": "c"}],
            ids=["add_m_a", "add_m_b", "add_m_c"],
            collection_name="test_add_multi",
        )
        assert store.count("test_add_multi") == 3

    def test_count_empty(self, store: ChromaStore):
        assert store.count("test_empty_1") == 0


# ═══════════════════════════════════════════════
# 检索测试
# ═══════════════════════════════════════════════

class TestSearch:
    def test_search_returns_results(self, store: ChromaStore):
        store.add_documents(
            texts=["Spring Boot 是 Java 框架", "HashMap 底层是数组+链表"],
            metadatas=[{"source": "test"}, {"source": "test"}],
            ids=["srch_1", "srch_2"],
            collection_name="test_srch",
        )
        results = store.search("Spring Boot", n_results=5,
                               collection_name="test_srch")
        assert len(results) > 0

    def test_search_returns_metadata(self, store: ChromaStore):
        results = store.search("Spring Boot", n_results=5,
                               collection_name="test_srch")
        assert "metadata" in results[0]

    def test_search_returns_distance(self, store: ChromaStore):
        results = store.search("Spring Boot", n_results=5,
                               collection_name="test_srch")
        assert "distance" in results[0]
        assert isinstance(results[0]["distance"], float)

    def test_search_empty_store(self, store: ChromaStore):
        results = store.search("任何内容", collection_name="test_srch_empty")
        assert results == []

    def test_search_n_results_limit(self, store: ChromaStore):
        results = store.search("Spring Boot", n_results=1,
                               collection_name="test_srch")
        assert len(results) <= 1


# ═══════════════════════════════════════════════
# 集合管理测试
# ═══════════════════════════════════════════════

class TestCollection:
    def test_custom_collection_name(self, store: ChromaStore):
        store.add_documents(
            texts=["自定义集合内容"],
            metadatas=[{"source": "test"}],
            ids=["col_1"],
            collection_name="custom_coll",
        )
        assert store.count("custom_coll") == 1

    def test_delete_collection(self, store: ChromaStore):
        store.add_documents(
            texts=["待删除"],
            metadatas=[{"source": "test"}],
            ids=["del_1"],
            collection_name="to_delete",
        )
        assert store.count("to_delete") > 0
        store.delete_collection("to_delete")
        assert store.count("to_delete") == 0

    def test_delete_nonexistent_collection(self, store: ChromaStore):
        store.delete_collection("not_exist_xxx")

    def test_multiple_collections_isolation(self, store: ChromaStore):
        store.add_documents(
            texts=["A内容"], metadatas=[{"source": "a"}],
            ids=["iso_a1"], collection_name="coll_iso_a",
        )
        store.add_documents(
            texts=["B内容"], metadatas=[{"source": "b"}],
            ids=["iso_b1"], collection_name="coll_iso_b",
        )
        assert store.count("coll_iso_a") == 1
        assert store.count("coll_iso_b") == 1


# ═══════════════════════════════════════════════
# 边界情况测试
# ═══════════════════════════════════════════════

class TestEdgeCases:
    def test_unicode(self, store: ChromaStore):
        store.add_documents(
            texts=["特殊字符：🔥 和中文混合"],
            metadatas=[{"source": "test"}],
            ids=["uni_1"],
            collection_name="test_uni",
        )
        assert store.count("test_uni") == 1

    def test_long_text(self, store: ChromaStore):
        long_text = "测试" * 1000
        store.add_documents(
            texts=[long_text],
            metadatas=[{"source": "test"}],
            ids=["long_1"],
            collection_name="test_long",
        )
        assert store.count("test_long") == 1

    def test_empty_texts_list_does_not_crash(self, store: ChromaStore):
        """空列表不会崩溃"""
        store.add_documents(texts=[], metadatas=[], ids=[],
                            collection_name="test_empty")
        assert store.count("test_empty") == 0
