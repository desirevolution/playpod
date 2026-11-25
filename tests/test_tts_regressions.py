"""Regressions for the five URL-based TTS handoff reliability fixes."""
import logging
import threading
from unittest.mock import Mock

import requests

from app.config import Settings
from app.integrations import Notifications
from test_announcements import announcement, AUDIO


def test_title_generation_does_not_block_controls_and_checkpoints_live_position(announcement):
    _, player, _, mpd, notifications = announcement
    player.start_episode(1, announce=False)
    mpd.elapsed = 100
    player.sync()
    entered, release = threading.Event(), threading.Event()

    def generate(text):
        entered.set()
        assert release.wait(3)
        return AUDIO

    notifications.title_audio.side_effect = generate
    task = threading.Thread(target=lambda: player.start_episode(2))
    task.start()
    try:
        assert entered.wait(1)
        # The outgoing podcast keeps playing while Node-RED is preparing audio.
        mpd.elapsed = 108
        # Queue editing is an independent control and must not wait on the TTS request.
        complete = threading.Event()
        edit = threading.Thread(target=lambda: (player.enqueue(3), complete.set()))
        edit.start()
        assert complete.wait(.6)
        edit.join(1)
    finally:
        release.set()
        task.join(3)
    assert not task.is_alive()
    assert player.episode(1)['position'] == 108
    assert player.saved['intro']['episode_id'] == 2


def test_new_playback_command_wins_over_stale_title_generation(announcement):
    _, player, _, mpd, notifications = announcement
    player.start_episode(1, announce=False)
    entered, release = threading.Event(), threading.Event()

    def generate(_):
        entered.set()
        assert release.wait(3)
        return AUDIO

    notifications.title_audio.side_effect = generate
    task = threading.Thread(target=lambda: player.start_episode(2))
    task.start()
    try:
        assert entered.wait(1)
        player.start_episode(3, announce=False)
        assert mpd.song['file'].endswith('/3.mp3')
    finally:
        release.set()
        task.join(3)
    assert not task.is_alive()
    assert player.saved['episode_id'] == 3
    assert not player.saved.get('intro')
    assert mpd.song['file'].endswith('/3.mp3')


def test_external_mpd_source_change_during_title_generation_is_respected(announcement):
    _, player, _, mpd, notifications = announcement
    player.start_episode(1, announce=False)
    entered, release = threading.Event(), threading.Event()

    def generate(_):
        entered.set()
        assert release.wait(3)
        return AUDIO

    notifications.title_audio.side_effect = generate
    task = threading.Thread(target=lambda: player.start_episode(2))
    task.start()
    try:
        assert entered.wait(1)
        # This is an external MPD client, not a PlayPod API operation.
        mpd.start('http://example.test/3.mp3', 22)
    finally:
        release.set()
        task.join(3)
    assert not task.is_alive()
    assert mpd.song['file'].endswith('/3.mp3')
    assert player.saved['episode_id'] == 3
    assert not player.saved.get('intro')

def test_nested_api_player_lock_released_during_tts(announcement):
    client, player, _, mpd, notifications = announcement
    entered, release = threading.Event(), threading.Event()

    def generate(_):
        entered.set()
        assert release.wait(3)
        return AUDIO

    notifications.title_audio.side_effect = generate
    task = threading.Thread(target=lambda: client.post('/api/v1/episodes/play', json={'episode_id': 1}))
    task.start()
    try:
        assert entered.wait(1)
        # This API call itself takes the same lock recursively via sync()/play().
        complete = threading.Event()
        command = threading.Thread(target=lambda: (player.start_episode(3, announce=False), complete.set()))
        command.start()
        assert complete.wait(1)
        command.join(2)
    finally:
        release.set()
        task.join(3)
    assert not task.is_alive()
    assert mpd.song['file'].endswith('/3.mp3')


def test_mode_generation_does_not_block_and_is_cancelled_by_new_source(announcement):
    _, player, _, mpd, notifications = announcement
    player.start_episode(1, announce=False)
    entered, release = threading.Event(), threading.Event()

    def generate(text):
        entered.set()
        assert release.wait(3)
        return AUDIO

    notifications.title_audio.side_effect = generate
    task = threading.Thread(target=lambda: player.set_mode(True))
    task.start()
    try:
        assert entered.wait(1)
        player.start_episode(2, announce=False)
    finally:
        release.set()
        task.join(3)
    assert not task.is_alive()
    assert player.mode and not player.saved.get('intro')
    assert mpd.song['file'].endswith('/2.mp3')


def test_title_zero_second_audio_falls_back_to_episode(announcement, caplog):
    _, player, _, mpd, _ = announcement
    original_start = mpd.start

    def start(url, position=0, **kwargs):
        result = original_start(url, position, **kwargs)
        mpd.duration = 0 if url == AUDIO else 1200
        return result

    mpd.start = start
    with caplog.at_level(logging.WARNING):
        player.start_episode(1)
    assert player.saved['episode_id'] == 1
    assert not player.saved.get('intro')
    assert mpd.song['file'].endswith('/1.mp3')
    assert '0 Sekunden' in caplog.text


def test_custom_zero_second_audio_fails_job_and_restores_podcast(announcement):
    _, player, _, mpd, _ = announcement
    player.start_episode(1, announce=False)
    original_start = mpd.start

    def start(url, position=0, **kwargs):
        result = original_start(url, position, **kwargs)
        mpd.duration = 0 if url == AUDIO else 1200
        return result

    mpd.start = start
    job_id = player.announce('Kurze Testansage')['id']
    assert player.process_announcements()
    assert player.announcement_status(job_id)['state'] == 'failed'
    assert player.saved['episode_id'] == 1
    assert mpd.song['file'].endswith('/1.mp3')


def test_long_tts_uses_decoded_audio_duration_not_default_timeout(announcement):
    _, player, _, mpd, notifications = announcement
    notifications.settings.tts_playback_timeout_seconds = 60
    now = [1000.]
    player.clock = lambda: now[0]
    original_start = mpd.start

    def start(url, position=0, **kwargs):
        result = original_start(url, position, **kwargs)
        mpd.duration = 300 if url == AUDIO else 1200
        return result

    mpd.start = start
    id_ = player.announce('Langer Text. ' * 130)['id']
    assert player.process_announcements()
    intro = player.saved['intro']
    assert intro['timeout_remaining'] >= 315
    now[0] += 120
    player.sync()
    assert player.announcement_status(id_)['state'] == 'playing'
    assert player.saved.get('intro')


def test_http_tts_failures_log_status_and_timeout_without_content(monkeypatch, caplog):
    notifications = Notifications(Settings(tts_audio_url='http://private.test/tts', tts_timeout_seconds=.5))
    response = Mock()
    response.status_code = 503
    error = requests.HTTPError('secret response body', response=response)
    monkeypatch.setattr('app.integrations.requests.post', Mock(side_effect=error))
    with caplog.at_level(logging.WARNING):
        assert notifications.title_audio('Private Nachricht') is None
    assert 'HTTP-Status 503' in caplog.text
    assert 'secret response body' not in caplog.text
    assert 'Private Nachricht' not in caplog.text

    caplog.clear()
    monkeypatch.setattr('app.integrations.requests.post', Mock(side_effect=requests.Timeout('sensitive URL')))
    with caplog.at_level(logging.WARNING):
        assert notifications.title_audio('Private Nachricht') is None
    assert 'HTTP-Timeout nach 0.5 Sekunden' in caplog.text
    assert 'sensitive URL' not in caplog.text
