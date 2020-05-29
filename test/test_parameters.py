import datetime
from copy import deepcopy
from urllib.parse import quote, unquote

import pytest
import yaml
from hypothesis import HealthCheck, given, settings

import schemathesis

from .utils import as_param


def test_headers(testdir):
    # When parameter is specified for "header"
    testdir.make_test(
        """
@schema.parametrize()
@settings(suppress_health_check=[HealthCheck.filter_too_much], deadline=None)
def test_(case):
    assert_str(case.headers["api_key"])
    assert_requests_call(case)
        """,
        **as_param({"name": "api_key", "in": "header", "required": True, "type": "string"}),
    )
    # Then the generated test case should contain it in its `headers` attribute
    testdir.run_and_assert(passed=1)


def test_cookies(testdir):
    # When parameter is specified for "cookie"
    testdir.make_test(
        """
@schema.parametrize()
@settings(suppress_health_check=[HealthCheck.filter_too_much], deadline=None)
def test_(case):
    assert_str(case.cookies["token"])
    assert_requests_call(case)
        """,
        schema_name="simple_openapi.yaml",
        **as_param({"name": "token", "in": "cookie", "required": True, "schema": {"type": "string"}}),
    )
    # Then the generated test case should contain it in its `cookies` attribute
    testdir.run_and_assert(passed=1)


