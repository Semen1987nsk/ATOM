"""PII redaction helpers for log output (SEC-10)."""
from typing import Optional


def mask_email(email: Optional[str]) -> str:
    """Mask an email for safe logging: "alice@example.com" -> "a***@e***.com".

    Keeps first char of local part + first char of domain label + the TLD.
    None/empty -> "<none>". Malformed (no "@") -> first char + "***".
    """
    if not email:
        return "<none>"

    local, sep, domain = email.partition("@")
    if not sep:
        return f"{local[0]}***" if local else "<none>"

    domain_label, dot, tld = domain.partition(".")
    masked_domain = f"{domain_label[0]}***" if domain_label else "***"
    if dot:
        masked_domain = f"{masked_domain}.{tld}"

    masked_local = f"{local[0]}***" if local else "***"
    return f"{masked_local}@{masked_domain}"
