import os
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, abort,
    current_app, send_from_directory,
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from . import db, limiter
from .models import User, Post, Attachment, Subscriber, SmsSubscriber, AuditLog
from .forms import (
    LoginForm, PostForm, UserForm, EditUserForm, SubscriberForm, SmsSubscriberForm,
    EmergencyAlertForm, AgencyAccessForm, CATEGORY_CHOICES, PRIORITY_CHOICES,
)
from .weather import get_forecast, RADAR_STATION
from .mailer import send_post_notification_async
from .sms import send_urgent_sms_async
from .timeutils import to_central_str

main = Blueprint("main", __name__)

PRIORITY_WEIGHT = {"urgent": 0, "advisory": 1, "info": 2}
CATEGORY_LABELS = dict(CATEGORY_CHOICES)
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}

# Precomputed once at startup so a login attempt against a nonexistent
# username costs the same as one against a real username with a wrong
# password — prevents timing-based username enumeration.
DUMMY_HASH = generate_password_hash("no-such-user-timing-safety-placeholder")

# Cap on total attachment bytes embedded in a notification email. Kept well
# under most providers' ~20-25MB message-size ceiling, since base64 encoding
# inflates raw file size by roughly a third.
MAX_EMAIL_ATTACHMENT_BYTES = 15 * 1024 * 1024

AGENCY_COOKIE_NAME = "agency_access"
AGENCY_COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 days — long-lived deliberately,
# so a kiosk/TV browser that logs in once with the shared password keeps
# working for months without needing to be manually re-authenticated.


def _safe_next_url(candidate, fallback_endpoint="main.index"):
    """Only allow same-site relative redirects. Without this check, a link
    like /login?next=https://evil.example/ would bounce the user to an
    attacker-controlled site immediately after they authenticate — a classic
    open-redirect / credential-phishing vector. Anything that isn't a plain
    site-relative path is discarded in favour of the fallback."""
    fallback = url_for(fallback_endpoint)
    if not candidate:
        return fallback
    # Must start with a single "/" — rejects absolute URLs ("https://evil"),
    # protocol-relative URLs ("//evil"), and backslash variants that some
    # browsers normalise into "//".
    if not candidate.startswith("/"):
        return fallback
    if candidate.startswith("//") or candidate.startswith("/\\"):
        return fallback
    if "\\" in candidate:
        return fallback
    return candidate


def _agency_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="agency-access")


def has_agency_access():
    token = request.cookies.get(AGENCY_COOKIE_NAME)
    if not token:
        return False
    try:
        data = _agency_serializer().loads(token, max_age=AGENCY_COOKIE_MAX_AGE)
        return bool(data.get("agency"))
    except (BadSignature, SignatureExpired):
        return False


