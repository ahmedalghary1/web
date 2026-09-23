import logging
from rest_framework.views import exception_handler
logger = logging.getLogger("api")
def safe_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("unhandled_api_error view=%s", context.get("view").__class__.__name__ if context.get("view") else "unknown")
    elif response.status_code >= 500:
        logger.error("api_server_error status=%s", response.status_code)
    return response
