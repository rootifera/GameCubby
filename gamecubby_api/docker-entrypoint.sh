#!/bin/sh
# Container entrypoint: fix ownership of the shared storage volume, then drop root.
#
# Older installs created /storage as root, so a plain `USER` would lock the app out
# of its own files. Starting as root only for the chown (a no-op once ownership is
# right) keeps existing installs working; the app itself never runs as root.
#
# APP_UID / APP_GID pick the runtime user (default 1000:1000 -- usually the first
# user on the host, so files in ./storage are yours instead of root's).
# If the container is started with an explicit non-root user (`user:` in compose),
# the chown/drop is skipped and the command just runs.
set -e

APP_UID="${APP_UID:-1000}"
APP_GID="${APP_GID:-1000}"

if [ "$(id -u)" = "0" ]; then
    # Some libraries (e.g. Node's os.userInfo) need a passwd entry for the uid.
    if ! getent passwd "$APP_UID" >/dev/null 2>&1; then
        echo "app:x:${APP_UID}:${APP_GID}:app:/tmp:/usr/sbin/nologin" >> /etc/passwd
    fi

    for dir in /storage /app/storage; do
        [ -d "$dir" ] || continue
        if [ -n "$(find "$dir" -not -user "$APP_UID" -print -quit 2>/dev/null)" ]; then
            echo "[entrypoint] fixing ownership of $dir (uid:gid ${APP_UID}:${APP_GID})"
            chown -R "${APP_UID}:${APP_GID}" "$dir" || echo "[entrypoint] WARNING: could not chown $dir"
        fi
    done

    export HOME=/tmp
    exec setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups --no-new-privs -- "$@"
fi

exec "$@"
