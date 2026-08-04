"""HTTP layer: FastAPI routes, schemas, and the app factory.

Thin by design. Routes parse, call a service, and return a declared `response_model`.
All draft logic lives in `popacta.domain`; all file reading in `popacta.ingest`.
"""
