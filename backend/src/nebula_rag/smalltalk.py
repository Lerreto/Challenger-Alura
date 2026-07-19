from __future__ import annotations

import re
import unicodedata


_GREETING = (
    r"(?:hola+|holis?|hey|hi|hello|saludos|buen dia|buenos dias"
    r"|buenas(?: dias| tardes| noches)?)"
)
_HOW_ARE_YOU = (
    r"(?:como (?:estas|vas|andas|te va|va todo)|que tal(?: todo| estas)?"
    r"|todo bien|que mas|que hay|que hubo|que haces)"
)
_THANKS = r"(?:(?:muchas |mil )?gracias|te agradezco|muy amable|genial gracias)"
_FAREWELL = (
    r"(?:chao|chau|adios|bye|hasta (?:luego|pronto|manana)|nos vemos|feliz (?:dia|tarde|noche))"
)
_IDENTITY = (
    r"(?:quien (?:eres|sos)|que (?:eres|sos)|que (?:puedes|podes|sabes) hacer"
    r"|en que (?:me )?(?:puedes|podes) ayudar(?:me)?|como (?:funcionas|trabajas)"
    r"|para que (?:sirves|servis)|ayuda|ayudame|help)"
)
_TAIL = r"(?:por favor|porfa)?"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9 ]+", " ", stripped).strip()


def _capabilities_text(document_titles: list[str]) -> str:
    if document_titles:
        listed = ", ".join(sorted(document_titles))
        library = f" En este momento tengo indexados: {listed}."
    else:
        library = " Todavía no hay documentos cargados en la biblioteca."
    return (
        "Soy Nébula, el asistente documental de Nébula Tech. Respondo preguntas usando "
        "únicamente los documentos de la biblioteca y siempre cito mis fuentes."
        + library
        + " Preguntame, por ejemplo, sobre envíos, reembolsos, garantías o privacidad."
    )


_CHAT_REF = r"(?:chat|conversacion(?:es)?|charla|mensajes?|preguntas?)"
_CHAT_META_PATTERNS = [
    rf"historial[a-z ]*\b{_CHAT_REF}",
    rf"{_CHAT_REF}[a-z ]*historial",
    r"\bque te (?:pregunte|dije|escribi|consulte)\b",
    # Any verb before "mi última/primera/anterior pregunta o mensaje" counts:
    # "consultar/revisar/ver/recordar/decirme/saber" + "mi última pregunta".
    r"\bmi (?:primera|ultima|anterior) (?:pregunta|mensaje)\b",
    r"\bde que (?:hemos hablado|hablamos|estabamos hablando|veniamos hablando)\b",
    r"\b(?:resume|resumime|resumen de) (?:la|esta) conversacion\b",
    rf"\b(?:se guardan?|guardas?) (?:las? |los? )?{_CHAT_REF}\b",
]


def chat_meta_response(question: str, previous_user_questions: list[str]) -> str | None:
    """Deterministic reply for questions about the conversation itself."""
    normalized = _normalize(question)
    if not normalized or not any(
        re.search(pattern, normalized) for pattern in _CHAT_META_PATTERNS
    ):
        return None
    if not previous_user_questions:
        return (
            "Esta es una conversación nueva, todavía no hay mensajes anteriores. "
            "Todo lo que hablemos se guarda automáticamente y podés retomarlo luego "
            "desde el selector de conversaciones."
        )
    recent = previous_user_questions[-5:]
    listed = "\n".join(f"• {item}" for item in recent)
    plural = "s" if len(previous_user_questions) != 1 else ""
    return (
        f"Claro. Esta conversación se guarda automáticamente y llevás "
        f"{len(previous_user_questions)} pregunta{plural} hasta ahora. "
        f"La{plural} más reciente{plural}:\n{listed}\n"
        "Podés desplazarte hacia arriba para ver todo, retomar otra conversación "
        "desde el selector, o empezar una nueva con «Nueva conversación»."
    )


def smalltalk_response(question: str, document_titles: list[str]) -> str | None:
    """Deterministic reply for pure social messages; None sends the question to RAG."""
    normalized = _normalize(question)
    if not normalized:
        return None

    if re.fullmatch(rf"{_GREETING}(?:[ ]+{_HOW_ARE_YOU})?[ ]*{_TAIL}", normalized) or re.fullmatch(
        _HOW_ARE_YOU, normalized
    ):
        return (
            "¡Hola! Todo bien por acá, gracias. Soy Nébula, el asistente documental de "
            "Nébula Tech: respondo preguntas sobre los documentos de la biblioteca "
            "(envíos, reembolsos, garantías, privacidad y más) citando siempre las "
            "fuentes. ¿Qué querés saber?"
        )
    if re.fullmatch(rf"(?:{_GREETING}[ ]+)?{_THANKS}[ ]*{_TAIL}", normalized):
        return "¡Con gusto! Si tenés otra pregunta sobre los documentos, escribime."
    if re.fullmatch(rf"(?:{_THANKS}[ ]+)?{_FAREWELL}", normalized):
        return "¡Hasta luego! Acá estaré cuando necesites consultar los documentos."
    if re.fullmatch(rf"(?:{_GREETING}[ ]+)?{_IDENTITY}[ ]*{_TAIL}", normalized):
        return _capabilities_text(document_titles)
    return None
