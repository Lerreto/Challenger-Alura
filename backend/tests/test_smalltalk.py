from __future__ import annotations

import pytest

from nebula_rag.smalltalk import chat_meta_response, smalltalk_response


TITLES = ["Política de privacidad", "Preguntas frecuentes"]


@pytest.mark.parametrize(
    "question",
    [
        "hola",
        "Hola!",
        "¡Hola! ¿Cómo estás?",
        "buenas tardes",
        "buenos días",
        "que tal",
        "hey",
    ],
)
def test_greetings_get_a_friendly_deterministic_reply(question: str) -> None:
    reply = smalltalk_response(question, TITLES)
    assert reply is not None
    assert "Nébula" in reply


@pytest.mark.parametrize(
    ("question", "fragment"),
    [
        ("gracias", "con gusto"),
        ("Muchas gracias!", "con gusto"),
        ("chao", "hasta luego"),
        ("adiós", "hasta luego"),
        ("¿quién eres?", "asistente documental"),
        ("que puedes hacer", "asistente documental"),
        ("ayuda", "asistente documental"),
    ],
)
def test_social_intents_are_recognized(question: str, fragment: str) -> None:
    reply = smalltalk_response(question, TITLES)
    assert reply is not None
    assert fragment in reply.lower()


def test_identity_reply_lists_the_indexed_documents() -> None:
    reply = smalltalk_response("¿quién eres?", TITLES)
    assert reply is not None
    assert "Política de privacidad" in reply
    assert smalltalk_response("¿quién eres?", []) is not None


@pytest.mark.parametrize(
    "question",
    [
        "hola, ¿cuánto tarda un reembolso?",
        "¿Cuánto tarda un reembolso?",
        "¿qué es la empresa?",
        "hola necesito saber la política de envíos",
        "¿Quién ganó el mundial de fútbol?",
        "gracias por la información, ¿y las devoluciones?",
    ],
)
def test_real_questions_are_never_hijacked_by_smalltalk(question: str) -> None:
    assert smalltalk_response(question, TITLES) is None


@pytest.mark.parametrize(
    "question",
    [
        "puedes revisar el historial de este chat?",
        "¿qué te pregunté antes?",
        "muéstrame el historial de la conversación",
        "¿de qué hemos hablado?",
        "¿se guardan las conversaciones?",
        "puedes consultar mi ultima pregunta?",
        "puedes revisar mi ultima pregunta?",
        "recordás cuál fue mi primera pregunta?",
        "sabes cuál es mi última pregunta?",
    ],
)
def test_chat_meta_questions_are_recognized(question: str) -> None:
    reply = chat_meta_response(question, ["¿Cuánto tarda un reembolso?"])
    assert reply is not None
    assert "¿Cuánto tarda un reembolso?" in reply or "guarda" in reply


def test_chat_meta_on_a_fresh_session_explains_persistence() -> None:
    reply = chat_meta_response("revisa el historial del chat", [])
    assert reply is not None
    assert "conversación nueva" in reply


@pytest.mark.parametrize(
    "question",
    [
        "¿guardan mi historial de compras?",
        "¿cuánto tiempo conservan mis datos?",
        "¿Cuánto tarda un reembolso?",
    ],
)
def test_document_questions_are_not_hijacked_by_chat_meta(question: str) -> None:
    assert chat_meta_response(question, ["algo"]) is None
