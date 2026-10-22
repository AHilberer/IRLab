"""Persistent logging for the device servers.

Each server logs to the console and to its own file `<log dir>/<server name>.log`,
rotated every night (one file per day is kept, for LOG_BACKUP_DAYS days). The log
directory is `logs/` at the repository root, or $IRLAB_LOG_DIR.

`add_action_logging(app, logger)` logs every request that changes the bench state
(any method but GET): client IP, endpoint, parameters, result or error, duration.
"""
import json
import logging
import logging.handlers
import os
import time
from pathlib import Path

from fastapi import Request, Response

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_FORMAT = '%(asctime)s %(levelname)-7s %(name)s: %(message)s'
LOG_BACKUP_DAYS = 365


def get_log_dir() -> Path:
    return Path(os.environ.get('IRLAB_LOG_DIR') or REPO_ROOT / 'logs')


def setup_logging(server_name: str) -> logging.Logger:
    """Return the logger of a server (named `server_name`), writing to the console
    and to `<log dir>/<server_name>.log`. Child loggers (e.g. `<server_name>.serial`)
    use the same outputs."""
    logger = logging.getLogger(server_name)
    if logger.handlers:            # already configured (module imported twice)
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False       # do not duplicate lines through uvicorn's root logger
    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_dir = get_log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_dir / f'{server_name}.log', when='midnight', backupCount=LOG_BACKUP_DAYS, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as e:
        logger.error('Cannot write log files in %s (%s): logging to the console only', log_dir, e)
    return logger


def add_action_logging(app, logger: logging.Logger):
    """Log each request that changes the bench state (any method but GET), when it
    starts and when it ends: client IP, endpoint, parameters, result or error, duration."""

    @app.middleware('http')
    async def log_actions(request: Request, call_next):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return await call_next(request)
        client = request.client.host if request.client else '?'
        target = request.url.path + (f'?{request.url.query}' if request.url.query else '')
        body = (await request.body()).decode(errors='replace')
        action = f'{request.method} {target}' + (f' {body}' if body else '') + f' from {client}'
        logger.info('%s: started', action)
        t0 = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception('%s: failed after %.2f s', action, time.monotonic() - t0)
            raise
        content = b''.join([chunk async for chunk in response.body_iterator])
        duration = time.monotonic() - t0
        try:
            result = json.loads(content)
        except ValueError:
            result = content.decode(errors='replace')
        level = logging.INFO if response.status_code < 400 else logging.ERROR
        logger.log(level, '%s: HTTP %d in %.2f s -> %s', action, response.status_code, duration, result)
        return Response(content=content, status_code=response.status_code,
                        headers=dict(response.headers), media_type=response.media_type)
