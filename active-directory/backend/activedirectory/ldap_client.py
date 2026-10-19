"""
Thin, read-only LDAP client for Active Directory computer objects.

Built directly on python-ldap (already a dependency via django-auth-ldap,
see auth/auth_backend/ldap_backend.py) rather than adding a new library.
"""

import datetime
import json
import logging
from pathlib import Path

import ldap
from ldap.controls import SimplePagedResultsControl

logger = logging.getLogger("extensions.activedirectory")

_CONFIG = json.loads((Path(__file__).resolve().parent / "config.json").read_text())

COMPUTER_ATTRIBUTES = [
    "objectGUID",
    "cn",
    "sAMAccountName",
    "dNSHostName",
    "distinguishedName",
    "operatingSystem",
    "operatingSystemVersion",
    "userAccountControl",
    "description",
    "whenCreated",
    "whenChanged",
    "lastLogonTimestamp",
    "pwdLastSet",
]

# userAccountControl bit flag for a disabled account/computer object.
UAC_ACCOUNTDISABLE = 0x0002

# Windows FILETIME epoch (1601-01-01) offset from the Unix epoch, in seconds.
_FILETIME_EPOCH_OFFSET = 11644473600


class LDAPConnectionError(Exception):
    """Raised when a domain cannot be reached or bound to."""


def _server_uri(domain):
    scheme = "ldaps" if domain.security == "ldaps" else "ldap"
    return f"{scheme}://{domain.server}:{domain.port}"


def connect(domain):
    """
    Open and bind a connection for the given ADDomain.

    Raises LDAPConnectionError with a human readable message on failure.
    """
    try:
        conn = ldap.initialize(_server_uri(domain))
        conn.set_option(ldap.OPT_REFERRALS, 0)
        conn.set_option(ldap.OPT_NETWORK_TIMEOUT, _CONFIG["connect_timeout_seconds"])
        conn.set_option(ldap.OPT_TIMEOUT, _CONFIG["search_timeout_seconds"])
        conn.set_option(
            ldap.OPT_X_TLS_REQUIRE_CERT,
            ldap.OPT_X_TLS_DEMAND if domain.verify_certificate else ldap.OPT_X_TLS_NEVER,
        )

        if domain.security == "starttls":
            conn.start_tls_s()

        conn.simple_bind_s(domain.bind_dn, domain.bind_password)
        return conn
    except ldap.LDAPError as exc:
        raise LDAPConnectionError(_format_ldap_error(exc)) from exc


def _format_ldap_error(exc):
    if exc.args and isinstance(exc.args[0], dict):
        info = exc.args[0]
        return info.get("desc") or info.get("info") or str(exc)
    return str(exc)


def test_connection(domain):
    """Try to bind to the domain. Returns (ok, error_message)."""
    try:
        conn = connect(domain)
        conn.unbind_s()
        return True, None
    except LDAPConnectionError as exc:
        return False, str(exc)


def _decode_guid(raw_guid):
    return raw_guid.hex() if raw_guid else ""


def _decode_filetime(raw_value):
    """Convert an AD FILETIME/timestamp attribute to an aware datetime, or None."""
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    seconds = value / 10_000_000 - _FILETIME_EPOCH_OFFSET
    try:
        return datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _decode_generalized_time(raw_value):
    """Decode an LDAP GeneralizedTime (whenCreated/whenChanged), or None."""
    try:
        text = raw_value.decode() if isinstance(raw_value, bytes) else raw_value
        return datetime.datetime.strptime(text, "%Y%m%d%H%M%S.0Z").replace(
            tzinfo=datetime.timezone.utc
        )
    except (ValueError, AttributeError, TypeError):
        return None


def _first(values):
    if not values:
        return None
    return values[0]


def _decode_text(raw_value):
    if raw_value is None:
        return ""
    return raw_value.decode("utf-8", errors="ignore") if isinstance(raw_value, bytes) else raw_value


def parse_computer_entry(dn, attrs):
    """Turn one raw LDAP entry into a plain dict of normalized fields."""
    uac = int(_decode_text(_first(attrs.get("userAccountControl"))) or 0)

    return {
        "object_guid": _decode_guid(_first(attrs.get("objectGUID"))),
        "name": _decode_text(_first(attrs.get("cn"))),
        "sam_account_name": _decode_text(_first(attrs.get("sAMAccountName"))),
        "dns_hostname": _decode_text(_first(attrs.get("dNSHostName"))),
        "distinguished_name": dn,
        "ou": dn.split(",", 1)[1] if "," in dn else "",
        "os_name": _decode_text(_first(attrs.get("operatingSystem"))),
        "os_version": _decode_text(_first(attrs.get("operatingSystemVersion"))),
        "enabled": not bool(uac & UAC_ACCOUNTDISABLE),
        "description": _decode_text(_first(attrs.get("description"))),
        "when_created": _decode_generalized_time(_first(attrs.get("whenCreated"))),
        "last_logon": _decode_filetime(_decode_text(_first(attrs.get("lastLogonTimestamp")))),
        "password_last_set": _decode_filetime(
            _decode_text(_first(attrs.get("pwdLastSet")))
        ),
    }


def iter_computers(domain):
    """
    Yield one normalized dict per computer object in the domain, using
    simple paged results so large directories don't load in one response.
    """
    conn = connect(domain)
    try:
        page_control = SimplePagedResultsControl(True, size=_CONFIG["page_size"], cookie="")
        attrs = COMPUTER_ATTRIBUTES + [domain.assigned_user_attribute]

        while True:
            try:
                msgid = conn.search_ext(
                    domain.base_dn,
                    ldap.SCOPE_SUBTREE,
                    "(objectClass=computer)",
                    attrs,
                    serverctrls=[page_control],
                )
                _rtype, results, _rmsgid, serverctrls = conn.result3(msgid)
            except ldap.LDAPError as exc:
                raise LDAPConnectionError(_format_ldap_error(exc)) from exc

            for dn, entry in results:
                if not dn:
                    continue
                entry_dict = parse_computer_entry(dn, entry)
                raw_assigned_user = _first(entry.get(domain.assigned_user_attribute))
                entry_dict["assigned_user_raw"] = _decode_text(raw_assigned_user)
                yield entry_dict

            controls = [
                c for c in serverctrls if c.controlType == SimplePagedResultsControl.controlType
            ]
            if not controls or not controls[0].cookie:
                break
            page_control.cookie = controls[0].cookie
    finally:
        conn.unbind_s()


def resolve_assigned_user(domain, conn, user_dn):
    """Resolve a user DN (e.g. managedBy) to name/login/email, best-effort."""
    if not user_dn:
        return "", "", ""
    try:
        _rtype, results = conn.search_s(
            user_dn,
            ldap.SCOPE_BASE,
            "(objectClass=user)",
            ["cn", "sAMAccountName", "mail"],
        )
    except ldap.LDAPError:
        return "", "", ""

    if not results or not results[0][0]:
        return "", "", ""

    _dn, attrs = results[0]
    name = _decode_text(_first(attrs.get("cn")))
    login = _decode_text(_first(attrs.get("sAMAccountName")))
    email = _decode_text(_first(attrs.get("mail")))
    return name, login, email
