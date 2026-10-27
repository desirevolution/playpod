"""One URL in an isolated child process, with bounded JSON progress on stdout."""
import json
import os
import shutil
from pathlib import Path
import sys
import time


def emit(event, **data):
    print(json.dumps({'event': event, **data}), flush=True)


def javascript_options():
    runtime = os.getenv('YTDLP_JS_RUNTIME', 'quickjs').strip().lower()
    if runtime not in ('quickjs', 'node'):
        raise ValueError('YTDLP_JS_RUNTIME muss quickjs oder node sein')
    executable = shutil.which('qjs' if runtime == 'quickjs' else 'node')
    if not executable:
        raise ValueError(f'JavaScript-Laufzeit {runtime} fehlt im PATH (YTDLP_JS_RUNTIME)')
    return {runtime: {'path': executable}}


def run(url, directory, max_bytes):
    from yt_dlp import YoutubeDL
    from yt_dlp.postprocessor import PostProcessor
    from yt_dlp.utils import DownloadError

    last = 0
    def progress(data):
        nonlocal last
        received = int(data.get('downloaded_bytes') or 0)
        total = data.get('total_bytes') or data.get('total_bytes_estimate')
        if received > max_bytes or (total and total > max_bytes):
            raise DownloadError('Datei überschreitet DOWNLOAD_MAX_BYTES')
        if time.monotonic() - last >= .5 or data.get('status') == 'finished':
            emit('progress', received=received, total=int(total) if total else None)
            last = time.monotonic()

    class Logger:
        def debug(self, message): pass
        def warning(self, message): pass
        def error(self, message): emit('error', error=str(message)[:1000])

    class Completed(PostProcessor):
        def run(self, info):
            emit('ready', path=info['filepath'], title=str(info.get('title') or '')[:1000],
                 description=str(info.get('description') or '')[:20000],
                 duration=info.get('duration'), thumbnail=info.get('thumbnail') or '')
            return [], info

    options = {
        'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True,
        'lazy_playlist': True, 'extract_flat': 'in_playlist',
        'logger': Logger(), 'cachedir': False, 'socket_timeout': 20,
        'retries': 2, 'fragment_retries': 2, 'concurrent_fragment_downloads': 1,
        'max_filesize': max_bytes, 'outtmpl': str(Path(directory).resolve() / 'audio.%(ext)s'),
        'progress_hooks': [progress],
        'postprocessor_hooks': [lambda data: emit('processing')],
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'js_runtimes': javascript_options(),
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info or info.get('_type') in ('playlist', 'multi_video') or info.get('entries') is not None:
            raise ValueError('Bitte einen einzelnen Episoden-/Videolink statt einer Playlist oder eines Kanals angeben')
        from .youtube import allowed
        if not allowed(info):
            raise ValueError('Shorts sowie laufende oder geplante Livestreams werden nicht importiert')
        ydl.add_post_processor(Completed(), when='after_move')
        ydl.process_ie_result(info, download=True)


def catalog(url):
    from yt_dlp import YoutubeDL
    # Flat extraction reads catalog metadata/thumbnails without audio or per-video formats.
    options = {'quiet': True, 'skip_download': True, 'extract_flat': True,
               'ignoreerrors': False, 'cachedir': False, 'socket_timeout': 20,
               'retries': 2, 'js_runtimes': javascript_options()}
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info or info.get('_type') not in ('playlist', 'multi_video'):
            raise ValueError('Bitte eine YouTube-Playlist oder einen Kanal angeben')
        entries = []
        for item in info.get('entries') or []:
            if not item:
                raise ValueError('YouTube-Sammlung konnte nicht vollständig gelesen werden')
            # Channel roots can produce nested tab playlists: /videos is normalized by caller.
            if item.get('entries') is not None:
                raise ValueError('Bitte den Videos-Bereich des Kanals verwenden')
            entries.append({key: item.get(key) for key in
                ('id','url','webpage_url','title','duration','timestamp','release_timestamp',
                 'thumbnails','thumbnail','live_status','is_live','was_live','media_type','availability')})
        if not entries and (info.get('playlist_count') or info.get('n_entries') or 0) > 0:
            raise ValueError('YouTube meldet Videos, aber die Eintragsliste ist leer. Bitte erneut aktualisieren.')
        emit('catalog', title=info.get('title') or url,
             thumbnails=info.get('thumbnails') or [], thumbnail=info.get('thumbnail') or '', entries=entries)


if __name__ == '__main__':
    try:
        if sys.argv[1] == '--catalog':
            catalog(sys.argv[2])
        else:
            run(sys.argv[1], sys.argv[2], int(sys.argv[3]))
    except Exception as exc:
        emit('error', error=str(exc)[:1000] or 'yt-dlp konnte den Link nicht herunterladen')
        sys.exit(1)
