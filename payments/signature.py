import hashlib
import hmac

from django.conf import settings


def compute_signature(body: bytes, secret: str | None = None) -> str:
    key = (secret if secret is not None else settings.WEBHOOK_SECRET).encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(compute_signature(body), signature.strip().lower())
