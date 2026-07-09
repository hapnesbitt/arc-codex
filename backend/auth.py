"""
auth.py — Shared Local Authentication Blueprint
================================================
Drop-in Flask blueprint for all Arc stacks.
Uses Redis DB 5 as shared user store — credentials work across
arc-codex, huntaegis, neetwatch, vid, and any future stack.

Redis DB 5 keyspace:
  arc:users              SET   — all registered usernames
  arc:user:{username}    HASH  — password_hash, email, is_admin, created
  arc:email:{email}      STR   — username (reverse lookup for reset)
  arc:reset:{token}      STR   — username (TTL 3600s)

Registration in main.py:
  from auth import auth_bp, init_auth
  app.register_blueprint(auth_bp)
  init_auth(app, redis_password=REDIS_PASSWORD, domain="arc-codex.com")

Routes added:
  GET/POST /auth/register
  GET/POST /auth/login
  GET      /auth/logout
  GET/POST /auth/forgot
  GET/POST /auth/reset/<token>
  GET      /auth/admin/users          (admin only)
  POST     /auth/admin/change_password (admin only)
  POST     /auth/admin/toggle_admin    (admin only)
  POST     /auth/admin/delete_user     (admin only)
"""

import os
import re
import secrets
import logging
from datetime import datetime, timezone
from functools import wraps

import redis
from flask import (Blueprint, current_app, flash, redirect, render_template_string,
                   request, session, url_for, jsonify)
from werkzeug.security import check_password_hash, generate_password_hash

# --- Rate limiting (audit finding #9) ---
# Flask-Limiter, Redis-backed, keyed on the real client IP. ProxyFix
# (installed in main.py) rewrites request.remote_addr to the rightmost
# XFF entry, which Caddy — with no `trusted_proxies` block — repopulates
# authoritatively from the direct TCP peer. That means the client cannot
# spoof identity by sending X-Forwarded-For themselves.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Storage URI is read at init_auth() time via app.config, not here — the
# limiter is instantiated with an in-memory fallback so decorators can
# attach at import time; init_auth() rebinds it to Redis before the app
# serves any requests.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=[],
    headers_enabled=True,
)

# Defense-in-depth against Jinja template metacharacters landing in
# user-controlled fields that are later rendered. The real fix is the
# structured-template rewrite of admin_users/reset (never build HTML by
# f-string then hand it to Jinja), but rejecting these characters at
# registration means an attacker can't sneak template payloads into
# usernames/emails even if a future edit accidentally reintroduces the
# unsafe rendering pattern.
_TEMPLATE_META = re.compile(r'\{\{|\}\}|\{%|%\}')

log = logging.getLogger("auth")

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ── Module-level Redis client (DB 5) ─────────────────────────────────────────
_auth_redis: redis.Redis | None = None
_domain: str = "arc-codex.com"
_from_addr: str = "ross@arc-codex.com"

AUTH_DB = 5
USER_SET = "arc:users"

def init_auth(app, redis_password: str = None, redis_host: str = "localhost",
              redis_port: int = 6379, domain: str = "arc-codex.com",
              from_addr: str = None):
    """Call once after app creation to wire up shared auth Redis + limiter."""
    global _auth_redis, _domain, _from_addr
    _domain = domain
    _from_addr = from_addr or f"ross@{domain}"

    # Bind Flask-Limiter to this app. Use the same Redis instance as the
    # auth store (DB 5) so limiter state lives with the credentials it
    # protects and gets included in the shared-auth backup path. If Redis
    # is unreachable, Flask-Limiter falls back to in-memory storage — auth
    # rate limits still apply per-worker, just aren't shared across the
    # gunicorn pool. That's a degraded state, not an open door.
    if redis_password:
        auth_redis_uri = f"redis://:{redis_password}@{redis_host}:{redis_port}/{AUTH_DB}"
    else:
        auth_redis_uri = f"redis://{redis_host}:{redis_port}/{AUTH_DB}"
    app.config.setdefault("RATELIMIT_STORAGE_URI", auth_redis_uri)
    app.config.setdefault("RATELIMIT_KEY_PREFIX", "arc:auth:limiter")
    try:
        limiter.init_app(app)
        log.info("✅ Auth rate-limiter attached (Redis DB %d)", AUTH_DB)
    except Exception as e:
        log.error("❌ Rate-limiter init failed, using in-memory fallback: %s", e)

    try:
        _auth_redis = redis.Redis(
            host=redis_host, port=redis_port,
            password=redis_password, db=AUTH_DB,
            decode_responses=True, socket_connect_timeout=5
        )
        _auth_redis.ping()
        log.info("✅ Auth Redis connected (DB %d)", AUTH_DB)

        # Bootstrap admin if no users exist
        if not _auth_redis.exists(USER_SET):
            admin_pass = os.getenv("ARC_ADMIN_PASSWORD", "")
            if admin_pass:
                _create_user("admin", admin_pass, email=os.getenv("ALERT_TO", "rossnesbitt@gmail.com"), is_admin=True)
                log.info("✅ Admin user bootstrapped")
    except Exception as e:
        log.error("❌ Auth Redis connection failed: %s", e)
        _auth_redis = None


