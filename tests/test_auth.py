"""Test del candado de acceso (APP_PASSWORD) usando el harness de Streamlit.

Se setea la variable de entorno directamente (la app lee os.getenv('APP_PASSWORD')).
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

APP = "ui/app.py"


def _has_password_input(at) -> bool:
    return any("Contraseña" in (ti.label or "") for ti in at.text_input)


def test_gate_blocks_without_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    at = AppTest.from_file(APP)
    at.run()
    # con APP_PASSWORD seteada, la app se detiene en el candado (input de contraseña)
    assert _has_password_input(at)
    assert "auth_ok" not in at.session_state


def test_gate_unlocks_with_correct_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    at = AppTest.from_file(APP)
    at.run()
    at.text_input[0].set_value("s3cret").run()
    assert at.session_state["auth_ok"] is True


def test_no_gate_when_password_unset(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    at = AppTest.from_file(APP)
    at.run()
    assert not _has_password_input(at)
    assert not at.exception  # la vista principal carga sin errores (bug del slider incluido)


def test_home_is_default_view(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    at = AppTest.from_file(APP)
    at.run()
    assert at.session_state["view"] == "home"          # abre en Home
    assert any("Home" in (t.value or "") or "Inicio" in (t.value or "") for t in at.title)
    assert not at.exception
