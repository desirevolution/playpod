import pytest

from app.ytdlp_runner import javascript_options


def test_quickjs_is_default_and_uses_resolved_binary(monkeypatch):
    monkeypatch.delenv('YTDLP_JS_RUNTIME', raising=False)
    monkeypatch.setattr('app.ytdlp_runner.shutil.which', lambda name: '/bin/qjs' if name == 'qjs' else None)
    assert javascript_options() == {'quickjs': {'path': '/bin/qjs'}}


def test_node_is_an_explicit_native_install_fallback(monkeypatch):
    monkeypatch.setenv('YTDLP_JS_RUNTIME', ' Node ')
    monkeypatch.setattr('app.ytdlp_runner.shutil.which', lambda name: '/bin/node' if name == 'node' else None)
    assert javascript_options() == {'node': {'path': '/bin/node'}}


@pytest.mark.parametrize('runtime', ['quickjs', 'node'])
def test_missing_runtime_has_actionable_error(monkeypatch, runtime):
    monkeypatch.setenv('YTDLP_JS_RUNTIME', runtime)
    monkeypatch.setattr('app.ytdlp_runner.shutil.which', lambda _: None)
    with pytest.raises(ValueError, match='fehlt im PATH'):
        javascript_options()


@pytest.mark.parametrize('runtime', ['', 'deno', 'qjs;echo broken'])
def test_invalid_runtime_rejected(monkeypatch, runtime):
    monkeypatch.setenv('YTDLP_JS_RUNTIME', runtime)
    with pytest.raises(ValueError, match='muss quickjs oder node sein'):
        javascript_options()
