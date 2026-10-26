import threading

from app.feeds import FeedJobs


def capture_jobs(jobs, monkeypatch):
    pending = []
    monkeypatch.setattr(jobs.executor, 'submit', lambda fn, *args: pending.append((fn, args)))
    return pending


def test_overdue_scheduler_refreshes_immediately_and_updates_persistent_status(rig, monkeypatch):
    client, _, db, _, _ = rig
    jobs = client.app.state.jobs
    jobs.interval = 43200
    monkeypatch.setattr('app.feeds.time.time', lambda: 100000)
    db.execute('UPDATE feeds SET last_attempt=50000')
    pending = capture_jobs(jobs, monkeypatch)
    checked = []

    def refresh(feed_id, url):
        checked.append(feed_id)
        db.execute('UPDATE feeds SET last_attempt=100000,last_success=100000 WHERE id=?', (feed_id,))
        return 0

    monkeypatch.setattr(jobs, 'refresh', refresh)
    assert jobs.next_refresh_at() == 93200
    jobs._schedule_once()
    assert len(pending) == 1
    assert db.get('rss_last_full_refresh') == 100000
    fn, args = pending.pop()
    fn(*args)
    assert checked == [1, 2]
    status = client.get('/api/v1/config').json()
    assert status['rss_last_refresh']['finished'] == 100000
    assert status['rss_last_refresh']['state'] == 'done'
    assert status['rss_next_refresh'] == 143200
    assert status['rss_scheduler_running'] is False  # fixture disables background workers


def test_restart_keeps_deadline_and_does_not_wait_a_new_full_interval(rig, monkeypatch):
    _, _, db, _, _ = rig
    db.put('rss_last_full_refresh', 100000)
    restarted = FeedJobs(db, interval=43200)
    try:
        pending = capture_jobs(restarted, monkeypatch)
        monkeypatch.setattr('app.feeds.time.time', lambda: 100120)
        assert restarted.next_refresh_at() == 143200
        assert restarted._schedule_once() == 60
        assert not pending
        monkeypatch.setattr('app.feeds.time.time', lambda: 143200)
        restarted._schedule_once()
        assert len(pending) == 1
        assert db.get('rss_last_full_refresh') == 143200
    finally:
        restarted.close()


def test_single_feed_does_not_postpone_full_pass_and_running_job_is_not_queued_again(rig, monkeypatch):
    client, _, db, _, _ = rig
    jobs = client.app.state.jobs
    pending = capture_jobs(jobs, monkeypatch)
    monkeypatch.setattr('app.feeds.time.time', lambda: 100000)
    db.put('rss_last_full_refresh', 90000)
    jobs.start_job('refresh', 1)
    assert db.get('rss_last_full_refresh') == 90000
    assert jobs.next_refresh_at() == 93600
    jobs._schedule_once()
    assert len(pending) == 1
    assert not jobs.refresh_again
    db.execute("UPDATE jobs SET state='done',finished=100000")
    jobs._schedule_once()
    assert len(pending) == 2
    assert db.get('rss_last_full_refresh') == 100000


def test_manual_full_refresh_rearms_schedule(rig, monkeypatch):
    client, _, db, _, _ = rig
    jobs = client.app.state.jobs
    capture_jobs(jobs, monkeypatch)
    monkeypatch.setattr('app.feeds.time.time', lambda: 100000)
    db.put('rss_last_full_refresh', 99000)
    assert client.post('/api/v1/feeds/refresh').status_code == 202
    assert jobs.next_refresh_at() == 103600


def test_never_checked_feed_is_due_and_local_only_catalog_is_not_scheduled(rig, monkeypatch):
    client, _, db, _, _ = rig
    jobs = client.app.state.jobs
    pending = capture_jobs(jobs, monkeypatch)
    monkeypatch.setattr('app.feeds.time.time', lambda: 100000)
    assert jobs.next_refresh_at() == 100000
    jobs._schedule_once()
    assert len(pending) == 1
    db.execute("UPDATE feeds SET kind='local'")
    assert jobs.next_refresh_at() is None
    jobs._schedule_once()
    assert len(pending) == 1


def test_scheduler_logs_temporary_errors_and_continues(rig, monkeypatch, caplog):
    jobs = rig[0].app.state.jobs
    recovered = threading.Event()
    calls = []
    waits = []

    def step():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('temporary scheduling error')
        recovered.set()
        jobs.stop_event.set()
        return 60

    def wait(delay):
        waits.append(delay)
        return jobs.stop_event.is_set()

    monkeypatch.setattr(jobs, '_schedule_once', step)
    monkeypatch.setattr(jobs.stop_event, 'wait', wait)
    jobs.start_scheduler()
    jobs.scheduler.join(timeout=2)
    assert recovered.is_set()
    assert not jobs.scheduler.is_alive()
    assert len(calls) == 2
    assert waits == [60, 60]
    assert 'konnte nicht geplant werden' in caplog.text


def test_interrupted_full_refresh_is_retried_before_the_next_interval(rig, monkeypatch):
    client, _, db, _, _ = rig
    jobs = client.app.state.jobs
    pending = capture_jobs(jobs, monkeypatch)
    monkeypatch.setattr('app.feeds.time.time', lambda: 100000)
    job_id = jobs.start_job('refresh')
    assert jobs.next_refresh_at() == 103600
    from app.db import Database
    Database(db.path)
    assert db.one('SELECT state FROM jobs WHERE id=?', (job_id,))['state'] == 'interrupted'
    assert jobs.next_refresh_at() == 100000
    jobs._schedule_once()
    assert len(pending) == 2
    assert db.get('rss_last_full_refresh_job') != job_id
