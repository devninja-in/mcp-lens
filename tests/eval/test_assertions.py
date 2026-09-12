import pytest
from src.app.eval.assertions import evaluate_assertion, resolve_path
from src.app.eval.models import Assertion, Status


class TestResolvePath:
    def test_simple_key(self):
        assert resolve_path({"a": 1}, "a") == 1

    def test_nested(self):
        assert resolve_path({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_array_index(self):
        assert resolve_path({"items": [10, 20, 30]}, "items[1]") == 20

    def test_nested_array(self):
        data = {"results": [{"name": "alice"}, {"name": "bob"}]}
        assert resolve_path(data, "results[1].name") == "bob"

    def test_missing_key(self):
        with pytest.raises(KeyError):
            resolve_path({"a": 1}, "b")

    def test_index_out_of_range(self):
        with pytest.raises(KeyError):
            resolve_path({"a": [1]}, "a[5]")

    def test_empty_path(self):
        data = {"a": 1}
        assert resolve_path(data, "") is data


class TestEquals:
    def test_match(self):
        r = evaluate_assertion(Assertion(type="equals", path="x", expected=42), {"x": 42})
        assert r.status == Status.PASS

    def test_no_match(self):
        r = evaluate_assertion(Assertion(type="equals", path="x", expected=42), {"x": 99})
        assert r.status == Status.FAIL

    def test_string_match(self):
        r = evaluate_assertion(Assertion(type="equals", path="s", expected="hello"), {"s": "hello"})
        assert r.status == Status.PASS


class TestNotEquals:
    def test_different(self):
        r = evaluate_assertion(Assertion(type="not_equals", path="x", expected=1), {"x": 2})
        assert r.status == Status.PASS

    def test_same(self):
        r = evaluate_assertion(Assertion(type="not_equals", path="x", expected=1), {"x": 1})
        assert r.status == Status.FAIL


class TestContains:
    def test_string_contains(self):
        r = evaluate_assertion(Assertion(type="contains", path="s", expected="ell"), {"s": "hello"})
        assert r.status == Status.PASS

    def test_list_contains(self):
        r = evaluate_assertion(Assertion(type="contains", path="a", expected=2), {"a": [1, 2, 3]})
        assert r.status == Status.PASS

    def test_not_found(self):
        r = evaluate_assertion(Assertion(type="contains", path="s", expected="xyz"), {"s": "hello"})
        assert r.status == Status.FAIL


class TestRegex:
    def test_match(self):
        r = evaluate_assertion(Assertion(type="regex", path="s", expected=r"^\d{3}$"), {"s": "123"})
        assert r.status == Status.PASS

    def test_no_match(self):
        r = evaluate_assertion(Assertion(type="regex", path="s", expected=r"^\d{3}$"), {"s": "abc"})
        assert r.status == Status.FAIL


class TestExists:
    def test_present(self):
        r = evaluate_assertion(Assertion(type="exists", path="x"), {"x": "val"})
        assert r.status == Status.PASS

    def test_absent(self):
        r = evaluate_assertion(Assertion(type="exists", path="x"), {"y": "val"})
        assert r.status == Status.FAIL


class TestNotExists:
    def test_absent(self):
        r = evaluate_assertion(Assertion(type="not_exists", path="x"), {"y": 1})
        assert r.status == Status.PASS


class TestTypeChecks:
    def test_is_array(self):
        r = evaluate_assertion(Assertion(type="is_array", path="a"), {"a": [1, 2]})
        assert r.status == Status.PASS

    def test_is_not_array(self):
        r = evaluate_assertion(Assertion(type="is_array", path="a"), {"a": "str"})
        assert r.status == Status.FAIL

    def test_is_object(self):
        r = evaluate_assertion(Assertion(type="is_object", path="o"), {"o": {"k": "v"}})
        assert r.status == Status.PASS

    def test_is_string(self):
        r = evaluate_assertion(Assertion(type="is_string", path="s"), {"s": "hello"})
        assert r.status == Status.PASS

    def test_is_number(self):
        r = evaluate_assertion(Assertion(type="is_number", path="n"), {"n": 42})
        assert r.status == Status.PASS

    def test_bool_not_number(self):
        r = evaluate_assertion(Assertion(type="is_number", path="b"), {"b": True})
        assert r.status == Status.FAIL


class TestLength:
    def test_exact(self):
        r = evaluate_assertion(Assertion(type="length", path="a", expected=3), {"a": [1, 2, 3]})
        assert r.status == Status.PASS

    def test_wrong_length(self):
        r = evaluate_assertion(Assertion(type="length", path="a", expected=5), {"a": [1, 2, 3]})
        assert r.status == Status.FAIL

    def test_gte(self):
        r = evaluate_assertion(Assertion(type="length_gte", path="a", expected=2), {"a": [1, 2, 3]})
        assert r.status == Status.PASS

    def test_lte(self):
        r = evaluate_assertion(Assertion(type="length_lte", path="a", expected=3), {"a": [1, 2, 3]})
        assert r.status == Status.PASS


class TestComparisons:
    def test_gt(self):
        r = evaluate_assertion(Assertion(type="gt", path="n", expected=5), {"n": 10})
        assert r.status == Status.PASS

    def test_gte_equal(self):
        r = evaluate_assertion(Assertion(type="gte", path="n", expected=10), {"n": 10})
        assert r.status == Status.PASS

    def test_lt(self):
        r = evaluate_assertion(Assertion(type="lt", path="n", expected=10), {"n": 5})
        assert r.status == Status.PASS

    def test_lte_equal(self):
        r = evaluate_assertion(Assertion(type="lte", path="n", expected=5), {"n": 5})
        assert r.status == Status.PASS


class TestNotEmpty:
    def test_non_empty_list(self):
        r = evaluate_assertion(Assertion(type="not_empty", path="a"), {"a": [1]})
        assert r.status == Status.PASS

    def test_empty_list(self):
        r = evaluate_assertion(Assertion(type="not_empty", path="a"), {"a": []})
        assert r.status == Status.FAIL


class TestSubset:
    def test_is_subset(self):
        r = evaluate_assertion(Assertion(type="subset", path="a", expected=[1, 2]), {"a": [1, 2, 3]})
        assert r.status == Status.PASS

    def test_not_subset(self):
        r = evaluate_assertion(Assertion(type="subset", path="a", expected=[4]), {"a": [1, 2, 3]})
        assert r.status == Status.FAIL


class TestUnknownType:
    def test_unknown(self):
        r = evaluate_assertion(Assertion(type="foobar", path="x"), {"x": 1})
        assert r.status == Status.FAIL
        assert "Unknown assertion type" in r.message


class TestPathResolutionFailure:
    def test_missing_path_fails(self):
        r = evaluate_assertion(Assertion(type="equals", path="missing.path", expected=1), {"x": 1})
        assert r.status == Status.FAIL
        assert "Path resolution failed" in r.message
