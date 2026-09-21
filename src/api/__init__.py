"""
Phase 4: FastAPI application layer over the existing ResQAI service.

Layers: routes (thin HTTP) -> schemas (public contract) -> service
(application service: lifecycle, health, catalog) -> resqai_service
(the Phase 3 seam) -> the Phase 1/2/3/3.5 intelligence. See docs/API.md.
"""
