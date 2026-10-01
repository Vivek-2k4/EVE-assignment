from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler


class Conflict(APIException):
    status_code = 409
    default_detail = "The request conflicts with the current state of the resource."
    default_code = "conflict"


class InvalidCredentials(APIException):
    status_code = 401
    default_detail = "Invalid email or password."
    default_code = "invalid_credentials"


class InvalidSignature(APIException):
    status_code = 401
    default_detail = "Invalid or missing webhook signature."
    default_code = "invalid_signature"


_FALLBACK_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "throttled",
}


def api_exception_handler(exc, context):
    """Every error leaves the API as {"error": {"code", "message", "details"?}}."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    details = None
    if isinstance(exc, ValidationError):
        code, message, details = "validation_error", "Invalid request.", data
    else:
        code = getattr(exc, "default_code", None) or _FALLBACK_CODES.get(response.status_code, "error")
        message = str(data.get("detail", "Error")) if isinstance(data, dict) else str(data)

    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    response.data = {"error": body}
    return response
