from app.modules.retrieve.retrieve_snowflake import retrieve


class FakeClient:
    def search_segments(self, query: str, limit: int = 10) -> str:
        return f"SQL({query},{limit})"


def test_retrieve_shape():
    results = retrieve("hello", limit=5, client=FakeClient())
    assert isinstance(results, list)
    assert results[0]["sql"] == "SQL(hello,5)"
