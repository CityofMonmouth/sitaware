import os
from datetime import timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "main.login"
login_manager.login_message = "Sign in to continue."
login_manager.login_message_category = "error"
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])


# Placeholder values that have ever shipped as defaults in this repo or its
# docs. If one of these is in use, every session cookie and Agency Access
# token is forgeable by anyone who has seen the source — i.e. a complete
# authentication bypass — so the app refuses to start rather than run
# insecurely in a way nobody would notice.
_INSECURE_SECRET_KEYS = {
    "dev-key-change-me",
    "change-this-to-a-random-string",
    "",
}


def create_app():
    app = Flask(__name__)

    secret_key = os.environ.get("SECRET_KEY", "")
    if secret_key.strip() in _INSECURE_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY is missing or still set to a placeholder value. "
            "Session cookies and Agency Access tokens would be trivially "
            "forgeable. Generate one with:  openssl rand -hex 32  "
            "then set SECRET_KEY=<that value> in your .env file and redeploy."
        )
    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////app/data/briefing.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_DIR"] = "/app/data/uploads"
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB per request

    app.config["SMTP_HOST"] = os.environ.get("SMTP_HOST", "")
    app.config["SMTP_PORT"] = int(os.environ.get("SMTP_PORT", "587"))
    app.config["SMTP_USERNAME"] = os.environ.get("SMTP_USERNAME", "")
    app.config["SMTP_PASSWORD"] = os.environ.get("SMTP_PASSWORD", "")
    app.config["SMTP_FROM_ADDRESS"] = os.environ.get("SMTP_FROM_ADDRESS", "")
    app.config["SMTP_USE_TLS"] = os.environ.get("SMTP_USE_TLS", "true").strip().lower() != "false"

    app.config["TWILIO_ACCOUNT_SID"] = os.environ.get("TWILIO_ACCOUNT_SID", "")
    app.config["TWILIO_AUTH_TOKEN"] = os.environ.get("TWILIO_AUTH_TOKEN", "")
    app.config["TWILIO_FROM_NUMBER"] = os.environ.get("TWILIO_FROM_NUMBER", "")

    # Shared read-only "Agency Access" password — not tied to any named
    # account. Leave AGENCY_PASSWORD unset/empty to disable this login path
    # entirely (the option just won't work until configured).
    agency_password = os.environ.get("AGENCY_PASSWORD", "")
    app.config["AGENCY_PASSWORD_HASH"] = (
        generate_password_hash(agency_password) if agency_password else None
    )

    # Branding — everything here defaults to a generic, unbranded state on
    # purpose. Any specific deployment (agency logos, a named credit line, a
    # custom title) sets these explicitly in its own .env rather than having
    # one agency's identity baked into the shared codebase as the default.
    app.config["BOARD_TITLE"] = os.environ.get("BOARD_TITLE", "Situational Awareness Board")
    app.config["FOOTER_CREDIT"] = os.environ.get("FOOTER_CREDIT", "")
    app.config["SHOW_LOGOS"] = os.environ.get("SHOW_LOGOS", "true").strip().lower() == "true"
    app.config["WEATHER_LOCATION_NAME"] = os.environ.get("WEATHER_LOCATION_NAME", "your area")

    # Set FORCE_HTTPS=true only once a real TLS certificate is in front of this
    # app (reverse proxy). Turning this on before HTTPS is actually working
    # will make the session cookie stop being sent at all, and login will
    # appear broken — this is deliberate, not a bug, if you see that happen.
    force_https = os.environ.get("FORCE_HTTPS", "false").strip().lower() == "true"
    app.config["FORCE_HTTPS"] = force_https
    app.config["SESSION_COOKIE_SECURE"] = force_https
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

    # Set BEHIND_PROXY=true ONLY when a reverse proxy (Caddy/nginx) is actually
    # in front of this app. It makes Flask trust X-Forwarded-* headers, which
    # fixes two things that are silently broken otherwise:
    #   1. Rate limiting — without this every request appears to come from the
    #      proxy's own IP, so all users share one bucket. An attacker wouldn't
    #      be limited meaningfully AND could trip the limit for everyone else.
    #   2. Links in notification emails/texts — request.host_url would be the
    #      internal address (localhost:8082) instead of the real public URL.
    # Enabling this WITHOUT a proxy is its own vulnerability: anyone could then
    # spoof X-Forwarded-For to dodge rate limits. Hence it's opt-in, not default.
    if os.environ.get("BEHIND_PROXY", "false").strip().lower() == "true":
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' https://radar.weather.gov https://services.swpc.noaa.gov; "
            "frame-src 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if force_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    from flask import render_template

    def _error_page(heading, message, code):
        return render_template("error.html", heading=heading, message=message), code

    @app.errorhandler(403)
    def _forbidden(e):
        return _error_page(
            "Not Allowed",
            "You don't have permission to do that. If you're viewing with "
            "Agency Access, that's read-only — sign in with a staff account "
            "to post or manage anything.",
            403,
        )

    @app.errorhandler(404)
    def _not_found(e):
        return _error_page("Not Found", "That page or file doesn't exist.", 404)

    @app.errorhandler(413)
    def _too_large(e):
        # Without this the user just gets a bare server error with no clue
        # that the upload size was the problem.
        return _error_page(
            "Upload Too Large",
            "That upload exceeds the 20MB limit for a single post. Try "
            "attaching fewer or smaller files.",
            413,
        )

    @app.errorhandler(429)
    def _rate_limited(e):
        return _error_page(
            "Slow Down",
            "Too many requests in a short time. Wait a minute and try again.",
            429,
        )

    @app.errorhandler(500)
    def _server_error(e):
        return _error_page(
            "Something Went Wrong",
            "An unexpected error occurred. If this keeps happening, check "
            "the container logs with: docker compose logs",
            500,
        )

    from .timeutils import to_central_str
    app.jinja_env.filters["central_time"] = to_central_str

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        # If the account has since been deactivated, treat the session as invalid
        # right away rather than waiting for their next login attempt.
        if user and not user.active_flag:
            return None
        return user

    from .routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()
        _ensure_admin(app)

    return app


def _ensure_admin(app):
    from .models import User

    if User.query.count() == 0:
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
        admin = User(
            username=username,
            display_name="Administrator",
            agency="System",
            role="admin",
            password_hash=generate_password_hash(password),
        )
        db.session.add(admin)
        db.session.commit()
        app.logger.warning(
            "Created initial admin user '%s'. CHANGE THIS PASSWORD IMMEDIATELY.",
            username,
        )
