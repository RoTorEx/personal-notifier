#!/bin/sh
set -eu
umask 077
python -c 'import uuid; print(uuid.uuid4().hex)' > /tmp/personal-notifier-instance
exec /app/.venv/bin/personal-notifier "$@"
