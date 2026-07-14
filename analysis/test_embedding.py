import unittest
from unittest.mock import patch

from analysis.embedding import EMBEDDING_SIZE, generate_embedding


class _FakeVector(list):
    def tolist(self):
        return list(self)


class _FakeModel:
    def encode(self, text, normalize_embeddings):
        if text != "测试新闻" or normalize_embeddings is not True:
            raise AssertionError("unexpected embedding input")
        return _FakeVector([0.5] * EMBEDDING_SIZE)


class EmbeddingTests(unittest.TestCase):
    def test_generate_embedding_returns_768_floats(self):
        with patch("analysis.embedding._MODEL", _FakeModel()):
            embedding = generate_embedding("测试新闻")

        self.assertEqual(len(embedding), 768)
        self.assertTrue(all(isinstance(value, float) for value in embedding))


if __name__ == "__main__":
    unittest.main()
