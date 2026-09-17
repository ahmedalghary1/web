import logging
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
logger = logging.getLogger("api")
@receiver(user_login_failed)
def log_login_failure(sender, credentials, request, **kwargs):
    logger.warning("login_failed phone=%s", credentials.get("phone") or credentials.get("username") or "unknown")
