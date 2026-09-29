"""ClaudeVerifier con el SDK real de Anthropic y la red interceptada (sin gastar crédito)."""

import json

import anthropic
import httpx2 as httpx

from app.marks.verifier import ClaudeVerifier
from tests.test_marks import _refs_crops


def test_sdk_builds_valid_request_and_parses_structured_answer():
    seen = {}
    answer = {
        "candidatos": [
            {"candidato_id": "m7_p1_c1", "es_marca": True, "marca_referencia_id": 7, "confianza": 0.94, "motivo": "Mismo lazo con raya central"},
            {"candidato_id": "m7_p1_c2", "es_marca": False, "marca_referencia_id": None, "confianza": 0.1, "motivo": "Es una palomita"},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5",
                "content": [{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1234, "output_tokens": 210},
            },
        )

    client = anthropic.Anthropic(api_key="sk-test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    refs, crops = _refs_crops()
    out = {v.candidate_id: v for v in ClaudeVerifier(client, model="claude-opus-5").verify(refs, crops)}

    assert out["m7_p1_c1"].is_mark and out["m7_p1_c1"].confidence == 0.94
    assert not out["m7_p1_c2"].is_mark

    body = seen["body"]
    assert seen["url"].startswith("https://api.anthropic.com/v1/messages")
    assert "server-side-fallback-2026-07-01" in seen["headers"]["anthropic-beta"]
    assert body["fallbacks"] == "default"
    assert body["model"] == "claude-opus-5"
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema" and "candidatos" in fmt["schema"]["properties"]
    blocks = body["messages"][0]["content"]
    assert sum(b["type"] == "image" for b in blocks) == 3
    assert all(b["source"]["media_type"] == "image/png" for b in blocks if b["type"] == "image")
    assert "temperature" not in body and "budget_tokens" not in json.dumps(body)


def test_grading_schema_round_trip_through_real_sdk():
    from app.grading.schemas import GradingOut
    from app.vision.claude_client import ClaudeClient, image_block, text_block
    from tests.test_grading_api import GRADING_75

    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_2", "type": "message", "role": "assistant", "model": "claude-opus-5",
                "content": [{"type": "text", "text": json.dumps(GRADING_75, ensure_ascii=False)}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 4200, "output_tokens": 900},
            },
        )

    client = anthropic.Anthropic(api_key="sk-test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    out, usage = ClaudeClient(client, model="claude-opus-5").structured(
        "sistema", [text_block("clave"), image_block(b"\xff\xd8fake")], GradingOut, purpose="prueba"
    )
    assert [e.estado for e in out.ejercicios] == ["correcto", "correcto", "error_menor", "error_menor"]
    assert usage.input_tokens == 4200
    schema = seen["body"]["output_config"]["format"]["schema"]
    text = json.dumps(schema)
    # Enumeraciones del esquema y sin restricciones numéricas (no soportadas).
    assert "error_menor" in text and "ilegible" in text
    assert "minimum" not in text and "maximum" not in text
