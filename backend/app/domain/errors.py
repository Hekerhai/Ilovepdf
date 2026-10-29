"""Domain errors. The API layer maps these to HTTP responses in one place."""


class FolioError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class ValidationFailed(FolioError):
    status_code = 422
    code = "invalid_input"


class NotFound(FolioError):
    status_code = 404
    code = "not_found"


class Unauthorized(FolioError):
    status_code = 401
    code = "unauthorized"


class Forbidden(FolioError):
    status_code = 403
    code = "forbidden"


class PremiumRequired(FolioError):
    status_code = 402
    code = "premium_required"


class QuotaExceeded(FolioError):
    status_code = 429
    code = "quota_exceeded"


class ServiceUnavailable(FolioError):
    status_code = 503
    code = "service_unavailable"


class ToolFailed(FolioError):
    status_code = 422
    code = "tool_failed"
