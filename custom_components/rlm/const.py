"""Constants for RLM."""

DOMAIN = "rlm"
VERSION = "0.1.0"
STORE_VERSION = 1
STORE_KEY = "rlm.active_leases"

EVENT_LEASE_STARTED = "rlm_lease_started"
EVENT_LEASE_COMPLETED = "rlm_lease_completed"
EVENT_LEASE_CANCELLED = "rlm_lease_cancelled"
EVENT_LEASE_RESUMED = "rlm_lease_resumed"
EVENT_LEASE_EXPIRED = "rlm_lease_expired"
EVENT_LEASE_RECOVERED = "rlm_lease_recovered"
EVENT_LEASE_ERROR = "rlm_lease_error"
