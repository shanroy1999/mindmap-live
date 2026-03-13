"""MindMap Live backend test suite.

Test modules
------------
conftest.py     — shared fixtures (engine, session, HTTP clients, factories)
test_models.py  — ORM model persistence, constraints, and cascade behaviour
test_health.py  — GET /health endpoint (happy path + DB-unreachable path)

Superseded
----------
test_nodes.py   — scaffold stub; uses the old sync TestClient and the pre-async
                  database layer.  Replace once the nodes router is migrated to
                  AsyncSession.
"""
