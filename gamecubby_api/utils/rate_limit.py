from time import monotonic
from threading import RLock
from fastapi import Request, HTTPException

_rate_state = {}
_rate_lock = RLock()

MAX_FAILS = 3
WINDOW = 30
BLOCK = 60

def check_rate_limit(ip: str, user: str):
    now = monotonic()
    key = (ip, user.lower())
    with _rate_lock:
        rec = _rate_state.get(key, {"fails": [], "blocked": 0})
        if rec["blocked"] > now:
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Try again later.",
                headers={"Retry-After": str(int(rec["blocked"] - now))}
            )
        rec["fails"] = [t for t in rec["fails"] if t >= now - WINDOW]
        _rate_state[key] = rec

def note_fail(ip: str, user: str):
    now = monotonic()
    key = (ip, user.lower())
    with _rate_lock:
        rec = _rate_state.setdefault(key, {"fails": [], "blocked": 0})
        rec["fails"] = [t for t in rec["fails"] if t >= now - WINDOW] + [now]
        if len(rec["fails"]) >= MAX_FAILS:
            rec["blocked"] = now + BLOCK

def note_success(ip: str, user: str):
    key = (ip, user.lower())
    with _rate_lock:
        if key in _rate_state:
            _rate_state[key] = {"fails": [], "blocked": 0}

def client_ip(request: Request) -> str:
    # Trust X-Real-IP set by nginx, or the leftmost address in X-Forwarded-For
    # set by traefik/other proxies, before falling back to the direct connection.
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host or ""
