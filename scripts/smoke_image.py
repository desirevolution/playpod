#!/usr/bin/env python3
"""Offline runtime check, runnable inside either image without test dependencies.

Optional --youtube-url performs metadata extraction against a user-selected URL.
All generated files and the test database live in a temporary directory.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.resources
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from urllib.request import Request, urlopen
import wave


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def request(url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, headers={'Content-Type': 'application/json', **(headers or {})})
    return urlopen(req, timeout=5)


def get_json(url, body=None):
    with request(url, body) as response:
        return json.load(response)


def check_runtime():
    from app.ytdlp_runner import javascript_options
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.youtube.jsc._builtin.quickjs import QuickJSJCP

    options = javascript_options()
    assert set(options) == {'quickjs'}, 'This comparison requires QuickJS, not a Node fallback'
    with YoutubeDL({'quiet': True, 'js_runtimes': options}) as ydl:
        runtime = ydl._js_runtimes['quickjs'].info
        assert runtime and runtime.supported and runtime.name == 'quickjs-ng', runtime
        assert runtime.version_tuple >= (0, 12, 0), runtime
        # Execute through yt-dlp's actual QuickJS provider (temporary script,
        # --script flag and stderr handling), not just through qjs -e.
        provider = SimpleNamespace(runtime_info=runtime, logger=logging.getLogger('smoke.quickjs'),
                                   _QJS_MIN_RECOMMENDED=QuickJSJCP._QJS_MIN_RECOMMENDED)
        lib = importlib.resources.files('yt_dlp_ejs.yt.solver').joinpath('lib.min.js').read_text()
        core = importlib.resources.files('yt_dlp_ejs.yt.solver').joinpath('core.min.js').read_text()
        script = lib + '\nObject.assign(globalThis, lib);\n' + core + '\nconsole.log(JSON.stringify({ok:typeof jsc, n:new Uint8Array([42])[0], b:(2n**10n).toString()}));'
        result = QuickJSJCP._run_js_runtime(provider, script)
        assert json.loads(result) == {'ok': 'function', 'n': 42, 'b': '1024'}, result
        print(f'QuickJS-NG {runtime.version}: yt-dlp provider + bundled EJS scripts OK', flush=True)


def check_app():
    import feedparser
    parsed = feedparser.parse('<rss version="2.0"><channel><title>Smoke</title><item><title>Episode</title><guid>1</guid></item></channel></rss>')
    assert parsed.entries[0].title == 'Episode'

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    with tempfile.TemporaryDirectory(prefix='playpod-smoke-') as temp:
        folder = Path(temp)
        with wave.open(str(folder / 'episode.wav'), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b'\0\0' * 32000)
        source = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=temp))
        source_thread = threading.Thread(target=source.serve_forever, daemon=True)
        source_thread.start()
        port = free_port()
        base = f'http://127.0.0.1:{port}'
        env = {**os.environ, 'SQLITE_PATH': str(folder / 'test.sqlite3'),
               'DOWNLOAD_DIRECTORY': str(folder / 'downloads'), 'MPD_HOST': '', 'MQTT_HOST': '',
               'MEDIA_ROOTS': '{}', 'MEDIA_BASE_URL': '', 'TTS_AUDIO_URL': '',
               'YTDLP_ENABLED': 'true', 'YTDLP_JS_RUNTIME': 'quickjs', 'YTDLP_TIMEOUT': '45'}
        with (folder / 'server.log').open('w+') as log:
            process = subprocess.Popen([sys.executable, '-m', 'app', '--host', '127.0.0.1', '--port', str(port)],
                                       env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        health = get_json(base + '/api/health')
                        break
                    except Exception:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            log.seek(0)
                            raise RuntimeError('App startup failed:\n' + log.read())
                        time.sleep(.1)
                assert health['checks']['mpd'] == 'disabled', health
                assert get_json(base + '/api/v1/state')['when_queue_empty'] == 'stop'
                assert get_json(base + '/manifest.webmanifest')['name'] == 'PlayPod'
                with request(base + '/') as response:
                    assert b'PlayPod' in response.read()
                task = get_json(base + '/api/v1/links', {'url': f'http://127.0.0.1:{source.server_port}/episode.wav'})
                deadline = time.monotonic() + 60
                while True:
                    rows = get_json(base + '/api/v1/downloads')['items']
                    row = next((r for r in rows if r['id'] == task['id']), None)
                    if row and row['state'] in ('ready', 'error', 'cancelled', 'interrupted'):
                        assert row['state'] == 'ready', row
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f'Download timeout: {row}')
                    time.sleep(.2)
                # Verify the actual transcoded file and same-origin browser URL.
                info = get_json(base + f'/api/v1/browser/episodes/{task["episode_id"]}/source')
                assert info['source_kind'] == 'local', info
                with request(base + info['url'], headers={'Range': 'bytes=0-31'}) as response:
                    assert response.status == 206
                    assert len(response.read()) == 32
                files = list((folder / 'downloads').rglob('*.audio'))
                assert files, 'No transcoded MP3 produced'
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name',
                                        '-of', 'json', str(files[0])],
                                       check=True, capture_output=True, text=True, timeout=10)
                media = json.loads(probe.stdout)
                assert float(media['format']['duration']) > 0
                assert media['streams'][0]['codec_name'] == 'mp3', media
                print('API, SQLite, RSS parser, frontend/PWA, yt-dlp child, FFmpeg MP3, local Range streaming: OK', flush=True)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                source.shutdown()
                source.server_close()
                source_thread.join(timeout=2)


def check_youtube(url):
    from app.ytdlp_runner import javascript_options
    from yt_dlp import YoutubeDL
    with YoutubeDL({'quiet': True, 'noplaylist': True, 'skip_download': True,
                    'js_runtimes': javascript_options(), 'socket_timeout': 10,
                    'retries': 0, 'extractor_retries': 0}) as ydl:
        info = ydl.extract_info(url, download=False)
        assert info and info.get('formats'), 'No YouTube formats returned'
        print(f'YouTube metadata/formats: OK ({info["id"]})', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--youtube-url', help='Optional public YouTube video to test; requires Internet')
    args = parser.parse_args()
    check_runtime()
    check_app()
    if args.youtube_url:
        check_youtube(args.youtube_url)


if __name__ == '__main__':
    main()
