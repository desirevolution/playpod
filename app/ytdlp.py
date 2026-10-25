"""Cancellable yt-dlp subprocess adapter; network extraction never blocks the player."""
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time


def extract(url, directory, max_bytes, timeout, check, report):
    directory.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'app.ytdlp_runner', url, str(directory), str(max_bytes)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               text=True, encoding='utf-8', errors='replace', start_new_session=True)
    events = queue.Queue(maxsize=32)
    finished = threading.Event()
    def read():
        try:
            for line in process.stdout:
                while not finished.is_set():
                    try:
                        events.put(line[:65536], timeout=.2)
                        break
                    except queue.Full:
                        pass
        finally:
            process.stdout.close()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline, result, error = time.monotonic() + timeout, None, ''
    try:
        while process.poll() is None or not events.empty() or reader.is_alive():
            check()
            if time.monotonic() > deadline:
                raise ValueError('Zeitlimit für yt-dlp überschritten')
            size = sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
            if size > max_bytes * 2 + 16 * 1024**2:
                raise ValueError('Temporäre Dateien überschreiten das Downloadlimit')
            try:
                event = json.loads(events.get(timeout=.2))
            except queue.Empty:
                continue
            if event['event'] == 'progress':
                report(event['received'], event.get('total'), 'download')
            elif event['event'] == 'processing':
                report(None, None, 'processing')
            elif event['event'] == 'ready':
                result = event
            elif event['event'] == 'error':
                error = event['error']
        if process.wait() != 0 or result is None:
            raise ValueError(error or 'yt-dlp hat keine Audiodatei erzeugt')
        path = Path(result['path']).resolve(strict=True)
        if not path.is_relative_to(directory.resolve()) or not path.is_file() or path.stat().st_size > max_bytes:
            raise ValueError('Ungültige oder zu große Audiodatei')
        return path, result
    finally:
        finished.set()
        # Kill the whole group, including FFmpeg/JS children, even after extraction errors.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
        reader.join(timeout=1)
