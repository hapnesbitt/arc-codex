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
import secrets
import logging
from datetime import datetime, timezone
from functools import wraps

import redis
from flask import (Blueprint, current_app, flash, redirect, render_template_string,
                   request, session, url_for, jsonify)
from werkzeug.security import check_password_hash, generate_password_hash

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
    """Call once after app creation to wire up shared auth Redis."""
    global _auth_redis, _domain, _from_addr
    _domain = domain
    _from_addr = from_addr or f"ross@{domain}"
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
            return redirect(url_for("auth.login"))
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
  body { margin: 0; font-family: monospace; background: #09090b; color: #e4e4e7; min-height: 100vh;
         display: flex; align-items: center; justify-content: center; padding: 24px; }
  .card { width: 100%; max-width: 420px; border: 1px solid #27272a; background: #09090b; padding: 40px; }
  .chrome { display: flex; align-items: center; gap: 6px; margin-bottom: 28px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; }
  .dot-r { background: rgba(239,68,68,.5); } .dot-y { background: rgba(234,179,8,.5); } .dot-g { background: rgba(34,197,94,.5); }
  .chrome-label { margin-left: 8px; font-size: 11px; color: #52525b; letter-spacing: .1em; }
  h1 { font-size: 22px; font-weight: 900; color: #f4f4f5; margin: 0 0 4px; letter-spacing: -.02em; }
  .sub { font-size: 12px; color: #52525b; margin: 0 0 28px; }
  label { display: block; font-size: 11px; color: #71717a; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 6px; }
  input[type=text], input[type=password], input[type=email] {
    width: 100%; padding: 10px 12px; background: #000; border: 1px solid #3f3f46;
    color: #e4e4e7; font-family: monospace; font-size: 14px; outline: none; margin-bottom: 18px;
    transition: border-color .2s; }
  input:focus { border-color: rgba(34,197,94,.5); }
  .btn { width: 100%; padding: 11px; background: rgba(34,197,94,.1); border: 1px solid rgba(34,197,94,.4);
         color: #4ade80; font-family: monospace; font-size: 13px; font-weight: 700; cursor: pointer;
         letter-spacing: .08em; text-transform: uppercase; transition: all .2s; margin-top: 4px; }
  .btn:hover { background: rgba(34,197,94,.18); }
  .btn-danger { background: rgba(239,68,68,.1); border-color: rgba(239,68,68,.4); color: #f87171; }
  .btn-danger:hover { background: rgba(239,68,68,.18); }
  .links { margin-top: 20px; text-align: center; font-size: 12px; color: #52525b; }
  .links a { color: #4ade80; text-decoration: none; }
  .links a:hover { text-decoration: underline; }
  .flash { padding: 10px 14px; margin-bottom: 18px; font-size: 12px; font-family: monospace; border-left: 2px solid; }
  .flash-danger  { background: rgba(239,68,68,.08);  border-color: rgba(239,68,68,.4);  color: #fca5a5; }
  .flash-success { background: rgba(34,197,94,.08);  border-color: rgba(34,197,94,.4);  color: #86efac; }
  .flash-warning { background: rgba(234,179,8,.08);  border-color: rgba(234,179,8,.4);  color: #fde68a; }
  .flash-info    { background: rgba(96,165,250,.08);  border-color: rgba(96,165,250,.4); color: #bfdbfe; }
  /* Admin table */
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 16px; }
  th { text-align: left; padding: 8px 12px; color: #52525b; text-transform: uppercase;
       letter-spacing: .08em; border-bottom: 1px solid #27272a; }
  td { padding: 8px 12px; border-bottom: 1px solid #18181b; color: #a1a1aa; }
  td:first-child { color: #e4e4e7; }
  .badge { padding: 2px 8px; font-size: 10px; border: 1px solid; }
  .badge-admin { color: #4ade80; border-color: rgba(34,197,94,.4); background: rgba(34,197,94,.08); }
  .badge-user  { color: #71717a; border-color: #3f3f46; }
  .admin-card { max-width: 900px; }
  .page-title { font-size: 18px; font-weight: 900; color: #f4f4f5; margin: 0 0 4px; }
  .input-sm { padding: 6px 10px; font-size: 12px; margin-bottom: 0; }
  .btn-sm { padding: 6px 12px; font-size: 11px; margin-top: 0; width: auto; }
  .row-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
</style>
</head>
<body>
<div class="card {{ extra_class or '' }}">
  <div class="chrome">
    <div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div>
    <span class="chrome-label">{{ chrome_label or (domain + '://auth') }}</span>
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
            elif r.sismember(USER_SET, username):
                flash("Username already taken.", "danger")
            elif r.exists(f"arc:email:{email}"):
                flash("Email already registered.", "danger")
            else:
                _create_user(username, password, email=email)
                log.info("New user registered: %s (%s)", username, email)
                flash("Account created! Please log in.", "success")
                return redirect(url_for("auth.login"))

    content = """
<h1>&gt; Create Account</h1>
<p class="sub">// register — access all arc stacks with one account</p>
<form method="post">
  <label>Username</label>
  <input type="text" name="username" required minlength="3" placeholder="choose a username" autocomplete="username">
  <label>Email</label>
  <input type="email" name="email" required placeholder="for password resets">
  <label>Password</label>
  <input type="password" name="password" required minlength="8" placeholder="min 8 characters" autocomplete="new-password">
  <label>Confirm Password</label>
  <input type="password" name="confirm_password" required minlength="8" placeholder="confirm password" autocomplete="new-password">
  <button type="submit" class="btn">&gt; create account</button>
</form>
<div class="links">
  Already have an account? <a href="{{ url_for('auth.login') }}">Log in</a>
</div>
"""
    from flask import render_template_string
    content = render_template_string(content)
    return _render("Register", content, chrome_label=f"{_domain}://auth/register")


@auth_bp.route("/login", methods=["GET", "POST"])
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
<h1>&gt; Log In</h1>
<p class="sub">// authenticate — one account for all arc stacks</p>
<form method="post">
  <label>Username</label>
  <input type="text" name="username" required placeholder="your username" autocomplete="username">
  <label>Password</label>
  <input type="password" name="password" required placeholder="your password" autocomplete="current-password">
  <button type="submit" class="btn">&gt; log in</button>
</form>
<div class="links">
  <a href="{{ url_for('auth.forgot') }}">Forgot password?</a>
  &nbsp;·&nbsp;
  <a href="{{ url_for('auth.register') }}">Create account</a>
  &nbsp;·&nbsp;
  <a href="/api/auth/signin">GitHub login</a>
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
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot", methods=["GET", "POST"])
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
        return redirect(url_for("auth.login"))

    content = """
<h1>&gt; Reset Password</h1>
<p class="sub">// enter your email to receive a reset link</p>
<form method="post">
  <label>Email Address</label>
  <input type="email" name="email" required placeholder="your registered email">
  <button type="submit" class="btn">&gt; send reset link</button>
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
        return redirect(url_for("auth.login"))

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
            return redirect(url_for("auth.login"))

    content = f"""
<h1>&gt; New Password</h1>
<p class="sub">// resetting password for: {username}</p>
<form method="post">
  <label>New Password</label>
  <input type="password" name="password" required minlength="8" placeholder="min 8 characters" autocomplete="new-password">
  <label>Confirm Password</label>
  <input type="password" name="confirm_password" required minlength="8" placeholder="confirm password" autocomplete="new-password">
  <button type="submit" class="btn">&gt; set password</button>
</form>
"""
    return _render("Reset Password", content)


# ── Admin routes ──────────────────────────────────────────────────────────────

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
        info["username"] = uname
        users.append(info)

    rows = ""
    for u in users:
        is_admin = u.get("is_admin") == "1"
        badge = '<span class="badge badge-admin">admin</span>' if is_admin else '<span class="badge badge-user">user</span>'
        email = u.get("email", "—")
        created = u.get("created", "—")[:10]
        rows += f"""<tr>
          <td>{u['username']}</td>
          <td>{email}</td>
          <td>{badge}</td>
          <td>{created}</td>
          <td>
            <form method="post" action="{url_for('auth.admin_change_password')}" style="display:inline">
              <div class="row-form">
                <input type="hidden" name="username" value="{u['username']}">
                <input type="password" class="input-sm" name="new_password" placeholder="new password" minlength="8" required style="width:160px">
                <button type="submit" class="btn btn-sm">&gt; set</button>
              </div>
            </form>
            &nbsp;
            <form method="post" action="{url_for('auth.admin_toggle_admin')}" style="display:inline">
              <input type="hidden" name="username" value="{u['username']}">
              <button type="submit" class="btn btn-sm">{'revoke admin' if is_admin else 'make admin'}</button>
            </form>
            &nbsp;
            <form method="post" action="{url_for('auth.admin_delete_user')}" style="display:inline"
                  onsubmit="return confirm('Delete user?')">
              <input type="hidden" name="username" value="{u['username']}">
              <button type="submit" class="btn btn-sm btn-danger">&gt; delete</button>
            </form>
          </td>
        </tr>"""

    content = f"""
<h1 class="page-title">&gt; User Admin</h1>
<p class="sub">// {len(users)} registered users — {_domain}</p>
<table>
  <thead><tr>
    <th>Username</th><th>Email</th><th>Role</th><th>Created</th><th>Actions</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="links" style="margin-top:24px"><a href="/">← back to feed</a></div>
"""
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
