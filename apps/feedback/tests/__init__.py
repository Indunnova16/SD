"""Tests del portal público de feedback (apps.feedback).

Paquete (no `tests.py` suelto) para que **pytest los colecte**:
`pyproject.toml` fija `python_files = ["test_*.py", "*_test.py"]`, patrones
que `tests.py` no matchea — los 36 tests de la v1.0 del portal nunca
corrieron en CI. Ver `SPRINTS/PLAN_2026-07-28_71_portal_tickets.md` §2.
"""
