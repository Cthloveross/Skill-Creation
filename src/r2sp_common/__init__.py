"""Pure shared protocol core for dataset-specific R2SP experiments."""

from .fingerprint import (
    CodeFileFingerprint,
    CodeFingerprint,
    fingerprint_code_roots,
    fingerprint_code_tree,
)
from .isolation import (
    ResetAttestation,
    ResetAttestationError,
    ResetCheck,
    ResetEvidence,
    RuntimeIdentity,
    attest_reset,
)
from .protocol import Page, PublicTrace, SearchEvent, SearchHit, TraceEvent
from .retrieval import (
    DeterministicBM25,
    InvalidQueryError,
    OpenBudgetExceeded,
    PageNotExposedError,
    RetrievalError,
    RetrieverClosedError,
    SearchBudgetExceeded,
    SessionWebRetriever,
    tokenize,
)
from .status import RunStatus, parse_run_status

__all__ = [
    "CodeFileFingerprint",
    "CodeFingerprint",
    "DeterministicBM25",
    "InvalidQueryError",
    "OpenBudgetExceeded",
    "Page",
    "PageNotExposedError",
    "PublicTrace",
    "ResetAttestation",
    "ResetAttestationError",
    "ResetCheck",
    "ResetEvidence",
    "RetrievalError",
    "RetrieverClosedError",
    "RunStatus",
    "RuntimeIdentity",
    "SearchBudgetExceeded",
    "SearchEvent",
    "SearchHit",
    "SessionWebRetriever",
    "TraceEvent",
    "attest_reset",
    "fingerprint_code_roots",
    "fingerprint_code_tree",
    "parse_run_status",
    "tokenize",
]

__version__ = "0.1.0"
