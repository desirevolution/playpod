"""Durable user activity. Call writers inside the catalog/progress transaction."""
import time

RETENTION_SECONDS = 90 * 86400


def prune(conn, now=None):
    conn.execute('DELETE FROM activity WHERE created<?', ((time.time() if now is None else now) - RETENTION_SECONDS,))


def record(conn, kind, *, episode_id=None, feed_id=None, count=1, target='', key=None, now=None):
    now = time.time() if now is None else now
    prune(conn, now)
    if episode_id is not None:
        row = conn.execute('SELECT e.title,f.title,e.feed_id FROM episodes e JOIN feeds f ON f.id=e.feed_id WHERE e.id=?', (episode_id,)).fetchone()
        if not row:
            return
        title, podcast, feed_id = row
    else:
        row = conn.execute('SELECT title FROM feeds WHERE id=?', (feed_id,)).fetchone()
        if not row:
            return
        title, podcast = '', row[0]
    conn.execute('''INSERT OR IGNORE INTO activity(kind,created,episode_id,feed_id,title,podcast,count,target,event_key)
        VALUES(?,?,?,?,?,?,?,?,?)''', (kind, now, episode_id, feed_id, title, podcast, count, target, key))


def listing(db, kind='all', before=None, limit=50):
    clauses, args = [], []
    if kind == 'new':
        clauses.append("a.kind IN ('episode_added','feed_added')")
    elif kind == 'completed':
        clauses.append("a.kind='completed'")
    if before is not None:
        clauses.append('a.id<?')
        args.append(before)
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    with db.connect() as conn:
        prune(conn)
        rows = [dict(row) for row in conn.execute('''SELECT a.id,a.kind,a.created,a.episode_id,a.feed_id,a.count,a.target,
            COALESCE(e.title,a.title) AS title, COALESCE(f.title,a.podcast) AS podcast
            FROM activity a LEFT JOIN episodes e ON e.id=a.episode_id
            LEFT JOIN feeds f ON f.id=a.feed_id''' + where + ' ORDER BY a.id DESC LIMIT ?', (*args, limit + 1))]
    return {'items': rows[:limit], 'next_cursor': rows[limit-1]['id'] if len(rows) > limit else None}
