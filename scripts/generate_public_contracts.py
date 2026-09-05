from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from frontier.adapters.api.public_read import create_public_read_app
from frontier.application.public_read import PublicReadRepository, PublicReadService

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "contracts" / "public" / "openapi_v0.json"
TYPESCRIPT_PATH = (
    ROOT / "clients" / "typescript" / "src" / "generated" / "public_read_v0.ts"
)


class _SchemaOnlyRepository:
    def resolve_snapshot(self, snapshot_id: str | None = None) -> Any:
        raise RuntimeError("schema-only repository")

    def list_observations(self, observation_ids: tuple[str, ...], *, as_of: Any) -> Any:
        raise RuntimeError("schema-only repository")

    def get_observation(self, observation_id: str, *, as_of: Any) -> Any:
        raise RuntimeError("schema-only repository")

    def list_source_health(self, *, as_of: Any) -> Any:
        raise RuntimeError("schema-only repository")


def openapi_document() -> dict[str, Any]:
    repository: PublicReadRepository = _SchemaOnlyRepository()
    app = create_public_read_app(PublicReadService(repository))
    return app.openapi()


def openapi_text(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _ref_name(ref: str) -> str:
    prefix = "#/components/schemas/"
    if not ref.startswith(prefix):
        return "unknown"
    return ref[len(prefix) :]


def _ts_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _ref_name(str(schema["$ref"]))
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(_ts_type(item) for item in schema["anyOf"])
    schema_type = schema.get("type")
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array":
        item_type = _ts_type(schema.get("items", {}))
        return f"Array<{item_type}>"
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        if properties:
            fields: list[str] = []
            for name in sorted(properties):
                optional = "" if name in required else "?"
                fields.append(f"{json.dumps(name)}{optional}: {_ts_type(properties[name])};")
            return "{ " + " ".join(fields) + " }"
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"Record<string, {_ts_type(additional)}>"
        return "Record<string, unknown>"
    return "unknown"


def _response_type(operation: dict[str, Any]) -> str:
    response = operation.get("responses", {}).get("200", {})
    content = response.get("content", {}).get("application/json", {})
    schema = content.get("schema", {})
    return _ts_type(schema) if isinstance(schema, dict) else "unknown"


def _parameter_type(parameter: dict[str, Any]) -> str:
    schema = parameter.get("schema", {})
    return _ts_type(schema) if isinstance(schema, dict) else "unknown"


def typescript_text(document: dict[str, Any]) -> str:
    lines = [
        "// GENERATED from contracts/public/openapi_v0.json. DO NOT EDIT.",
        "// Authority: ADR-0008 / PUBLIC_READ_PLANE_V0.",
        "",
        "export interface FrontierPublicReadTransport {",
        "  get<T>(path: string, query?: Record<string, string | number | boolean | null | undefined>): Promise<T>;",
        "}",
        "",
    ]

    schemas = document.get("components", {}).get("schemas", {})
    for name in sorted(schemas):
        schema = schemas[name]
        if isinstance(schema, dict):
            lines.append(f"export type {name} = {_ts_type(schema)};")
    lines.append("")

    paths = document.get("paths", {})
    for path in sorted(paths):
        path_item = paths[path]
        if not isinstance(path_item, dict) or "get" not in path_item:
            continue
        operation = path_item["get"]
        if not isinstance(operation, dict):
            continue
        operation_id = str(operation.get("operationId", "unnamedOperation"))
        parameters = operation.get("parameters", [])
        path_parameters = [item for item in parameters if item.get("in") == "path"]
        query_parameters = [item for item in parameters if item.get("in") == "query"]
        response_type = _response_type(operation)

        required_args = ["transport: FrontierPublicReadTransport"]
        for parameter in path_parameters:
            required_args.append(f"{parameter['name']}: {_parameter_type(parameter)}")
        query_shape = ""
        if query_parameters:
            fields = []
            for parameter in sorted(query_parameters, key=lambda item: item["name"]):
                optional = "" if parameter.get("required") else "?"
                fields.append(
                    f"{parameter['name']}{optional}: {_parameter_type(parameter)};"
                )
            query_shape = "{ " + " ".join(fields) + " }"
            required_args.append(f"query: {query_shape} = {{}}")

        rendered_path = json.dumps(path)
        for parameter in path_parameters:
            name = parameter["name"]
            rendered_path = rendered_path.replace(
                "{" + name + "}",
                f"${{encodeURIComponent(String({name}))}}",
            )
        if path_parameters:
            rendered_path = "`" + json.loads(rendered_path).replace("`", "\\`") + "`"

        lines.append(
            f"export async function {operation_id}({', '.join(required_args)}): Promise<{response_type}> {{"
        )
        query_arg = ", query" if query_parameters else ""
        lines.append(f"  return transport.get<{response_type}>({rendered_path}{query_arg});")
        lines.append("}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _check(path: Path, expected: str) -> bool:
    return path.exists() and path.read_text(encoding="utf-8") == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    document = openapi_document()
    openapi = openapi_text(document)
    typescript = typescript_text(document)
    if args.check:
        failures = []
        if not _check(OPENAPI_PATH, openapi):
            failures.append(str(OPENAPI_PATH.relative_to(ROOT)))
        if not _check(TYPESCRIPT_PATH, typescript):
            failures.append(str(TYPESCRIPT_PATH.relative_to(ROOT)))
        if failures:
            print("public-contract-generation: FAIL: drift in " + ", ".join(failures))
            return 1
        print("public-contract-generation: PASS")
        return 0

    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    TYPESCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(openapi, encoding="utf-8")
    TYPESCRIPT_PATH.write_text(typescript, encoding="utf-8")
    print(f"wrote {OPENAPI_PATH.relative_to(ROOT)}")
    print(f"wrote {TYPESCRIPT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
