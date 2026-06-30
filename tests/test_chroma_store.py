# tests/test_chroma_store.py
# Responsibility: Test ChromaStore CRUD functionality

import pytest
import numpy as np
from pathlib import Path
from rag.chroma_store import ChromaStore


class SimpleEmbedding:
    """Lightweight test embedding - returns random 384-dim vectors, no model dependency"""

    def __call__(self, input: list[str]):
        return [np.random.randn(384).astype(np.float32) for _ in input]

    def embed_query(self, input):
        """Required by chromadb 1.5.9+ for query embedding"""
        return self.__call__(input)


# All tests share one Chroma instance (avoid frequent create/destroy, slow on Windows)
@pytest.fixture(scope="session")
def chroma_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("chroma")


@pytest.fixture
def store(chroma_dir: Path) -> ChromaStore:
    """Each test function shares one directory, data isolation via different collection names"""
    return ChromaStore(chroma_dir, embedding_function=SimpleEmbedding())


# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
# Initialization tests
# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
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
        s1.add_documents(["content"], [{"source": "test"}], ["id_1"],
                         collection_name="load_test")
        assert s1.count("load_test") == 1
        del s1
        s2 = ChromaStore(db_path, embedding_function=ef)
        assert s2.count("load_test") == 1


# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
# Write tests
# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
class TestAddDocuments:
    def test_add_one_document(self, store: ChromaStore):
        store.add_documents(
            texts=["Test content"],
            metadatas=[{"source": "test.md"}],
            ids=["add_1"],
            collection_name="test_add",
        )
        assert store.count("test_add") == 1

    def test_add_multiple_documents(self, store: ChromaStore):
        store.add_documents(
            texts=["Content A", "Content B", "Content C"],
            metadatas=[{"source": "a"}, {"source": "b"}, {"source": "c"}],
            ids=["add_m_a", "add_m_b", "add_m_c"],
            collection_name="test_add_multi",
        )
        assert store.count("test_add_multi") == 3

    def test_count_empty(self, store: ChromaStore):
        assert store.count("test_empty_1") == 0


# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
# Search tests
# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
class TestSearch:
    def test_search_returns_results(self, store: ChromaStore):
        store.add_documents(
            texts=["Spring Boot is Java framework", "HashMap is array + linked list"],
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
        results = store.search("any content", collection_name="test_srch_empty")
        assert results == []

    def test_search_n_results_limit(self, store: ChromaStore):
        results = store.search("Spring Boot", n_results=1,
                               collection_name="test_srch")
        assert len(results) <= 1


# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
# Collection management tests
# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
class TestCollection:
    def test_custom_collection_name(self, store: ChromaStore):
        store.add_documents(
            texts=["Custom collection content"],
            metadatas=[{"source": "test"}],
            ids=["col_1"],
            collection_name="custom_coll",
        )
        assert store.count("custom_coll") == 1

    def test_delete_collection(self, store: ChromaStore):
        store.add_documents(
            texts=["To be deleted"],
            metadatas=[{"source": "test"}],
            ids=["del_1"],
            collection_name="to_delete",
        )
        assert store.count("to_delete") > 0
        store.delete_collection("to_delete")
        assert store.count("to_delete") == 0

    def test_delete_nonexistent_collection(self, store: ChromaStore):
        # Should not raise error
        store.delete_collection("not_exist_xxx")

    def test_multiple_collections_isolation(self, store: ChromaStore):
        store.add_documents(
            texts=["A content"], metadatas=[{"source": "a"}],
            ids=["iso_a1"], collection_name="coll_iso_a",
        )
        store.add_documents(
            texts=["B content"], metadatas=[{"source": "b"}],
            ids=["iso_b1"], collection_name="coll_iso_b",
        )
        assert store.count("coll_iso_a") == 1
        assert store.count("coll_iso_b") == 1


# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
# Edge case tests
# ¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T¨T
class TestEdgeCases:
    def test_unicode(self, store: ChromaStore):
        store.add_documents(
            texts=["Special chars: @#$%^&*() and Chinese mixed"],
            metadatas=[{"source": "test"}],
            ids=["uni_1"],
            collection_name="test_uni",
        )
        assert store.count("test_uni") == 1

    def test_long_text(self, store: ChromaStore):
        long_text = "test " * 1000
        store.add_documents(
            texts=[long_text],
            metadatas=[{"source": "test"}],
            ids=["long_1"],
            collection_name="test_long",
        )
        assert store.count("test_long") == 1

    def test_empty_texts_list_does_not_crash(self, store: ChromaStore):
        """Empty list should not crash"""
        store.add_documents(texts=[], metadatas=[], ids=[],
                            collection_name="test_empty")
        assert store.count("test_empty") == 0