def _r() -> redis.Redis | None:
    return _auth_redis


def _create_user(username: str, password: str, email: str = "", is_admin: bool = False) -> bool:
    r = _r()
    if not r:
        return False
    pipe = r.pipeline()
    pipe.sadd(USER_SET, username)
    pipe.hset(f"arc:user:{username}", mapping={
        "password_hash": generate_password_hash(password),
        "email": email,
        "is_admin": "1" if is_admin else "0",
        "created": datetime.now(timezone.utc).isoformat(),
    })
    if email:
        pipe.set(f"arc:email:{email.lower()}", username)
    pipe.execute()
    return True


# ── Decorators ────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


# ── Email helper (calls mailer's local Postfix) ───────────────────────────────
def _send_reset_email(to_addr: str, token: str, domain: str):
    """Send password reset email via local Postfix."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    reset_url = f"https://{domain}/auth/reset/{token}"

    text = f"""Password Reset Request

Click the link below to reset your password:
{reset_url}

This link expires in 1 hour. If you didn't request this, ignore this email.

— {domain}
"""
    html = f"""<html><body style="font-family:monospace;background:#0f172a;color:#e2e8f0;padding:24px;">
<h2 style="color:#f59e0b;">Password Reset</h2>
<p>Click below to reset your password:</p>
<p><a href="{reset_url}" style="color:#f59e0b;">{reset_url}</a></p>
<p style="color:#64748b;font-size:12px;">Expires in 1 hour. If you didn't request this, ignore this email.</p>
<hr style="border-color:#334155;">
<p style="color:#475569;font-size:12px;">{domain}</p>
</body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = _from_addr
        msg["To"] = to_addr
        msg["Subject"] = f"Password Reset — {domain}"
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP("localhost", 25, timeout=10) as smtp:
            smtp.sendmail(_from_addr, [to_addr], msg.as_string())
        log.info("✅ Reset email sent to %s", to_addr)
        return True
    except Exception as e:
        log.error("❌ Reset email failed: %s", e)
        return False


