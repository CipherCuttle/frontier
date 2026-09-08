from scripts.generate_public_contracts import openapi_document, typescript_text


def _signature(text: str, operation_id: str) -> str:
    prefix = f"export async function {operation_id}("
    return next(line for line in text.splitlines() if line.startswith(prefix))


def test_required_query_parameters_do_not_get_empty_default() -> None:
    text = typescript_text(openapi_document())

    search_signature = _signature(text, "searchEvidence")
    radar_signature = _signature(text, "getRadar")

    assert "q: string;" in search_signature
    assert "= {}" not in search_signature
    assert "= {}" in radar_signature