def test_body(testdir):
    # When parameter is specified for "body"
    testdir.make_test(
        """
@schema.parametrize(method="POST")
@settings(max_examples=3, deadline=None)
def test_(case):
    assert_int(case.body)
    assert_requests_call(case)
        """,
        paths={
            "/users": {
                "post": {
                    "parameters": [{"name": "id", "in": "body", "required": True, "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    )
    # Then the generated test case should contain it in its `body` attribute
    testdir.run_and_assert(passed=1)


def test_path(testdir):
    # When parameter is specified for "path"
    testdir.make_test(
        """
@schema.parametrize(endpoint="/users/{user_id}")
@settings(max_examples=3, deadline=None)
def test_(case):
    assert_int(case.path_parameters["user_id"])
    assert_requests_call(case)
        """,
        paths={
            "/users/{user_id}": {
                "get": {
                    "parameters": [{"name": "user_id", "required": True, "in": "path", "type": "integer"}],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    )
    # Then the generated test case should contain it its `path_parameters` attribute
    testdir.run_and_assert(passed=1)


def test_multiple_path_variables(testdir):
    # When there are multiple parameters for "path"
    testdir.make_test(
        """
@schema.parametrize(endpoint="/users/{user_id}/{event_id}")
@settings(max_examples=3, deadline=None)
def test_(case):
    assert_int(case.path_parameters["user_id"])
    assert_int(case.path_parameters["event_id"])
    assert_requests_call(case)
        """,
        paths={
            "/users/{user_id}/{event_id}": {
                "get": {
                    "parameters": [
                        {"name": "user_id", "required": True, "in": "path", "type": "integer"},
                        {"name": "event_id", "required": True, "in": "path", "type": "integer"},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    )
    # Then the generated test case should contain them its `path_parameters` attribute
    testdir.run_and_assert(passed=1)


def test_form_data(testdir):
    # When parameter is specified for "form_data"
    testdir.make_test(
        """
@schema.parametrize()
@settings(max_examples=1, deadline=None)
def test_(case):
    assert_str(case.form_data["status"])
    assert_requests_call(case)
        """,
        **as_param({"name": "status", "in": "formData", "required": True, "type": "string"}),
    )
    # Then the generated test case should contain it in its `form_data` attribute
    testdir.run_and_assert(passed=1)


@pytest.fixture(params=["swagger", "openapi"])
def schema_spec(request):
    return request.param


@pytest.fixture
def base_schema(request, schema_spec):
    if schema_spec == "swagger":
        return deepcopy(request.getfixturevalue("simple_schema"))
    if schema_spec == "openapi":
        return deepcopy(request.getfixturevalue("simple_openapi"))


@pytest.fixture(params=["header", "query"])
def location(request):
    return request.param


@pytest.fixture
def schema(schema_spec, location, base_schema):
    # It is the same for Swagger & Open API
    definition = {"api_key": {"type": "apiKey", "name": "api_key", "in": location}}
    if schema_spec == "swagger":
        base_schema["securityDefinitions"] = definition
    if schema_spec == "openapi":
        components = base_schema.setdefault("components", {})
        components["securitySchemes"] = definition
    base_schema["security"] = [{"api_key": []}]
    return base_schema


def test_security_definitions_api_key(testdir, schema, location):
    # When schema contains "apiKeySecurity" security definition
    # And it is in query or header
    location = "headers" if location == "header" else location
    testdir.make_test(
        f"""
@schema.parametrize()
@settings(max_examples=1, deadline=None)
def test_(case):
    assert_str(case.{location}["api_key"])
    assert_requests_call(case)
        """,
        schema=schema,
    )
    # Then the generated test case should contain API key in a proper place
    testdir.run_and_assert(passed=1)


def test_security_definitions_api_key_cookie(testdir, simple_openapi):
    # When schema contains "apiKeySecurity" security definition
    # And it is in cookie
    schema = deepcopy(simple_openapi)
    components = schema.setdefault("components", {})
    components["securitySchemes"] = {"api_key": {"type": "apiKey", "name": "api_key", "in": "cookie"}}
    schema["security"] = [{"api_key": []}]
    testdir.make_test(
        """
@schema.parametrize()
@settings(max_examples=1, deadline=None)
def test_(case):
    assert_str(case.cookies["api_key"])
    assert_requests_call(case)
        """,
        schema=schema,
    )
    # Then the generated test case should contain API key in a proper place
    testdir.run_and_assert(passed=1)


@pytest.fixture()
def overridden_security_schema(schema, schema_spec):
    if schema_spec == "swagger":
        schema["paths"]["/users"]["get"]["security"] = []
    if schema_spec == "openapi":
        schema["paths"]["/query"]["get"]["security"] = []
    return schema


def test_security_definitions_override(testdir, overridden_security_schema, location):
    # When "security" is an empty list in the endpoint definition
    testdir.make_test(
        """
@schema.parametrize()
@settings(max_examples=1, deadline=None)
def test_(case):
    assert "api_key" not in (case.headers or [])
    assert "api_key" not in (case.query or [])
    assert_requests_call(case)
        """,
        schema=overridden_security_schema,
    )
    # Then the generated test case should not contain API key
    testdir.run_and_assert(passed=1)


@pytest.fixture()
def basic_auth_schema(base_schema, schema_spec):
    if schema_spec == "swagger":
        base_schema["securityDefinitions"] = {"basic_auth": {"type": "basic"}}
    if schema_spec == "openapi":
        components = base_schema.setdefault("components", {})
        components["securitySchemes"] = {"basic_auth": {"type": "http", "scheme": "basic"}}
    base_schema["security"] = [{"basic_auth": []}]
    return base_schema


def test_security_definitions_basic_auth(testdir, basic_auth_schema):
    # When schema is using HTTP Basic Auth
    testdir.make_test(
        """
import base64

@schema.parametrize()
@settings(max_examples=1, deadline=None)
def test_(case):
    assert "Authorization" in case.headers
    auth = case.headers["Authorization"]
    assert auth.startswith("Basic ")
    assert isinstance(base64.b64decode(auth[6:]), bytes)
    assert_requests_call(case)
        """,
        schema=basic_auth_schema,
    )
    # Then the generated data should contain a valid "Authorization" header
    testdir.run_and_assert(passed=1)


def test_security_definitions_bearer_auth(testdir, simple_openapi):
    # When schema is using HTTP Bearer Auth scheme
    schema = deepcopy(simple_openapi)
    components = schema.setdefault("components", {})
    components["securitySchemes"] = {"bearer_auth": {"type": "http", "scheme": "bearer"}}
    schema["security"] = [{"bearer_auth": []}]
    testdir.make_test(
        """
@schema.parametrize()
@settings(max_examples=1, deadline=None)
def test_(case):
    assert "Authorization" in case.headers
    auth = case.headers["Authorization"]
    assert auth.startswith("Bearer ")
    assert_requests_call(case)
        """,
        schema=schema,
    )
    # Then the generated test case should contain a valid "Authorization" header
    testdir.run_and_assert("-s", passed=1)


def test_unknown_data(testdir):
    # When parameter is specified for unknown "in"
    # And schema validation is disabled
    testdir.make_test(
        """
@schema.parametrize()
@settings(max_examples=1)
def test_(case):
    pass
        """,
        **as_param({"name": "status", "in": "unknown", "required": True, "type": "string"}),
        validate_schema=False,
    )
    # Then the generated test ignores this parameter
    testdir.run_and_assert(passed=1)


@pytest.mark.hypothesis_nested
def test_date_deserializing(testdir):
    # When dates in schema are written without quotes (achieved by dumping the schema with date instances)
    schema = {
        "openapi": "3.0.2",
        "info": {"title": "Test", "description": "Test", "version": "0.1.0"},
        "paths": {
            "/teapot": {
                "get": {
                    "summary": "Test",
                    "parameters": [
                        {
                            "name": "key",
                            "in": "query",
                            "required": True,
                            "schema": {
                                "allOf": [
                                    # For sake of example to check allOf logic
                                    {"type": "string", "example": datetime.date(2020, 1, 1)},
                                    {"type": "string", "example": datetime.date(2020, 1, 1)},
                                ]
                            },
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    schema_path = testdir.makefile(".yaml", schema=yaml.dump(schema))
    # Then yaml loader should ignore it
    # And data generation should work without errors
    schema = schemathesis.from_path(str(schema_path))

    @given(case=schema["/teapot"]["GET"].as_strategy())
    @settings(suppress_health_check=[HealthCheck.filter_too_much])
    def test(case):
        assert isinstance(case.query["key"], str)

    test()


ARRAY_SCHEMA = {"type": "array", "enum": [["blue", "black", "brown"]]}
OBJECT_SCHEMA = {
    "additionalProperties": False,
    "type": "object",
    "properties": {
        "r": {"type": "integer", "enum": [100]},  # "const" is not supported by Open API
        "g": {"type": "integer", "enum": [200]},
        "b": {"type": "integer", "enum": [150]},
    },
    "required": ["r", "g", "b"],
}


def chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i : i + n]


# Helpers to avoid dictionary ordering issues


class Prefixed:
    def __init__(self, instance, prefix=""):
        self.instance = quote(instance)
        self.prefix = quote(prefix)

    def prepare(self, value):
        raise NotImplementedError

    def __eq__(self, other):
        if self.prefix:
            if not other.startswith(self.prefix):
                return False
            instance = self.instance[len(self.prefix) :]
            other = other[len(self.prefix) :]
        else:
            instance = self.instance
        return self.prepare(instance) == self.prepare(other)

    def __str__(self):
        return self.instance

    def __repr__(self):
        return f"'{self.instance}'"


class CommaDelimitedObject(Prefixed):
    def prepare(self, value):
        items = unquote(value).split(",")
        return dict(chunks(items, 2))


class DelimitedObject(Prefixed):
    def __init__(self, *args, delimiter=",", **kwargs):
        super().__init__(*args, **kwargs)
        self.delimiter = delimiter

    def prepare(self, value):
        items = unquote(value).split(self.delimiter)
        return dict(item.split("=") for item in items)


def make_openapi_schema(*parameters):
    return {
        "openapi": "3.0.2",
        "info": {"title": "Test", "description": "Test", "version": "0.1.0"},
        "paths": {
            "/teapot": {
                "get": {"summary": "Test", "parameters": list(parameters), "responses": {"200": {"description": "OK"}},}
            }
        },
    }


def assert_generates(raw_schema, expected, parameter):
    schema = schemathesis.from_dict(raw_schema)

    @given(case=schema["/teapot"]["GET"].as_strategy())
    def test(case):
        assert getattr(case, parameter) == expected

    test()


@pytest.mark.hypothesis_nested
@pytest.mark.parametrize(
    "schema, explode, style, expected",
    (
        # Based on examples from https://swagger.io/docs/specification/serialization/
        (OBJECT_SCHEMA, True, "deepObject", {"color[r]": 100, "color[g]": 200, "color[b]": 150}),
        (OBJECT_SCHEMA, True, "form", {"r": 100, "g": 200, "b": 150}),
        (OBJECT_SCHEMA, False, "form", {"color": CommaDelimitedObject("r,100,g,200,b,150")}),
        (ARRAY_SCHEMA, False, "pipeDelimited", {"color": "blue|black|brown"}),
        (ARRAY_SCHEMA, True, "pipeDelimited", {"color": ["blue", "black", "brown"]}),
        (ARRAY_SCHEMA, False, "spaceDelimited", {"color": "blue black brown"}),
        (ARRAY_SCHEMA, True, "spaceDelimited", {"color": ["blue", "black", "brown"]}),
        (ARRAY_SCHEMA, False, "form", {"color": "blue,black,brown"}),
        (ARRAY_SCHEMA, True, "form", {"color": ["blue", "black", "brown"]}),
    ),
)
def test_query_serialization_styles_openapi3(schema, explode, style, expected):
    raw_schema = make_openapi_schema(
        {"name": "color", "in": "query", "required": True, "schema": schema, "explode": explode, "style": style}
    )
    assert_generates(raw_schema, expected, "query")


@pytest.mark.hypothesis_nested
@pytest.mark.parametrize(
    "schema, explode, expected",
    (
        (ARRAY_SCHEMA, True, {"X-Api-Key": "blue,black,brown"}),
        (ARRAY_SCHEMA, False, {"X-Api-Key": "blue,black,brown"}),
        (OBJECT_SCHEMA, True, {"X-Api-Key": DelimitedObject("r=100,g=200,b=150")}),
        (OBJECT_SCHEMA, False, {"X-Api-Key": CommaDelimitedObject("r,100,g,200,b,150")}),
    ),
)
def test_header_serialization_styles_openapi3(schema, explode, expected):
    raw_schema = make_openapi_schema(
        {"name": "X-Api-Key", "in": "header", "required": True, "schema": schema, "explode": explode}
    )
    assert_generates(raw_schema, expected, "headers")


@pytest.mark.hypothesis_nested
@pytest.mark.parametrize(
    "schema, explode, expected",
    (
        (ARRAY_SCHEMA, True, {}),
        (ARRAY_SCHEMA, False, {"SessionID": "blue,black,brown"}),
        (OBJECT_SCHEMA, True, {}),
        (OBJECT_SCHEMA, False, {"SessionID": CommaDelimitedObject("r,100,g,200,b,150")}),
    ),
)
def test_cookie_serialization_styles_openapi3(schema, explode, expected):
    raw_schema = make_openapi_schema(
        {"name": "SessionID", "in": "cookie", "required": True, "schema": schema, "explode": explode}
    )
    assert_generates(raw_schema, expected, "cookies")


@pytest.mark.hypothesis_nested
@pytest.mark.parametrize(
    "schema, style, explode, expected",
    (
        (ARRAY_SCHEMA, "simple", False, {"color": quote("blue,black,brown")}),
        (ARRAY_SCHEMA, "simple", True, {"color": quote("blue,black,brown")}),
        (OBJECT_SCHEMA, "simple", False, {"color": CommaDelimitedObject("r,100,g,200,b,150")}),
        (OBJECT_SCHEMA, "simple", True, {"color": DelimitedObject("r=100,g=200,b=150")}),
        (ARRAY_SCHEMA, "label", False, {"color": quote(".blue,black,brown")}),
        (ARRAY_SCHEMA, "label", True, {"color": quote(".blue.black.brown")}),
        (OBJECT_SCHEMA, "label", False, {"color": CommaDelimitedObject(".r,100,g,200,b,150", prefix=".")}),
        (OBJECT_SCHEMA, "label", True, {"color": DelimitedObject(".r=100.g=200.b=150", prefix=".", delimiter=".")}),
        (ARRAY_SCHEMA, "matrix", False, {"color": quote(";blue,black,brown")}),
        (ARRAY_SCHEMA, "matrix", True, {"color": quote(";color=blue;color=black;color=brown")}),
        (OBJECT_SCHEMA, "matrix", False, {"color": CommaDelimitedObject(";r,100,g,200,b,150", prefix=";")}),
        (OBJECT_SCHEMA, "matrix", True, {"color": DelimitedObject(";r=100;g=200;b=150", prefix=";", delimiter=";")}),
    ),
)
def test_path_serialization_styles_openapi3(schema, style, explode, expected):
    raw_schema = {
        "openapi": "3.0.2",
        "info": {"title": "Test", "description": "Test", "version": "0.1.0"},
        "paths": {
            "/teapot/{color}": {
                "get": {
                    "summary": "Test",
                    "parameters": [
                        {
                            "name": "color",
                            "in": "path",
                            "required": True,
                            "schema": schema,
                            "style": style,
                            "explode": explode,
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    schema = schemathesis.from_dict(raw_schema)

    @given(case=schema["/teapot/{color}"]["GET"].as_strategy())
    def test(case):
        assert case.path_parameters == expected

    test()


@pytest.mark.hypothesis_nested
def test_query_serialization_styles_openapi_multiple_params():
    raw_schema = make_openapi_schema(
        {
            "name": "color1",
            "in": "query",
            "required": True,
            "schema": ARRAY_SCHEMA,
            "explode": False,
            "style": "pipeDelimited",
        },
        {
            "name": "color2",
            "in": "query",
            "required": True,
            "schema": ARRAY_SCHEMA,
            "explode": False,
            "style": "spaceDelimited",
        },
    )
    assert_generates(raw_schema, {"color1": "blue|black|brown", "color2": "blue black brown"}, "query")


@pytest.mark.hypothesis_nested
@pytest.mark.parametrize(
    "collection_format, expected",
    (
        ("csv", {"color": "blue,black,brown"}),
        ("ssv", {"color": "blue black brown"}),
        ("tsv", {"color": "blue\tblack\tbrown"}),
        ("pipes", {"color": "blue|black|brown"}),
        ("multi", {"color": ["blue", "black", "brown"]}),
    ),
)
def test_query_serialization_styles_swagger2(collection_format, expected):
    raw_schema = {
        "swagger": "2.0",
        "info": {"title": "Test", "description": "Test", "version": "0.1.0"},
        "host": "127.0.0.1:8888",
        "basePath": "/",
        "schemes": ["http"],
        "produces": ["application/json"],
        "paths": {
            "/teapot": {
                "get": {
                    "parameters": [
                        {
                            "in": "query",
                            "name": "color",
                            "required": True,
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": collection_format,
                            "enum": [["blue", "black", "brown"]],
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    assert_generates(raw_schema, expected, "query")
