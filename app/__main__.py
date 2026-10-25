import argparse
import logging
import os
import uvicorn
from . import __version__

parser = argparse.ArgumentParser(description="PlayPod SQLite podcast player")
parser.add_argument("--version", action="version", version=__version__)
parser.add_argument("--host", default="0.0.0.0")
parser.add_argument("--port", type=int, default=9393)
args = parser.parse_args()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# python-mpd2 logs every polling connection at INFO; retain its warnings/errors.
logging.getLogger("mpd").setLevel(logging.WARNING)
uvicorn.run("app.api:create_app", factory=True, host=args.host, port=args.port, workers=1,
            access_log=os.getenv("ACCESS_LOG", "false").lower() in ("1", "true", "yes"))
