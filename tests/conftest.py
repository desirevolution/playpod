from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings


class FakeMPD:
    def __init__(self):
        self.state = "stop"
        self.elapsed = 0
        self.duration = 1200
        self.volume = 55
        self.song = {}
        self.calls = []
        self.unavailable = False
        self.bad_urls = set()
        self.error = ""
        self.counter = 0

    def snapshot(self):
        if self.unavailable:
            raise OSError("offline")
        return {"state": self.state, "elapsed": str(self.elapsed), "duration": str(self.duration), "volume": str(self.volume), "error": self.error}, deepcopy(self.song)

    def start(self, url, position=0, *, paused=False):
        self.calls.append(("start", url, position))
        if self.unavailable or url in self.bad_urls:
            raise OSError("start failed")
        self.counter += 1
        self.song = {"id": str(self.counter), "file": url}
        self.state = "pause" if paused else "play"
        self.elapsed = position
        self.error = ""
        return str(self.counter)

    def call(self, name, *args):
        if self.unavailable:
            raise OSError("offline")
        self.calls.append((name, *args))
        if name == "pause":
            self.state = "pause" if args[0] else "play"
        elif name == "stop":
            self.state = "stop"
        elif name == "seekcur":
            self.elapsed = float(args[0])
        elif name == "clear":
            self.song = {}
            self.state = "stop"
            self.elapsed = 0
            self.duration = 0
        elif name == "setvol":
            self.volume = args[0]


class FakeNotifications:
    client = None
    def __init__(self):
        self.published = []
        self.spoken = []
    def publish(self, state):
        self.published.append(state)
    def title_audio(self, title):
        self.spoken.append(title)
        return None
    def start(self):
        pass
    def stop(self):
        pass


@pytest.fixture
def rig(tmp_path):
    mpd = FakeMPD()
    notifications = FakeNotifications()
    app = create_app(Settings(database=str(tmp_path / "player.sqlite3")), mpd=mpd, notifications=notifications, background=False)
    db = app.state.db
    db.execute("INSERT INTO feeds(id,url,title,favorite) VALUES(1,'http://example.test/rss','Podcast A',1),(2,'http://example.test/rss2','Podcast B',0)")
    for i in range(1, 6):
        db.execute("INSERT INTO episodes(id,feed_id,source_key,title,url,duration) VALUES(?,?,?,?,?,1200)", (i, 1 if i < 4 else 2, str(i), f"Episode {i}", f"http://example.test/{i}.mp3"))
    player = app.state.player
    # Existing playback regressions explicitly exercise the sleep setup.
    player.saved.update(timer_seconds=900, remaining=900, when_queue_empty='random_unheard')
    player.sync()
    with TestClient(app) as client:
        yield client, player, db, mpd, notifications
