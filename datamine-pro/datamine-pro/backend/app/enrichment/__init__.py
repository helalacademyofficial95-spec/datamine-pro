"""Website discovery, ownership verification and B2C matching.

Design rules (see docs in each module):
- Nothing is invented. A URL is only reported when it was fetched and inspected.
- "Verified" requires evidence on the site itself (its own legal notice showing the
  company's registration number). Everything weaker is labelled accordingly.
- Core logic (text, pagefacts, discovery, verify, classify, pipeline) uses only the
  Python standard library so it is cheap on free hosting and testable offline.
"""

ENRICHMENT_VERSION = 2

# Per-field verification vocabulary shared by backend and frontend.
VERIFIED = "Verified"
PARTIAL = "Partially Verified"
UNVERIFIED = "Unverified"
NOT_FOUND = "Not Found"
NOT_APPLICABLE = "Not Applicable"
