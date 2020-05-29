import functools
from typing import Any, Callable, Dict, Generator, List, Optional

Generated = Dict[str, Any]
Definition = Dict[str, Any]
DefinitionList = List[Definition]
MapFunction = Callable[[Generated], Generated]


def compose(*functions: Callable) -> Callable:
    """Compose multiple functions into a single one."""

    def noop(x: Any) -> Any:
        return x

    return functools.reduce(lambda f, g: lambda x: f(g(x)), functions, noop)


def make_serializer(
    func: Callable[[DefinitionList], Generator[Optional[Callable], None, None]]
) -> Callable[[DefinitionList], Optional[Callable]]:
    """A maker function to avoid code duplication."""

    def _wrapper(definitions: DefinitionList) -> Optional[Callable]:
        conversions = list(func(definitions))
        if conversions:
            return compose(*[conversion for conversion in conversions if conversion is not None])
        return None

    return _wrapper


def _serialize_openapi3(definitions: DefinitionList) -> Generator[Optional[Callable], None, None]:
    """Different collection styles for Open API 3.0."""
    for definition in definitions:
        name = definition["name"]
        style = definition.get("style")
        explode = definition.get("explode")
        type_ = definition.get("schema", {}).get("type")
        if definition["in"] == "path":
            yield from _serialize_path_openapi3(name, type_, style, explode)
        elif definition["in"] == "query":
            yield from _serialize_query_openapi3(name, type_, style, explode)
        elif definition["in"] == "header":
            yield from _serialize_header_openapi3(name, type_, explode)
        elif definition["in"] == "cookie":
            yield from _serialize_cookie_openapi3(name, type_, explode)


def _serialize_path_openapi3(
    name: str, type_: str, style: Optional[str], explode: Optional[bool]
) -> Generator[Optional[Callable], None, None]:
    if style == "simple":
        if type_ == "object":
            if explode is False:
                yield comma_delimited_object(name)
            if explode is True:
                yield delimited_object(name)
        if type_ == "array":
            yield delimited(name, ",")
    if style == "label":
        if type_ == "object":
            yield label_object(name, explode)
        if type_ == "array":
            yield label_array(name, explode)
    if style == "matrix":
        if type_ == "object":
            yield matrix_object(name, explode)
        if type_ == "array":
            yield matrix_array(name, explode)


def _serialize_query_openapi3(
    name: str, type_: str, style: Optional[str], explode: Optional[bool]
) -> Generator[Optional[Callable], None, None]:
    if type_ == "object":
        if style == "deepObject":
            yield deep_object(name)
        if style is None or style == "form":
            if explode is False:
                yield comma_delimited_object(name)
            if explode is True:
                yield extracted_object(name)
    elif type_ == "array":
        if explode is False:
            if style == "pipeDelimited":
                yield delimited(name, "|")
            if style == "spaceDelimited":
                yield delimited(name, " ")
            if style is None or style == "form":  # "form" is the default style
                yield delimited(name, ",")


def _serialize_header_openapi3(
    name: str, type_: str, explode: Optional[bool]
) -> Generator[Optional[Callable], None, None]:
    # Header parameters always use the "simple" style, that is, comma-separated values
    if type_ == "array":
        yield delimited(name, ",")
    if type_ == "object":
        if explode is False:
            yield comma_delimited_object(name)
        if explode is True:
            yield delimited_object(name)


def _serialize_cookie_openapi3(
    name: str, type_: str, explode: Optional[bool]
) -> Generator[Optional[Callable], None, None]:
    # Cookie parameters always use the "form" style
    if explode and type_ in ("array", "object"):
        # `explode=true` doesn't make sense
        # I.e. we can't create multiple values for the same cookie
        # We use the same behavior as in the examples - https://swagger.io/docs/specification/serialization/
        # The item is removed
        yield nothing(name)
    if explode is False:
        if type_ == "array":
            yield delimited(name, ",")
        if type_ == "object":
            yield comma_delimited_object(name)


def _serialize_swagger2(definitions: DefinitionList) -> Generator[Optional[Callable], None, None]:
    """Different collection formats for Open API 2.0."""
    for definition in definitions:
        name = definition["name"]
        collection_format = definition.get("collectionFormat", "csv")
        type_ = definition.get("type")
        if definition["in"] != "body" and type_ in ("array", "object"):
            if collection_format == "csv":
                yield delimited(name, ",")
            if collection_format == "ssv":
                yield delimited(name, " ")
            if collection_format == "tsv":
                yield delimited(name, "\t")
            if collection_format == "pipes":
                yield delimited(name, "|")


serialize_openapi3_parameters = make_serializer(_serialize_openapi3)
serialize_swagger2_parameters = make_serializer(_serialize_swagger2)


def delimited(name: str, delimiter: str) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            item[name] = delimiter.join(item[name])
        return item

    return _map


def deep_object(name: str) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            generated = item.pop(name)
            item.update({f"{name}[{key}]": value for key, value in generated.items()})
        return item

    return _map


def comma_delimited_object(name: str) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            item[name] = ",".join(map(str, sum(item[name].items(), ())))
        return item

    return _map


def delimited_object(name: str) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            item[name] = ",".join(f"{key}={value}" for key, value in item[name].items())
        return item

    return _map


def extracted_object(name: str) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            generated = item.pop(name)
            item.update(generated)
        return item

    return _map


def label_array(name: str, explode: Optional[bool]) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            if explode:
                item[name] = f".{'.'.join(item[name])}"
            else:
                item[name] = f".{','.join(item[name])}"
        return item

    return _map


def label_object(name: str, explode: Optional[bool]) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            if explode:
                new = ".".join(f"{key}={value}" for key, value in item[name].items())
                item[name] = f".{new}"
            else:
                object_items = map(str, sum(item[name].items(), ()))
                item[name] = f".{','.join(object_items)}"
        return item

    return _map


def matrix_array(name: str, explode: Optional[bool]) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            if explode:
                new = ";".join(f"{name}={value}" for value in item[name])
                item[name] = f";{new}"
            else:
                item[name] = f";{','.join(item[name])}"
        return item

    return _map


def matrix_object(name: str, explode: Optional[bool]) -> MapFunction:
    def _map(item: Generated) -> Generated:
        if name in item:
            if explode:
                new = ";".join(f"{key}={value}" for key, value in item[name].items())
                item[name] = f";{new}"
            else:
                object_items = map(str, sum(item[name].items(), ()))
                item[name] = f";{','.join(object_items)}"
        return item

    return _map


def nothing(name: str) -> MapFunction:
    def _map(item: Generated) -> Generated:
        item.pop(name, None)
        return item

    return _map