def view_access_required(f):
    """Gates read-only pages behind either a real personal login OR the
    shared Agency Access cookie. Deliberately separate from Flask-Login's
    current_user — the agency cookie can never satisfy @login_required, so
    it can't be used (even by mistake) to reach posting or admin routes."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated or has_agency_access():
            return f(*args, **kwargs)
        return redirect(url_for("main.login", next=request.path))
    return wrapper


@main.app_context_processor
def inject_branding():
    return dict(
        board_title=current_app.config["BOARD_TITLE"],
        footer_credit=current_app.config["FOOTER_CREDIT"],
        show_logos=current_app.config["SHOW_LOGOS"],
        weather_location=current_app.config["WEATHER_LOCATION_NAME"],
    )


@main.app_context_processor
def inject_agency_status():
    try:
        return dict(viewing_as_agency=(not current_user.is_authenticated) and has_agency_access())
    except Exception:
        return dict(viewing_as_agency=False)


@main.app_context_processor
def inject_urgent_count():
    # These run on every rendered page, including the error pages. If the
    # database is the thing that's broken, letting this raise would break
    # the 500 page too and surface a bare stack trace instead of a useful
    # message — so it degrades to "no banner" rather than failing.
    try:
        now = datetime.utcnow()
        count = Post.query.filter(
            Post.priority == "urgent",
            Post.deleted_at.is_(None),
            db.or_(Post.expires_at.is_(None), Post.expires_at > now),
        ).count()
        return dict(urgent_count=count)
    except Exception:
        return dict(urgent_count=0)


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _save_attachments(post, files):
    upload_dir = current_app.config["UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)
    for f in files:
        if not f or not f.filename:
            continue
        if not _allowed_file(f.filename):
            flash(f"Skipped '{f.filename}' — only PDF, JPG, PNG allowed.", "error")
            continue
        ext = f.filename.rsplit(".", 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        f.save(os.path.join(upload_dir, stored_name))
        # secure_filename() strips non-ASCII entirely, so a filename made up
        # only of e.g. accented or CJK characters comes back as "". That would
        # render as a blank link on the board and a nameless email attachment,
        # so fall back to something meaningful.
        display_name = secure_filename(f.filename) or f"attachment.{ext}"
        att = Attachment(
            post_id=post.id,
            stored_name=stored_name,
            original_name=display_name,
            content_type=f.mimetype,
        )
        db.session.add(att)
    db.session.commit()


def _delete_attachment_file(att):
    try:
        os.remove(os.path.join(current_app.config["UPLOAD_DIR"], att.stored_name))
    except OSError:
        pass


def _log_audit(action, target_type, target_id, summary):
    """Records a soft_delete/restore/purge action. This entry is never
    itself deleted, even when the thing it refers to is later purged —
    that's the point: "this record was destroyed" must remain provable
    after the fact, along with who did it and when."""
    entry = AuditLog(
        actor_id=current_user.id if current_user.is_authenticated else None,
        actor_name=(current_user.display_name or current_user.username)
        if current_user.is_authenticated else "unknown",
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
    )
    db.session.add(entry)


def _gather_email_attachments(post):
    """Reads attachment files off disk for embedding in the notification
    email. Returns (attachments_list, oversized_note) — if the total size
    exceeds MAX_EMAIL_ATTACHMENT_BYTES, files are skipped entirely (rather
    than risking a bounced/rejected email) and oversized_note explains why,
    to be appended to the email body instead."""
    attachments = post.active_attachments
    if not attachments:
        return [], None

    upload_dir = current_app.config["UPLOAD_DIR"]
    total_size = 0
    for att in attachments:
        path = os.path.join(upload_dir, att.stored_name)
        try:
            total_size += os.path.getsize(path)
        except OSError:
            continue

    if total_size > MAX_EMAIL_ATTACHMENT_BYTES:
        note = (
            f"This post has {len(attachments)} attachment(s) totaling "
            f"~{total_size // (1024 * 1024)}MB — too large to include in this "
            f"email. View them on the board instead."
        )
        return [], note

    files = []
    for att in attachments:
        path = os.path.join(upload_dir, att.stored_name)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        files.append({
            "filename": att.original_name,
            "content_type": att.content_type,
            "data": data,
        })
    return files, None


def _notify_subscribers(post):
    recipient_emails = [s.email for s in Subscriber.query.all()]
    if not recipient_emails:
        print("[mailer] Email List has no addresses — skipping send.")
        return

    smtp_config = {
        "host": current_app.config["SMTP_HOST"],
        "port": current_app.config["SMTP_PORT"],
        "username": current_app.config["SMTP_USERNAME"],
        "password": current_app.config["SMTP_PASSWORD"],
        "from_addr": current_app.config["SMTP_FROM_ADDRESS"],
        "use_tls": current_app.config["SMTP_USE_TLS"],
    }

    attachments, oversized_note = _gather_email_attachments(post)

    board_url = request.host_url.rstrip("/") + url_for("main.index")
    subject = f"[{post.priority.upper()}] {post.title} \u2014 Situational Awareness Briefing"
    body_lines = [
        f"Priority: {post.priority.upper()}",
        f"Category: {CATEGORY_LABELS.get(post.category, post.category)}",
        f"Posted by: {post.author_name}" + (f" \u2014 {post.agency}" if post.agency else ""),
        f"Time: {to_central_str(post.created_at)}",
        "",
        post.body,
    ]
    if oversized_note:
        body_lines += ["", oversized_note]
    body_lines += ["", f"View the full board: {board_url}"]
    body_text = "\n".join(body_lines)

    send_post_notification_async(smtp_config, subject, body_text, recipient_emails, attachments)


def _build_sms_text(post, board_url):
    """Keep the message short and self-contained — carriers/Twilio bill per
    ~160-char segment, and a truncated message with no link would be useless
    anyway, so this always preserves the link even if the body gets cut."""
    prefix = f"URGENT: {post.title}"
    suffix = f" - {board_url}"
    max_len = 300
    remaining = max_len - len(prefix) - len(suffix) - 3  # buffer for " - "
    body_snippet = " ".join(post.body.split())  # collapse newlines/whitespace
    if remaining <= 0:
        return f"{prefix}{suffix}"
    if len(body_snippet) > remaining:
        body_snippet = body_snippet[:remaining].rstrip() + "..."
    return f"{prefix} - {body_snippet}{suffix}"


def _notify_sms_subscribers(post):
    recipient_phones = [s.phone for s in SmsSubscriber.query.all()]
    if not recipient_phones:
        print("[sms] Text Alert list has no numbers — skipping send.")
        return

    twilio_config = {
        "account_sid": current_app.config["TWILIO_ACCOUNT_SID"],
        "auth_token": current_app.config["TWILIO_AUTH_TOKEN"],
        "from_number": current_app.config["TWILIO_FROM_NUMBER"],
    }
    board_url = request.host_url.rstrip("/") + url_for("main.index")
    message_text = _build_sms_text(post, board_url)
    send_urgent_sms_async(twilio_config, message_text, recipient_phones)


@main.route("/uploads/<path:filename>")
@view_access_required
def uploaded_file(filename):
    # A soft-deleted attachment is meant to be hidden, not just delisted —
    # otherwise the direct file URL would still work for anyone who had it,
    # deletion in name only. Admins retain access since they're the ones who
    # review/restore/purge from the Deleted Items page.
    att = Attachment.query.filter_by(stored_name=filename).first()
    if att and att.is_deleted:
        if not (current_user.is_authenticated and current_user.role == "admin"):
            abort(404)
    response = send_from_directory(current_app.config["UPLOAD_DIR"], filename)
    # Uploaded files are user-supplied; extension is validated at upload time, but
    # this stops browsers from content-sniffing a mislabeled file as something
    # executable (e.g. HTML) regardless of what we served it as.
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@main.route("/")
@view_access_required
def index():
    now = datetime.utcnow()
    category = request.args.get("category", "")
    priority = request.args.get("priority", "")

    query = Post.query.filter(
        Post.deleted_at.is_(None),
        db.or_(Post.expires_at.is_(None), Post.expires_at > now),
    )
    if category:
        query = query.filter(Post.category == category)
    if priority:
        query = query.filter(Post.priority == priority)

    posts = query.order_by(Post.created_at.desc()).all()
    # Python's list.sort() is stable, so this preserves the newest-first ordering
    # from the query above within each priority tier: urgent posts appear first,
    # and within "urgent" the most recently published one is on top.
    posts.sort(key=lambda p: PRIORITY_WEIGHT.get(p.priority, 9))
    forecast = get_forecast()
    return render_template(
        "index.html",
        posts=posts,
        category_labels=CATEGORY_LABELS,
        category_choices=CATEGORY_CHOICES,
        priority_choices=PRIORITY_CHOICES,
        selected_category=category,
        selected_priority=priority,
        forecast=forecast,
        radar_station=RADAR_STATION,
    )


@main.route("/archive")
@view_access_required
def archive():
    now = datetime.utcnow()
    category = request.args.get("category", "")
    priority = request.args.get("priority", "")

    query = Post.query.filter(
        Post.deleted_at.is_(None),
        Post.expires_at.isnot(None),
        Post.expires_at <= now,
    )
    if category:
        query = query.filter(Post.category == category)
    if priority:
        query = query.filter(Post.priority == priority)

    posts = query.order_by(Post.created_at.desc()).limit(200).all()
    return render_template(
        "archive.html",
        posts=posts,
        category_labels=CATEGORY_LABELS,
        category_choices=CATEGORY_CHOICES,
        priority_choices=PRIORITY_CHOICES,
        selected_category=category,
        selected_priority=priority,
    )


@main.route("/kiosk")
@view_access_required
def kiosk():
    now = datetime.utcnow()
    posts = (
        Post.query.filter(
            Post.deleted_at.is_(None),
            db.or_(Post.expires_at.is_(None), Post.expires_at > now),
        )
        .order_by(Post.created_at.desc())
        .all()
    )
    # Same stable-sort logic as the main board: urgent first, newest within each tier.
    posts.sort(key=lambda p: PRIORITY_WEIGHT.get(p.priority, 9))
    forecast = get_forecast()
    return render_template(
        "kiosk.html",
        posts=posts,
        category_labels=CATEGORY_LABELS,
        forecast=forecast,
        radar_station=RADAR_STATION,
    )


@main.route("/weather")
@view_access_required
def weather():
    forecast = get_forecast()
    return render_template(
        "weather.html",
        forecast=forecast,
        radar_station=RADAR_STATION,
    )


@main.route("/login", methods=["GET", "POST"])
@limiter.limit("8 per minute; 30 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    personal_form = LoginForm(prefix="personal")
    agency_form = AgencyAccessForm(prefix="agency")
    agency_configured = bool(current_app.config["AGENCY_PASSWORD_HASH"])

    if personal_form.submit.data and personal_form.validate_on_submit():
        user = User.query.filter_by(username=personal_form.username.data.strip()).first()
        # Always run a hash comparison, even when the username doesn't exist,
        # using a fixed dummy hash — this keeps response timing the same in
        # both cases so a timing attack can't be used to enumerate valid
        # usernames. DUMMY_HASH is any valid-format hash; it never matches.
        password_hash = user.password_hash if user else DUMMY_HASH
        password_ok = check_password_hash(password_hash, personal_form.password.data)
        if user and user.is_active and password_ok:
            login_user(user)
            flash("Signed in.", "success")
            return redirect(_safe_next_url(request.args.get("next")))
        flash("Invalid username or password.", "error")

    elif agency_form.submit.data and not agency_configured:
        # Without this branch the submission silently fell through and
        # re-rendered the page with no message at all, which looks identical
        # to "the button is broken".
        flash("Agency Access is not configured on this server yet.", "error")

    elif agency_form.submit.data and agency_form.validate_on_submit():
        if check_password_hash(current_app.config["AGENCY_PASSWORD_HASH"], agency_form.password.data):
            # Deliberately ignore any `next` destination here — agency access
            # can never satisfy a @login_required page, so honoring `next`
            # could bounce the visitor straight back to this login page.
            response = redirect(url_for("main.index"))
            token = _agency_serializer().dumps({"agency": True})
            response.set_cookie(
                AGENCY_COOKIE_NAME,
                token,
                max_age=AGENCY_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=current_app.config["FORCE_HTTPS"],
            )
            flash("Viewing with Agency Access (read-only).", "success")
            return response
        flash("Incorrect agency password.", "error")

    return render_template(
        "login.html",
        personal_form=personal_form,
        agency_form=agency_form,
        agency_configured=agency_configured,
    )


@main.route("/agency-logout", methods=["POST"])
def agency_logout():
    # POST-only (with CSRF token) rather than a plain link. As a GET route,
    # any prefetch, link scanner, or a hostile <img src="/agency-logout"> on
    # an unrelated page could silently sign out the kiosk display and leave
    # the TV sitting on a login screen until someone walks over to it.
    response = redirect(url_for("main.login"))
    response.delete_cookie(AGENCY_COOKIE_NAME)
    flash("Signed out of Agency Access.", "success")
    return response


@main.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Signed out.", "success")
    return redirect(url_for("main.index"))


@main.route("/post/new", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour", methods=["POST"])
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(
            title=form.title.data.strip(),
            body=form.body.data.strip(),
            category=form.category.data,
            priority=form.priority.data,
            author_id=current_user.id,
            author_name=current_user.display_name or current_user.username,
            agency=current_user.agency,
            expires_at=form.expires_at.data or (datetime.utcnow() + timedelta(hours=24)),
        )
        db.session.add(post)
        db.session.commit()
        _save_attachments(post, request.files.getlist("attachments"))
        if form.notify_email.data:
            _notify_subscribers(post)
        if post.priority == "urgent":
            _notify_sms_subscribers(post)
        flash("Update posted.", "success")
        return redirect(url_for("main.index"))
    return render_template("post_form.html", form=form, mode="new")


@main.route("/emergency-alert", methods=["GET", "POST"])
@login_required
@limiter.limit("6 per hour", methods=["POST"])
def emergency_alert():
    form = EmergencyAlertForm()
    if form.validate_on_submit():
        post = Post(
            title="EMERGENCY ALERT",
            body=form.message.data.strip(),
            category="incident",
            priority="urgent",
            author_id=current_user.id,
            author_name=current_user.display_name or current_user.username,
            agency=current_user.agency,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        db.session.add(post)
        db.session.commit()
        # Emergency alerts always go out on both channels — no per-post
        # checkbox here, this button exists specifically to broadcast as
        # widely and fast as possible.
        _notify_subscribers(post)
        _notify_sms_subscribers(post)
        flash("Emergency alert sent — posted to the board and texted to the SMS list.", "success")
        return redirect(url_for("main.index"))
    return render_template("emergency_alert.html", form=form)


@main.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = db.session.get(Post, post_id) or abort(404)
    if post.author_id != current_user.id and current_user.role != "admin":
        abort(403)
    form = PostForm(obj=post)
    if form.validate_on_submit():
        post.title = form.title.data.strip()
        post.body = form.body.data.strip()
        post.category = form.category.data
        post.priority = form.priority.data
        # Blank expiry means the same thing here as it does on a new post —
        # the default 24h window — rather than "never expires". Previously
        # clearing this field on an edit made the post permanent, which no
        # label on the form suggests and which would quietly keep a stale
        # update pinned to the board indefinitely.
        post.expires_at = form.expires_at.data or (post.created_at + timedelta(hours=24))
        db.session.commit()
        _save_attachments(post, request.files.getlist("attachments"))
        flash("Update revised.", "success")
        return redirect(url_for("main.index"))
    return render_template("post_form.html", form=form, mode="edit", post=post)


@main.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = db.session.get(Post, post_id) or abort(404)
    if post.author_id != current_user.id and current_user.role != "admin":
        abort(403)
    # Soft delete only — the row and any attached files stay on disk. This
    # is deliberate: an ordinary "delete" click should never be the same
    # thing as permanently destroying a public record. See _log_audit and
    # the /admin/deleted-items page for how this gets reviewed and, if
    # appropriate, actually purged later.
    post.deleted_at = datetime.utcnow()
    post.deleted_by_id = current_user.id
    _log_audit(
        "soft_delete", "post", post.id,
        f"Title: {post.title}\nCategory: {post.category}\nPriority: {post.priority}\n\n{post.body}",
    )
    db.session.commit()
    flash("Update removed from the board. It can be restored or permanently purged from Deleted Items.", "success")
    return redirect(url_for("main.index"))


@main.route("/attachment/<int:attachment_id>/delete", methods=["POST"])
@login_required
def delete_attachment(attachment_id):
    att = db.session.get(Attachment, attachment_id) or abort(404)
    post = att.post
    if post.author_id != current_user.id and current_user.role != "admin":
        abort(403)
    # Soft delete — same reasoning as delete_post above. The file stays on
    # disk until an actual purge.
    att.deleted_at = datetime.utcnow()
    att.deleted_by_id = current_user.id
    _log_audit("soft_delete", "attachment", att.id, f"Filename: {att.original_name} (post: {post.title})")
    db.session.commit()
    flash("Attachment removed. It can be restored or permanently purged from Deleted Items.", "success")
    return redirect(url_for("main.edit_post", post_id=post.id))


@main.route("/admin/deleted-items")
@login_required
def admin_deleted_items():
    if current_user.role != "admin":
        abort(403)
    deleted_posts = (
        Post.query.filter(Post.deleted_at.isnot(None))
        .order_by(Post.deleted_at.desc())
        .all()
    )
    deleted_attachments = (
        Attachment.query.filter(Attachment.deleted_at.isnot(None))
        .order_by(Attachment.deleted_at.desc())
        .all()
    )
    return render_template(
        "admin_deleted_items.html",
        deleted_posts=deleted_posts,
        deleted_attachments=deleted_attachments,
        category_labels=CATEGORY_LABELS,
    )


@main.route("/admin/post/<int:post_id>/restore", methods=["POST"])
@login_required
def restore_post(post_id):
    post = db.session.get(Post, post_id) or abort(404)
    if post.author_id != current_user.id and current_user.role != "admin":
        abort(403)
    post.deleted_at = None
    post.deleted_by_id = None
    _log_audit("restore", "post", post.id, f"Title: {post.title}")
    db.session.commit()
    flash("Update restored to the board.", "success")
    return redirect(url_for("main.admin_deleted_items"))


@main.route("/admin/post/<int:post_id>/purge", methods=["POST"])
@login_required
def purge_post(post_id):
    if current_user.role != "admin":
        abort(403)
    post = db.session.get(Post, post_id) or abort(404)
    if not post.is_deleted:
        # Purging is only ever allowed on something already soft-deleted —
        # this prevents a purge link/form from ever being used to skip the
        # soft-delete step entirely.
        abort(400)
    summary = f"Title: {post.title}\nCategory: {post.category}\nPriority: {post.priority}\n\n{post.body}"
    for att in post.attachments:
        _delete_attachment_file(att)
    _log_audit("purge", "post", post.id, summary)
    db.session.delete(post)
    db.session.commit()
    flash("Update permanently purged.", "success")
    return redirect(url_for("main.admin_deleted_items"))


@main.route("/admin/attachment/<int:attachment_id>/restore", methods=["POST"])
@login_required
def restore_attachment(attachment_id):
    att = db.session.get(Attachment, attachment_id) or abort(404)
    post = att.post
    if post.author_id != current_user.id and current_user.role != "admin":
        abort(403)
    att.deleted_at = None
    att.deleted_by_id = None
    _log_audit("restore", "attachment", att.id, f"Filename: {att.original_name}")
    db.session.commit()
    flash("Attachment restored.", "success")
    return redirect(url_for("main.admin_deleted_items"))


@main.route("/admin/attachment/<int:attachment_id>/purge", methods=["POST"])
@login_required
def purge_attachment(attachment_id):
    if current_user.role != "admin":
        abort(403)
    att = db.session.get(Attachment, attachment_id) or abort(404)
    if not att.is_deleted:
        abort(400)
    summary = f"Filename: {att.original_name} (post: {att.post.title})"
    _delete_attachment_file(att)
    _log_audit("purge", "attachment", att.id, summary)
    db.session.delete(att)
    db.session.commit()
    flash("Attachment permanently purged.", "success")
    return redirect(url_for("main.admin_deleted_items"))


@main.route("/admin/audit-log")
@login_required
def admin_audit_log():
    if current_user.role != "admin":
        abort(403)
    entries = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    return render_template("admin_audit_log.html", entries=entries)


@main.route("/admin/users", methods=["GET", "POST"])
@login_required
def admin_users():
    if current_user.role != "admin":
        abort(403)
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data.strip()).first():
            flash("Username already exists.", "error")
        else:
            u = User(
                username=form.username.data.strip(),
                display_name=form.display_name.data.strip(),
                agency=form.agency.data,
                role=form.role.data,
                password_hash=generate_password_hash(form.password.data),
            )
            db.session.add(u)
            db.session.commit()
            flash(f"User {u.username} created.", "success")
            return redirect(url_for("main.admin_users"))
    users = User.query.order_by(User.username).all()
    return render_template("admin_users.html", form=form, users=users)


@main.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if current_user.role != "admin":
        abort(403)
    user = db.session.get(User, user_id) or abort(404)
    form = EditUserForm(obj=user)
    if form.validate_on_submit():
        if user.role == "admin" and form.role.data != "admin":
            remaining_admins = User.query.filter(
                User.role == "admin", User.active_flag.is_(True), User.id != user.id
            ).count()
            if remaining_admins == 0:
                flash(
                    "Can't remove admin rights from the last active admin account — "
                    "promote someone else first, or you'll lock everyone out of user management.",
                    "error",
                )
                return redirect(url_for("main.admin_users"))
        user.display_name = form.display_name.data.strip()
        user.agency = form.agency.data
        user.role = form.role.data
        if form.password.data:
            user.password_hash = generate_password_hash(form.password.data)
        db.session.commit()
        flash(f"User {user.username} updated.", "success")
        return redirect(url_for("main.admin_users"))
    return render_template("edit_user.html", form=form, user=user)


@main.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def toggle_user(user_id):
    if current_user.role != "admin":
        abort(403)
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("You can't deactivate your own account.", "error")
        return redirect(url_for("main.admin_users"))
    user.active_flag = not user.active_flag
    db.session.commit()
    flash(f"User {user.username} {'activated' if user.active_flag else 'deactivated'}.", "success")
    return redirect(url_for("main.admin_users"))


@main.route("/admin/subscribers", methods=["GET", "POST"])
@login_required
def admin_subscribers():
    if current_user.role != "admin":
        abort(403)
    form = SubscriberForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if Subscriber.query.filter_by(email=email).first():
            flash("That email is already on the list.", "error")
        else:
            sub = Subscriber(
                email=email,
                label=form.label.data.strip() if form.label.data else None,
            )
            db.session.add(sub)
            db.session.commit()
            flash(f"Added {email} to the notification list.", "success")
            return redirect(url_for("main.admin_subscribers"))
    subscribers = Subscriber.query.order_by(Subscriber.email).all()
    smtp_configured = bool(current_app.config["SMTP_HOST"])
    return render_template(
        "admin_subscribers.html",
        form=form,
        subscribers=subscribers,
        smtp_configured=smtp_configured,
    )


@main.route("/admin/subscribers/<int:subscriber_id>/delete", methods=["POST"])
@login_required
def delete_subscriber(subscriber_id):
    if current_user.role != "admin":
        abort(403)
    sub = db.session.get(Subscriber, subscriber_id) or abort(404)
    db.session.delete(sub)
    db.session.commit()
    flash(f"Removed {sub.email} from the notification list.", "success")
    return redirect(url_for("main.admin_subscribers"))


@main.route("/admin/sms-subscribers", methods=["GET", "POST"])
@login_required
def admin_sms_subscribers():
    if current_user.role != "admin":
        abort(403)
    form = SmsSubscriberForm()
    if form.validate_on_submit():
        phone = form.phone.data.strip()
        if SmsSubscriber.query.filter_by(phone=phone).first():
            flash("That phone number is already on the list.", "error")
        else:
            sub = SmsSubscriber(
                phone=phone,
                label=form.label.data.strip() if form.label.data else None,
            )
            db.session.add(sub)
            db.session.commit()
            flash(f"Added {phone} to the text alert list.", "success")
            return redirect(url_for("main.admin_sms_subscribers"))
    subscribers = SmsSubscriber.query.order_by(SmsSubscriber.phone).all()
    twilio_configured = bool(
        current_app.config["TWILIO_ACCOUNT_SID"]
        and current_app.config["TWILIO_AUTH_TOKEN"]
        and current_app.config["TWILIO_FROM_NUMBER"]
    )
    return render_template(
        "admin_sms_subscribers.html",
        form=form,
        subscribers=subscribers,
        twilio_configured=twilio_configured,
    )


@main.route("/admin/sms-subscribers/<int:subscriber_id>/delete", methods=["POST"])
@login_required
def delete_sms_subscriber(subscriber_id):
    if current_user.role != "admin":
        abort(403)
    sub = db.session.get(SmsSubscriber, subscriber_id) or abort(404)
    db.session.delete(sub)
    db.session.commit()
    flash(f"Removed {sub.phone} from the text alert list.", "success")
    return redirect(url_for("main.admin_sms_subscribers"))
