"""Versioned HTTP contracts. Inputs reject unknown fields instead of ignoring typos."""
from typing import Literal, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LinkInput(Input):
    url: str = Field(min_length=1, max_length=4000)


class FeedDownloadInput(Input):
    ids: list[int] = Field(min_length=1, max_length=1000)


class FeedInput(Input):
    url: str = Field(min_length=1, max_length=4000)
    title: str = Field(default='', max_length=500)
    favorite: bool = False


class ValueBool(Input):
    value: bool


class AnnouncementInput(Input):
    text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def valid_text(self):
        self.text = self.text.strip()
        if not self.text:
            raise ValueError('Ansagetext darf nicht leer sein')
        return self


class AnnouncementResult(BaseModel):
    id: str
    text: str
    state: Literal['queued', 'generating', 'playing', 'done', 'failed', 'cancelled']
    error: str
    created: float
    finished: float | None
    queue_position: int


class ModeInput(Input):
    favorites_only: bool


class SleepDefaultsInput(Input):
    minutes: int = Field(ge=1, le=1440)
    when_queue_empty: Literal['random', 'random_unheard']


class PlaybackInput(Input):
    when_queue_empty: Literal['keep', 'default', 'stop', 'random', 'random_unheard'] = 'keep'
    timer: Literal['keep', 'default', 'preserve'] = Field(default='keep', description='keep startet bei manuellem Start/Fortsetzen/next die gewählte Laufzeit neu; default wählt die konfigurierte Einschlaf-Laufzeit (initial 15 Minuten). preserve behält beim Fortsetzen die Restzeit (UI). Toggle-Pause verändert die Restzeit nicht.')


class SeekInput(Input):
    position_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False, examples=[120])
    offset_seconds: float | None = Field(default=None, allow_inf_nan=False, examples=[30, -30])

    @model_validator(mode='after')
    def exactly_one_position(self) -> Self:
        if (self.position_seconds is None) == (self.offset_seconds is None):
            raise ValueError('Genau position_seconds oder offset_seconds angeben')
        return self


class VolumeInput(Input):
    value: int = Field(ge=0, le=100)


class VolumeAdjustInput(Input):
    delta: int = Field(ge=-100, le=100, examples=[5, -5])


class TimerInput(Input):
    minutes: int = Field(ge=0, le=1440, description='0 deaktiviert den Timer; sonst Laufzeit in Minuten.')


class ExtendInput(Input):
    minutes: int = Field(default=5, ge=1, le=1440)


class EpisodeInput(Input):
    episode_id: int = Field(gt=0)
    from_start: bool = False


class PlayEpisodeInput(EpisodeInput):
    when_queue_empty: Literal['keep', 'default', 'stop', 'random', 'random_unheard'] = 'keep'
    timer: Literal['keep', 'default'] = 'keep'


class OrderInput(Input):
    ids: list[int]
    revision: int


class DeleteInput(Input):
    ids: list[int] = Field(max_length=1000)
    include_temporary: bool = False


class EpisodeResult(BaseModel):
    # Retain catalog metadata (including local media fields) in player snapshots.
    model_config = ConfigDict(extra='allow')
    id: int
    feed_id: int
    title: str
    podcast: str
    url: str
    duration: float
    position: float
    source_type: Literal['audio', 'web']
    bookmarked: int
    completed: int


class TimerResult(BaseModel):
    suspended: bool = False
    enabled: bool
    minutes: float
    remaining: float
    run_active: bool


class PlayerResult(BaseModel):
    when_queue_empty: Literal['stop', 'random', 'random_unheard']
    sleep_mode: bool
    model_config = ConfigDict(extra='allow')
    state: Literal['play', 'pause', 'stop', 'error']
    phase: Literal['announcement', 'episode']
    announcement_kind: Literal['title', 'mode', 'custom'] | None = None
    announcement_text: str = ''
    elapsed: float
    duration: float
    volume: int
    current: EpisodeResult | None
    queue: list[EpisodeResult]
    revision: int
    source_kind: Literal['remote', 'local', 'announcement']
    favorites_only: bool
    error: str
    undo_available: bool
    timer: TimerResult


class QueueAddedResult(BaseModel):
    added: bool
    state: PlayerResult


class JobAccepted(BaseModel):
    job_id: str
    status_url: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[dict] = Field(default_factory=list)


class ErrorResult(BaseModel):
    error: ErrorInfo


class EpisodeListResult(BaseModel):
    items: list[EpisodeResult]
    total: int


class FeedResult(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: int
    url: str
    title: str
    favorite: int
    kind: Literal['rss', 'local', 'links']
    episode_count: int
    error: str


class JobResult(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    kind: str
    state: str
    progress: int
    total: int
    error: str


class DownloadResult(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    episode_id: int
    state: Literal['queued', 'running', 'ready', 'error', 'cancelled', 'cancel_requested', 'missing', 'deleted']
    phase: Literal['download', 'processing']
    received: int
    total: int | None
    error: str


class DownloadAccepted(DownloadResult):
    status_url: str


class DownloadStatusResult(BaseModel):
    enabled: bool
    online: bool
    error: str
    ytdlp_enabled: bool
    storage: dict[str, int]
    items: list[DownloadResult]


class ActivityResult(BaseModel):
    id: int
    kind: Literal['episode_added', 'feed_added', 'completed']
    created: float
    episode_id: int | None
    feed_id: int | None
    title: str
    podcast: str
    count: int
    target: Literal['', 'mpd', 'browser']


class ActivityPageResult(BaseModel):
    items: list[ActivityResult]
    next_cursor: int | None


class ActivityStatusResult(BaseModel):
    latest: int
    unseen: int


class EpisodeLocationResult(BaseModel):
    feed_id: int
    offset: int
