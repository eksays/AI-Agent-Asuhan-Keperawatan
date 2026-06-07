from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import os

from lab_config import LAB_FEATURE_ACTIVATION_STATUS, LAB_NAMESPACE, ensure_approved_fixture_root, synthetic_lab_enabled
from security_controls import SANDBOX_DEFAULT_API_KEYS, is_placeholder_secret, is_weak_secret


APP_MODES = {"clinical_sandbox", "controlled_pilot", "production"}
SAFETY_NOTICE = "Clinical sandbox — AI-generated suggestions require nurse review."
UNSUPPORTED_NOTICE = "Unsupported or unverified features are disabled."

PRODUCTION_PREREQUISITES = (
    "OUTBOUND_PHI_FIREWALL_VERIFIED",
    "CLINICAL_SCHEMA_VALIDATION_VERIFIED",
    "REGISTRY_GOVERNANCE_VERIFIED",
    "MERMAID_XSS_TESTS_VERIFIED",
    "UPLOAD_ISOLATION_VERIFIED",
)


@dataclass(frozen=True)
class AppConfig:
    app_mode: str
    feature_external_llm: bool
    feature_ebp_external_search: bool
    feature_clinical_photo_analysis: bool
    feature_mermaid_pathway_rendering: bool
    allow_unsafe_external_llm_for_local_debug: bool
    frontend_origins: tuple[str, ...]
    shopee_base_url: str
    director_bootstrap: str
    director_enrollment_enabled: bool
    cdss_secret_key: str
    api_auth_keys: tuple[str, ...]
    session_ttl_sec: int
    session_idle_timeout_sec: int
    session_max_active: int
    rate_limit_window_sec: int
    rate_limit_max_keys: int
    mfa_failure_limit: int
    mfa_failure_window_sec: int
    mfa_lockout_sec: int
    trusted_proxy_hosts: tuple[str, ...]
    harvest_interval_sec: int
    harvest_topics: tuple[str, ...]
    unpaywall_email: str
    upload_max_bytes: int
    upload_max_filename_length: int
    upload_max_extracted_chars: int
    upload_max_pdf_pages: int
    upload_max_docx_entries: int
    upload_max_docx_total_uncompressed_bytes: int
    upload_max_docx_single_entry_uncompressed_bytes: int
    upload_max_docx_compression_ratio: float
    upload_parser_timeout_sec: int
    upload_max_parser_result_bytes: int
    audit_ledger_hmac_key: str
    audit_ledger_key_id: str
    audit_ledger_path: str
    synthetic_lab_mode: bool
    synthetic_data_only: bool
    synthetic_lab_fixture_root: str
    synthetic_lab_trace_ttl_sec: int
    synthetic_lab_trace_max_runs: int
    synthetic_lab_trace_max_stages: int
    synthetic_lab_trace_max_document_ids: int
    synthetic_lab_trace_max_metadata_bytes: int

    @property
    def external_llm_enabled(self) -> bool:
        return self.feature_external_llm or self.allow_unsafe_external_llm_for_local_debug

    @property
    def ebp_external_search_enabled(self) -> bool:
        return self.feature_ebp_external_search and self.external_llm_enabled