# ── Templates (inline — no template files needed) ─────────────────────────────
_BASE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — {{ domain }}</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body { margin: 0; font-family: 'Segoe UI', system-ui, sans-serif;
         background: #0f172a; color: #e2e8f0; min-height: 100vh;
         display: flex; align-items: center; justify-content: center; padding: 24px; }
  .card { width: 100%; max-width: 420px; background: rgba(15,23,42,.8);
          border: 1px solid rgba(148,163,184,.15); border-radius: 16px;
          padding: 40px; backdrop-filter: blur(12px);
          box-shadow: 0 0 40px rgba(251,191,36,.05); }
  .logo { text-align: center; margin-bottom: 8px; }
  .logo-title { font-size: 28px; font-weight: 900; color: #f59e0b;
                letter-spacing: -.03em; }
  .logo-sub { font-size: 12px; color: #475569; margin-top: 2px; }
  h1 { font-size: 18px; font-weight: 700; color: #f1f5f9; margin: 24px 0 4px;
       text-align: center; }
  .sub { font-size: 13px; color: #64748b; margin: 0 0 24px; text-align: center; }
  label { display: block; font-size: 12px; font-weight: 600; color: #94a3b8;
          text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
  .input-wrap { position: relative; margin-bottom: 16px; }
  input[type=text], input[type=password], input[type=email] {
    width: 100%; padding: 11px 14px; background: rgba(30,41,59,.8);
    border: 1px solid rgba(148,163,184,.2); border-radius: 8px;
    color: #f1f5f9; font-size: 14px; outline: none;
    transition: border-color .2s, box-shadow .2s; }
  input:focus { border-color: rgba(251,191,36,.5);
                box-shadow: 0 0 0 3px rgba(251,191,36,.1); }
  .pw-wrap { position: relative; }
  .pw-wrap input { padding-right: 44px; width: 100%; }
  .pw-toggle { position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
               background: none; border: none; cursor: pointer; color: #64748b;
               font-size: 16px; padding: 4px; line-height: 1; }
  .pw-toggle:hover { color: #94a3b8; }
  .btn { width: 100%; padding: 12px; margin-top: 8px;
         background: linear-gradient(135deg, #f59e0b, #d97706);
         border: none; border-radius: 8px; color: #0f172a;
         font-size: 14px; font-weight: 700; cursor: pointer;
         transition: opacity .2s, transform .1s; }
  .btn:hover { opacity: .9; transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }
  .btn-danger { background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; }
  .btn-secondary { background: rgba(148,163,184,.1); border: 1px solid rgba(148,163,184,.2);
                   color: #94a3b8; border-radius: 8px; }
  .btn-secondary:hover { background: rgba(148,163,184,.15); opacity: 1; }
  .links { margin-top: 20px; text-align: center; font-size: 13px; color: #64748b; }
  .links a { color: #f59e0b; text-decoration: none; font-weight: 500; }
  .links a:hover { text-decoration: underline; }
  .divider { display: flex; align-items: center; gap: 12px; margin: 20px 0;
             color: #334155; font-size: 12px; }
  .divider::before, .divider::after { content: ''; flex: 1;
    height: 1px; background: rgba(148,163,184,.1); }
  .flash { padding: 10px 14px; margin-bottom: 16px; font-size: 13px;
           border-radius: 8px; border-left: 3px solid; }
  .flash-danger  { background: rgba(239,68,68,.08);  border-color: #ef4444;  color: #fca5a5; }
  .flash-success { background: rgba(34,197,94,.08);  border-color: #22c55e;  color: #86efac; }
  .flash-warning { background: rgba(245,158,11,.08); border-color: #f59e0b;  color: #fde68a; }
  .flash-info    { background: rgba(96,165,250,.08); border-color: #60a5fa;  color: #bfdbfe; }
  /* Admin table */
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 16px; }
  th { text-align: left; padding: 8px 12px; color: #64748b; text-transform: uppercase;
       letter-spacing: .06em; border-bottom: 1px solid rgba(148,163,184,.1); }
  td { padding: 8px 12px; border-bottom: 1px solid rgba(148,163,184,.05); color: #94a3b8; }
  td:first-child { color: #e2e8f0; }
  .badge { padding: 2px 8px; font-size: 10px; border-radius: 4px; border: 1px solid; }
  .badge-admin { color: #f59e0b; border-color: rgba(245,158,11,.4); background: rgba(245,158,11,.08); }
  .badge-user  { color: #64748b; border-color: rgba(148,163,184,.2); }
  .admin-card { max-width: 960px; }
  .page-title { font-size: 18px; font-weight: 700; color: #f1f5f9; margin: 0 0 4px; }
  .input-sm { padding: 6px 10px; font-size: 12px; }
  .btn-sm { padding: 6px 14px; font-size: 11px; width: auto; margin-top: 0; border-radius: 6px; }
  .row-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
</style>
<script>
function togglePw(id) {
  var el = document.getElementById(id);
  var btn = el.nextElementSibling;
  if (el.type === 'password') { el.type = 'text'; btn.textContent = '🙈'; }
  else { el.type = 'password'; btn.textContent = '👁'; }
}
</script>
</head>
<body>
<div class="card {{ extra_class or '' }}">
  <div class="logo">
    <a href="/" style="display:block;text-align:center;text-decoration:none;">
      <div class="logo-title">Arc Codex</div>
      <div class="logo-sub">Intelligence infrastructure for the independent mind</div>
    </a>
  </div>
  {% for cat, msg in get_flashed_messages(with_categories=true) %}
    <div class="flash flash-{{ cat }}">{{ msg }}</div>
  {% endfor %}
  {{ content | safe }}
</div>
</body></html>
"""

def _render(title, content, chrome_label=None, extra_class="", domain=None):
    from flask import render_template_string, get_flashed_messages
    d = domain or _domain
    from flask import Response
    html = render_template_string(_BASE,
        title=title, content=content, domain=d,
        chrome_label=chrome_label, extra_class=extra_class,
        get_flashed_messages=get_flashed_messages)
    return Response(html, mimetype='text/html')


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10/hour;3/minute", methods=["POST"])
def register():
    if session.get("username"):
        return redirect("/")
    if request.method == "POST":
        r = _r()
        if not r:
            flash("Registration unavailable — database offline.", "danger")
        else:
            username = request.form.get("username", "").strip().lower()
            email    = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm  = request.form.get("confirm_password", "")
            if not all([username, email, password, confirm]):
                flash("All fields are required.", "danger")
            elif len(username) < 3:
                flash("Username must be at least 3 characters.", "danger")
            elif len(password) < 8:
                flash("Password must be at least 8 characters.", "danger")
            elif password != confirm:
                flash("Passwords do not match.", "danger")
            elif _TEMPLATE_META.search(username) or _TEMPLATE_META.search(email):
                flash("Username and email cannot contain '{{', '}}', '{%', or '%}'.", "danger")
            elif r.sismember(USER_SET, username):
                flash("Username already taken.", "danger")
            elif r.exists(f"arc:email:{email}"):
                flash("Email already registered.", "danger")
            else:
                _create_user(username, password, email=email)
                log.info("New user registered: %s (%s)", username, email)
                flash("Account created! Please log in.", "success")
                return redirect("/")

    content = """
<h1>Create Account</h1>
<p class="sub">One account for all Arc stacks</p>
<form method="post">
  <label>Username</label>
  <input type="text" name="username" required minlength="3" placeholder="choose a username" autocomplete="username">
  <label>Email</label>
  <input type="email" name="email" required placeholder="for password resets">
  <label>Password</label>
  <div class="pw-wrap">
    <input type="password" id="pw1" name="password" required minlength="8" placeholder="min 8 characters" autocomplete="new-password">
    <button type="button" class="pw-toggle" onclick="togglePw('pw1')">👁</button>
  </div>
  <label>Confirm Password</label>
  <div class="pw-wrap">
    <input type="password" id="pw2" name="confirm_password" required minlength="8" placeholder="confirm password" autocomplete="new-password">
    <button type="button" class="pw-toggle" onclick="togglePw('pw2')">👁</button>
  </div>
  <button type="submit" class="btn">Create Account</button>
</form>
<div class="links">
  Already have an account? <a href="{{ url_for('auth.login') }}">Log in</a>
</div>
"""
    from flask import render_template_string
    content = render_template_string(content)
    return _render("Register", content, chrome_label=f"{_domain}://auth/register")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5/minute", methods=["POST"])
def login():
    if session.get("username"):
        return redirect("/")
    if request.method == "POST":
        r = _r()
        if not r:
            flash("Login unavailable — database offline.", "danger")
        else:
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            try:
                if not r.sismember(USER_SET, username):
                    flash("Invalid credentials.", "danger")
                else:
                    user = r.hgetall(f"arc:user:{username}")
                    if not user or not check_password_hash(user.get("password_hash", ""), password):
                        flash("Invalid credentials.", "danger")
                    else:
                        session["username"] = username
                        session["is_admin"] = user.get("is_admin") == "1"
                        session.permanent = True
                        log.info("User logged in: %s", username)
                        next_url = request.args.get("next", "/")
                        return redirect(next_url if next_url.startswith("/") else "/")
            except redis.exceptions.RedisError as e:
                log.error("Redis error login %s: %s", username, e)
                flash("Login error — please try again.", "danger")

    content = """
<h1>Welcome Back</h1>
<p class="sub">Sign in to Arc Codex</p>
<form method="post">
  <label>Username</label>
  <input type="text" name="username" required placeholder="your username" autocomplete="username">
  <label>Password</label>
  <div class="pw-wrap">
    <input type="password" id="pw" name="password" required placeholder="your password" autocomplete="current-password">
    <button type="button" class="pw-toggle" onclick="togglePw('pw')">👁</button>
  </div>
  <button type="submit" class="btn">Log In</button>
</form>
<div class="divider">or</div>
<a href="/api/auth/signin" class="btn btn-secondary" style="display:block;text-align:center;text-decoration:none;padding:11px;">
  Continue with GitHub
</a>
<div class="links" style="margin-top:16px">
  <a href="{{ url_for('auth.forgot') }}">Forgot password?</a>
  &nbsp;·&nbsp;
  <a href="{{ url_for('auth.register') }}">Create account</a>
</div>
"""
    from flask import render_template_string
    content = render_template_string(content)
    return _render("Log In", content, chrome_label=f"{_domain}://auth/login")


@auth_bp.route("/logout")
def logout():
    username = session.pop("username", "unknown")
    session.clear()
    log.info("User logged out: %s", username)
    flash("Logged out successfully.", "info")
    return redirect("/")


@auth_bp.route("/forgot", methods=["GET", "POST"])
@limiter.limit("3/hour", methods=["POST"])
def forgot():
    if request.method == "POST":
        r = _r()
        email = request.form.get("email", "").strip().lower()
        if r and email:
            username = r.get(f"arc:email:{email}")
            if username:
                token = secrets.token_urlsafe(32)
                r.setex(f"arc:reset:{token}", 3600, username)
                _send_reset_email(email, token, _domain)
        # Always show same message — don't reveal whether email exists
        flash("If that email is registered, a reset link is on its way.", "info")
        return redirect("/")

    content = """
<h1>Reset Password</h1>
<p class="sub">Enter your email to receive a reset link</p>
<form method="post">
  <label>Email Address</label>
  <input type="email" name="email" required placeholder="your registered email">
  <button type="submit" class="btn">Send Reset Link</button>
</form>
<div class="links"><a href="{{ url_for('auth.login') }}">Back to login</a></div>
"""
    from flask import render_template_string
    content = render_template_string(content)
    return _render("Forgot Password", content)


@auth_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    r = _r()
    if not r:
        flash("Service unavailable.", "danger")
        return redirect("/")

    username = r.get(f"arc:reset:{token}")
    if not username:
        flash("Reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            r.hset(f"arc:user:{username}", "password_hash", generate_password_hash(password))
            r.delete(f"arc:reset:{token}")
            log.info("Password reset for user: %s", username)
            flash("Password updated! Please log in.", "success")
            return redirect("/")

    # username comes from the arc:reset:<token> lookup (i.e., it was
    # user-supplied at registration). Pass as a Jinja variable so autoescape
    # HTML-escapes any markup that slipped past the register-time filter.
    _RESET_FORM = """
<h1>&gt; New Password</h1>
<p class="sub">// resetting password for: {{ username }}</p>
<form method="post">
  <label>New Password</label>
  <div class="pw-wrap">
    <input type="password" id="pw1" name="password" required minlength="8" placeholder="min 8 characters" autocomplete="new-password">
    <button type="button" class="pw-toggle" onclick="togglePw('pw1')">👁</button>
  </div>
  <label>Confirm Password</label>
  <div class="pw-wrap">
    <input type="password" id="pw2" name="confirm_password" required minlength="8" placeholder="confirm password" autocomplete="new-password">
    <button type="button" class="pw-toggle" onclick="togglePw('pw2')">👁</button>
  </div>
  <button type="submit" class="btn">Set Password</button>
</form>
"""
    content = render_template_string(_RESET_FORM, username=username)
    return _render("Reset Password", content)


# ── Admin routes ──────────────────────────────────────────────────────────────

# Admin dashboard template. User-supplied fields (username, email) are
# expanded as Jinja variables — NEVER built into HTML by f-string — so
# Jinja autoescape turns any {{...}} / {%...%} / <script>… payloads into
# inert text. If you edit this template, do not switch any user-derived
# value to |safe.
_ADMIN_USERS_TMPL = """
<h1 class="page-title">&gt; User Admin</h1>
<p class="sub">// {{ users|length }} registered users — {{ domain }}</p>
<table>
  <thead><tr>
    <th>Username</th><th>Email</th><th>Role</th><th>Created</th><th>Actions</th>
  </tr></thead>
  <tbody>
  {% for u in users %}
    <tr>
      <td>{{ u.username }}</td>
      <td>{{ u.email or '—' }}</td>
      <td>
        {% if u.is_admin %}
          <span class="badge badge-admin">admin</span>
        {% else %}
          <span class="badge badge-user">user</span>
        {% endif %}
      </td>
      <td>{{ (u.created or '—')[:10] }}</td>
      <td>
        <form method="post" action="{{ url_for('auth.admin_change_password') }}" style="display:inline">
          <div class="row-form">
            <input type="hidden" name="username" value="{{ u.username }}">
            <input type="password" class="input-sm" name="new_password" placeholder="new password" minlength="8" required style="width:160px">
            <button type="submit" class="btn btn-sm">&gt; set</button>
          </div>
        </form>
        &nbsp;
        <form method="post" action="{{ url_for('auth.admin_toggle_admin') }}" style="display:inline">
          <input type="hidden" name="username" value="{{ u.username }}">
          <button type="submit" class="btn btn-sm">{{ 'revoke admin' if u.is_admin else 'make admin' }}</button>
        </form>
        &nbsp;
        <form method="post" action="{{ url_for('auth.admin_delete_user') }}" style="display:inline"
              onsubmit="return confirm('Delete user?')">
          <input type="hidden" name="username" value="{{ u.username }}">
          <button type="submit" class="btn btn-sm btn-danger">&gt; delete</button>
        </form>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
<div class="links" style="margin-top:24px"><a href="/">← back to feed</a></div>
"""


@auth_bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    r = _r()
    if not r:
        flash("Database unavailable.", "danger")
        return redirect("/")

    usernames = sorted(r.smembers(USER_SET))
    users = []
    for uname in usernames:
        info = r.hgetall(f"arc:user:{uname}")
        users.append({
            "username": uname,
            "email": info.get("email", ""),
            "is_admin": info.get("is_admin") == "1",
            "created": info.get("created", ""),
        })

    content = render_template_string(_ADMIN_USERS_TMPL, users=users, domain=_domain)
    return _render("User Admin", content, extra_class="admin-card",
                   chrome_label=f"{_domain}://auth/admin")


@auth_bp.route("/admin/change_password", methods=["POST"])
@login_required
@admin_required
def admin_change_password():
    r = _r()
    target = request.form.get("username", "")
    new_pass = request.form.get("new_password", "")
    if not r or not target or len(new_pass) < 8:
        flash("Invalid request.", "danger")
    elif not r.sismember(USER_SET, target):
        flash(f'User "{target}" not found.', "danger")
    else:
        r.hset(f"arc:user:{target}", "password_hash", generate_password_hash(new_pass))
        log.info("Admin %s changed password for %s", session.get("username"), target)
        flash(f'Password updated for "{target}".', "success")
    return redirect(url_for("auth.admin_users"))


@auth_bp.route("/admin/toggle_admin", methods=["POST"])
@login_required
@admin_required
def admin_toggle_admin():
    r = _r()
    target = request.form.get("username", "")
    if not r or not target:
        flash("Invalid request.", "danger")
    elif target == session.get("username"):
        flash("Cannot change your own admin status.", "danger")
    elif not r.sismember(USER_SET, target):
        flash(f'User "{target}" not found.', "danger")
    else:
        current = r.hget(f"arc:user:{target}", "is_admin")
        new_val = "0" if current == "1" else "1"
        r.hset(f"arc:user:{target}", "is_admin", new_val)
        action = "revoked from" if new_val == "0" else "granted to"
        log.info("Admin %s %s admin for %s", session.get("username"), action, target)
        flash(f'Admin {action} "{target}".', "success")
    return redirect(url_for("auth.admin_users"))


@auth_bp.route("/admin/delete_user", methods=["POST"])
@login_required
@admin_required
def admin_delete_user():
    r = _r()
    target = request.form.get("username", "")
    if not r or not target:
        flash("Invalid request.", "danger")
    elif target == session.get("username"):
        flash("Cannot delete your own account.", "danger")
    elif not r.sismember(USER_SET, target):
        flash(f'User "{target}" not found.', "danger")
    else:
        email = r.hget(f"arc:user:{target}", "email") or ""
        pipe = r.pipeline()
        pipe.srem(USER_SET, target)
        pipe.delete(f"arc:user:{target}")
        if email:
            pipe.delete(f"arc:email:{email.lower()}")
        pipe.execute()
        log.info("Admin %s deleted user %s", session.get("username"), target)
        flash(f'User "{target}" deleted.', "success")
    return redirect(url_for("auth.admin_users"))


# ── Current user helper ───────────────────────────────────────────────────────
def current_user() -> dict | None:
    """Return current user's Redis hash or None if not logged in."""
    username = session.get("username")
    if not username:
        return None
    r = _r()
    if not r:
        return None
    data = r.hgetall(f"arc:user:{username}")
    if data:
        data["username"] = username
    return data or None
