from src.app.eval.models import Status
from src.app.eval.overlap import (
    _desc_similarity,
    _name_similarity,
    _schema_overlap,
    _tokenize_name,
    detect_overlaps,
)


class TestTokenizeName:
    def test_snake_case(self):
        assert _tokenize_name("get_user_data") == {"get", "user", "data"}

    def test_camel_case(self):
        assert _tokenize_name("getUserData") == {"get", "User", "Data"} or _tokenize_name("getUserData") == {
            "get",
            "user",
            "data",
        }
        tokens = _tokenize_name("getUserData")
        assert all(t.islower() for t in tokens)
        assert "get" in tokens

    def test_single_word(self):
        assert _tokenize_name("search") == {"search"}


class TestNameSimilarity:
    def test_identical(self):
        assert _name_similarity("get_users", "get_users") == 1.0

    def test_completely_different(self):
        score = _name_similarity("get_users", "delete_projects")
        assert score < 0.3

    def test_partial_overlap(self):
        score = _name_similarity("get_user", "get_account")
        assert 0.0 < score < 1.0


class TestDescSimilarity:
    def test_identical(self):
        assert _desc_similarity("Search for users", "Search for users") == 1.0

    def test_different(self):
        score = _desc_similarity("Search for users", "Delete all projects from the database")
        assert score < 0.5

    def test_partial(self):
        score = _desc_similarity("Search for users in the database", "Find users in the system")
        assert 0.0 < score < 1.0


class TestSchemaOverlap:
    def test_same_params(self):
        a = {"inputSchema": {"type": "object", "properties": {"q": {}, "limit": {}}}}
        b = {"inputSchema": {"type": "object", "properties": {"q": {}, "limit": {}}}}
        assert _schema_overlap(a, b) == 1.0

    def test_disjoint(self):
        a = {"inputSchema": {"type": "object", "properties": {"q": {}}}}
        b = {"inputSchema": {"type": "object", "properties": {"id": {}}}}
        assert _schema_overlap(a, b) == 0.0

    def test_partial(self):
        a = {"inputSchema": {"type": "object", "properties": {"q": {}, "limit": {}}}}
        b = {"inputSchema": {"type": "object", "properties": {"q": {}, "offset": {}}}}
        score = _schema_overlap(a, b)
        assert 0.0 < score < 1.0


class TestDetectOverlaps:
    def test_similar_tools_flagged(self):
        tools = [
            {
                "name": "search_users",
                "description": "Search for users in the database by name or email",
                "inputSchema": {"type": "object", "properties": {"query": {}, "limit": {}}},
            },
            {
                "name": "find_users",
                "description": "Find users in the database by name or email address",
                "inputSchema": {"type": "object", "properties": {"query": {}, "limit": {}}},
            },
        ]
        results = detect_overlaps(tools)
        assert len(results) >= 1
        assert results[0].status == Status.WARN
        assert "search_users" in results[0].message
        assert "find_users" in results[0].message

    def test_different_tools_clean(self):
        tools = [
            {
                "name": "search_users",
                "description": "Search for users in the database",
                "inputSchema": {"type": "object", "properties": {"query": {}}},
            },
            {
                "name": "delete_project",
                "description": "Permanently remove a project and all associated data",
                "inputSchema": {"type": "object", "properties": {"project_id": {}}},
            },
        ]
        results = detect_overlaps(tools)
        assert len(results) == 0
