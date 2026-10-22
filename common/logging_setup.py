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


class _ActionLoggingMiddleware:
    """ASGI middleware logging each request that changes the bench state (any method
    but GET). The request body is captured while the endpoint reads it (not read in
    advance, which blocks the endpoint with older Starlette versions), and the response
    while it is sent."""

    def __init__(self, app, logger: logging.Logger):
        self.app = app
        self.logger = logger

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] in ('GET', 'HEAD', 'OPTIONS'):
            await self.app(scope, receive, send)
            return
        client = scope.get('client')
        query = scope.get('query_string', b'').decode(errors='replace')
        target = scope['path'] + (f'?{query}' if query else '')
        body, response, status = [], [], {}
        started = False
        t0 = time.monotonic()

        def action():
            text = b''.join(body).decode(errors='replace')
            return (f"{scope['method']} {target}" + (f' {text}' if text else '')
                    + f" from {client[0] if client else '?'}")

        async def receive_logged():
            nonlocal started
            message = await receive()
            if message['type'] == 'http.request':
                body.append(message.get('body', b''))
                if not message.get('more_body', False) and not started:
                    started = True
                    self.logger.info('%s: started', action())
            return message

        async def send_logged(message):
            if message['type'] == 'http.response.start':
                status['code'] = message['status']
            elif message['type'] == 'http.response.body':
                response.append(message.get('body', b''))
            await send(message)

        headers = dict(scope.get('headers') or [])
        if headers.get(b'content-length', b'0') == b'0' and b'transfer-encoding' not in headers:
            # no body to wait for: the action starts now
            started = True
            self.logger.info('%s: started', action())
        try:
            await self.app(scope, receive_logged, send_logged)
        except Exception:
            self.logger.exception('%s: failed after %.2f s', action(), time.monotonic() - t0)
            raise
        content = b''.join(response)
        try:
            result = json.loads(content)
        except ValueError:
            result = content.decode(errors='replace')
        code = status.get('code', 0)
        level = logging.INFO if code < 400 else logging.ERROR
        self.logger.log(level, '%s: HTTP %d in %.2f s -> %s', action(), code, time.monotonic() - t0, result)


def add_action_logging(app, logger: logging.Logger):
    """Log each request that changes the bench state (any method but GET), when it
    starts and when it ends: client IP, endpoint, parameters, result or error, duration."""
    app.add_middleware(_ActionLoggingMiddleware, logger=logger)
