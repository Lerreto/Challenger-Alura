class NebulaError(Exception):
    code = "nebula_error"


class DocumentValidationError(NebulaError):
    code = "document_validation_error"


class DocumentProcessingError(NebulaError):
    code = "document_processing_error"


class DocumentConflictError(NebulaError):
    code = "document_conflict"


class DocumentNotFoundError(NebulaError):
    code = "document_not_found"


class LLMUnavailableError(NebulaError):
    code = "llm_not_configured"


class LLMServiceError(NebulaError):
    def __init__(self, code: str, message: str, http_status: int) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