def _bool_env(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default

def _bounded_int_env(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    value = _int_env(env, name, default)
    if value < minimum or value > maximum:
        return default
    return value

def _float_env(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in (raw or "").split(",") if item.strip())


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    source = os.environ if env is None else env
    app_mode = (source.get("APP_MODE") or "clinical_sandbox").strip().lower()
    if app_mode not in APP_MODES:
        raise RuntimeError(f"Invalid APP_MODE: {app_mode!r}")

    allow_debug = _bool_env(source, "ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG")
    if allow_debug and app_mode != "clinical_sandbox":
        raise RuntimeError("ALLOW_UNSAFE_EXTERNAL_LLM_FOR_LOCAL_DEBUG is only valid in clinical_sandbox mode.")

    missing = tuple(name for name in PRODUCTION_PREREQUISITES if not _bool_env(source, name))
    if app_mode == "production" and missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Production mode is disabled until safety prerequisites are explicitly verified: {joined}")

    origins = _csv(source.get("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"))
    topics = _csv(source.get("HARVEST_TOPICS", "nursing care,clinical nursing,evidence based nursing"))
    api_keys = _csv(source.get('CDSS_API_KEYS', ','.join(SANDBOX_DEFAULT_API_KEYS)))
    cdss_secret = source.get('CDSS_SECRET_KEY', '').strip()
    audit_ledger_key = source.get('AUDIT_LEDGER_HMAC_KEY', '').strip()
    audit_ledger_key_id = (source.get('AUDIT_LEDGER_KEY_ID') or 'audit-ledger-local-v1').strip()
    audit_ledger_path = source.get('AUDIT_LEDGER_PATH', '').strip()
    trusted_proxies = _csv(source.get('TRUSTED_PROXY_HOSTS', ''))
    synthetic_lab_mode = _bool_env(source, 'SYNTHETIC_LAB_MODE')
    synthetic_data_only = _bool_env(source, 'SYNTHETIC_DATA_ONLY')
    if (synthetic_lab_mode or synthetic_data_only) and app_mode != 'clinical_sandbox':
        raise RuntimeError('Synthetic integration lab flags are only valid in clinical_sandbox mode.')
    if synthetic_lab_mode and not synthetic_data_only:
        raise RuntimeError('SYNTHETIC_LAB_MODE requires SYNTHETIC_DATA_ONLY=true.')
    feature_external_llm = _bool_env(source, "FEATURE_EXTERNAL_LLM")
    feature_ebp_external_search = _bool_env(source, "FEATURE_EBP_EXTERNAL_SEARCH")
    feature_clinical_photo_analysis = _bool_env(source, "FEATURE_CLINICAL_PHOTO_ANALYSIS")
    feature_mermaid_pathway_rendering = _bool_env(source, "FEATURE_MERMAID_PATHWAY_RENDERING")
    harvest_interval_sec = _int_env(source, "HARVEST_INTERVAL_SEC", 0)
    fixture_root = ensure_approved_fixture_root(source.get(
        'SYNTHETIC_LAB_FIXTURE_ROOT',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests', 'fixtures', 'synthetic_lab'),
    ))
    if synthetic_lab_mode and synthetic_data_only:
        incompatible = []
        if feature_external_llm:
            incompatible.append('FEATURE_EXTERNAL_LLM')
        if feature_ebp_external_search:
            incompatible.append('FEATURE_EBP_EXTERNAL_SEARCH')
        if feature_clinical_photo_analysis:
            incompatible.append('FEATURE_CLINICAL_PHOTO_ANALYSIS')
        if feature_mermaid_pathway_rendering:
            incompatible.append('FEATURE_MERMAID_PATHWAY_RENDERING')
        if harvest_interval_sec > 0:
            incompatible.append('HARVEST_INTERVAL_SEC')
        if incompatible:
            raise RuntimeError('Synthetic integration lab profile is offline-only; incompatible setting(s): ' + ', '.join(incompatible))
    if '*' in origins and app_mode != 'clinical_sandbox':
        raise RuntimeError('Wildcard CORS origins are not allowed outside clinical_sandbox mode.')
    if app_mode in {'controlled_pilot', 'production'}:
        if not api_keys or any(is_weak_secret(key, 20) for key in api_keys):
            raise RuntimeError('Controlled pilot and production modes require explicit strong CDSS_API_KEYS.')
        if is_weak_secret(cdss_secret, 32):
            raise RuntimeError('Controlled pilot and production modes require a strong CDSS_SECRET_KEY.')
        if is_placeholder_secret(source.get('DIRECTOR_BOOTSTRAP', '')):
            raise RuntimeError('DIRECTOR_BOOTSTRAP must not be a placeholder in controlled pilot or production mode.')
        if is_weak_secret(audit_ledger_key, 32):
            raise RuntimeError('Controlled pilot and production modes require a strong AUDIT_LEDGER_HMAC_KEY.')
    if audit_ledger_path and is_weak_secret(audit_ledger_key, 32):
        raise RuntimeError('Persistent audit ledger storage requires a strong AUDIT_LEDGER_HMAC_KEY.')
    if is_placeholder_secret(audit_ledger_key_id):
        raise RuntimeError('AUDIT_LEDGER_KEY_ID must not be a placeholder value.')

    return AppConfig(
        app_mode=app_mode,
        feature_external_llm=feature_external_llm,
        feature_ebp_external_search=feature_ebp_external_search,
        feature_clinical_photo_analysis=feature_clinical_photo_analysis,
        feature_mermaid_pathway_rendering=feature_mermaid_pathway_rendering,
        allow_unsafe_external_llm_for_local_debug=allow_debug,
        api_auth_keys=api_keys,
        session_ttl_sec=_int_env(source, 'SESSION_TTL_SEC', 3600),
        session_idle_timeout_sec=_int_env(source, 'SESSION_IDLE_TIMEOUT_SEC', 900),
        session_max_active=_int_env(source, 'SESSION_MAX_ACTIVE', 1000),
        rate_limit_window_sec=_int_env(source, 'RATE_LIMIT_WINDOW_SEC', 60),
        rate_limit_max_keys=_int_env(source, 'RATE_LIMIT_MAX_KEYS', 2048),
        mfa_failure_limit=_int_env(source, 'MFA_FAILURE_LIMIT', 5),
        mfa_failure_window_sec=_int_env(source, 'MFA_FAILURE_WINDOW_SEC', 300),
        mfa_lockout_sec=_int_env(source, 'MFA_LOCKOUT_SEC', 300),
        trusted_proxy_hosts=trusted_proxies,
        frontend_origins=origins,
        shopee_base_url=source.get("SHOPEE_BASE_URL", "https://openrouter.ai/api/v1"),
        director_bootstrap=source.get("DIRECTOR_BOOTSTRAP", ""),
        director_enrollment_enabled=_bool_env(source, "DIRECTOR_ENROLLMENT_ENABLED"),
        cdss_secret_key=source.get("CDSS_SECRET_KEY", "").strip(),
        harvest_interval_sec=harvest_interval_sec,
        harvest_topics=topics,
        upload_max_bytes=_int_env(source, 'UPLOAD_MAX_BYTES', 10 * 1024 * 1024),
        upload_max_filename_length=_int_env(source, 'UPLOAD_MAX_FILENAME_LENGTH', 180),
        upload_max_extracted_chars=_int_env(source, 'UPLOAD_MAX_EXTRACTED_CHARS', 50_000),
        upload_max_pdf_pages=_int_env(source, 'UPLOAD_MAX_PDF_PAGES', 30),
        upload_max_docx_entries=_int_env(source, 'UPLOAD_MAX_DOCX_ENTRIES', 100),
        upload_max_docx_total_uncompressed_bytes=_int_env(source, 'UPLOAD_MAX_DOCX_TOTAL_UNCOMPRESSED_BYTES', 5 * 1024 * 1024),
        upload_max_docx_single_entry_uncompressed_bytes=_int_env(source, 'UPLOAD_MAX_DOCX_SINGLE_ENTRY_UNCOMPRESSED_BYTES', 2 * 1024 * 1024),
        upload_max_docx_compression_ratio=_float_env(source, 'UPLOAD_MAX_DOCX_COMPRESSION_RATIO', 100.0),
        upload_parser_timeout_sec=_int_env(source, 'UPLOAD_PARSER_TIMEOUT_SEC', 20),
        upload_max_parser_result_bytes=_int_env(source, 'UPLOAD_MAX_PARSER_RESULT_BYTES', 100 * 1024),
        audit_ledger_hmac_key=audit_ledger_key,
        audit_ledger_key_id=audit_ledger_key_id,
        audit_ledger_path=audit_ledger_path,
        synthetic_lab_mode=synthetic_lab_mode,
        synthetic_data_only=synthetic_data_only,
        synthetic_lab_fixture_root=fixture_root,
        synthetic_lab_trace_ttl_sec=_bounded_int_env(source, 'SYNTHETIC_LAB_TRACE_TTL_SEC', 600, 30, 3600),
        synthetic_lab_trace_max_runs=_bounded_int_env(source, 'SYNTHETIC_LAB_TRACE_MAX_RUNS', 128, 1, 1000),
        synthetic_lab_trace_max_stages=_bounded_int_env(source, 'SYNTHETIC_LAB_TRACE_MAX_STAGES', 16, 1, 64),
        synthetic_lab_trace_max_document_ids=_bounded_int_env(source, 'SYNTHETIC_LAB_TRACE_MAX_DOCUMENT_IDS', 32, 0, 256),
        synthetic_lab_trace_max_metadata_bytes=_bounded_int_env(source, 'SYNTHETIC_LAB_TRACE_MAX_METADATA_BYTES', 8192, 512, 65536),
        unpaywall_email=source.get("UNPAYWALL_EMAIL", "cdss.keperawatan@example.com"),
    )


CONFIG = load_config()


def build_capabilities(cfg: AppConfig = CONFIG) -> dict:
    debug_warning = " Unsafe local debug override is active; never use with real patient data."
    external_reason = (
        "Enabled only because unsafe local debug override is active." + debug_warning
        if cfg.allow_unsafe_external_llm_for_local_debug
        else "Explicitly enabled by server configuration. Use only after outbound PHI firewall verification."
        if cfg.feature_external_llm
        else "Disabled until outbound PHI firewall verification passes."
    )
    ebp_reason = (
        "Explicitly enabled by server configuration after external LLM enablement."
        if cfg.ebp_external_search_enabled
        else "Disabled until de-identified concept-query enforcement passes."
    )
    return {
        "synthetic_lab_enabled": synthetic_lab_enabled(cfg),
        "synthetic_data_only": cfg.synthetic_data_only,
        "lab_namespace": LAB_NAMESPACE,
        "lab_external_provider_enabled": False,
        "lab_feature_activation_status": LAB_FEATURE_ACTIVATION_STATUS if synthetic_lab_enabled(cfg) else "disabled",
        "app_mode": cfg.app_mode,
        "safety_notice": SAFETY_NOTICE,
        "unsupported_notice": UNSUPPORTED_NOTICE,
        "capabilities": {
            "external_llm": {"enabled": cfg.external_llm_enabled, "reason": external_reason},
            "ebp_external_search": {"enabled": cfg.ebp_external_search_enabled, "reason": ebp_reason},
            "clinical_photo_analysis": {
                "enabled": cfg.feature_clinical_photo_analysis,
                "reason": "Validated OCR or vision analysis is not implemented."
                if not cfg.feature_clinical_photo_analysis
                else "Explicitly enabled by server configuration.",
            },
            "mermaid_pathway_rendering": {
                "enabled": cfg.feature_mermaid_pathway_rendering,
                "reason": "Disabled until strict SVG sanitization and XSS regression tests pass."
                if not cfg.feature_mermaid_pathway_rendering
                else "Explicitly enabled by server configuration.",
            },
            "sdki_authoritative_grounding": {
                "enabled": False,
                "reason": "Registry approval, provenance, and quarantine workflow are incomplete.",
            },
            "slki": {"enabled": False, "reason": "Approved registry is unavailable."},
            "siki": {"enabled": False, "reason": "Approved registry is unavailable."},
            "nanda": {"enabled": False, "reason": "Approved registry is unavailable."},
            "noc": {"enabled": False, "reason": "Approved registry is unavailable."},
            "nic": {"enabled": False, "reason": "Approved registry is unavailable."},
        },
    }


def capability_enabled(name: str, cfg: AppConfig = CONFIG) -> bool:
    return bool(build_capabilities(cfg)["capabilities"].get(name, {}).get("enabled"))


def capability_reason(name: str, cfg: AppConfig = CONFIG) -> str:
    return str(build_capabilities(cfg)["capabilities"].get(name, {}).get("reason", "Capability is unavailable."))
