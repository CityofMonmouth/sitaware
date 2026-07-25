from datetime import datetime
from flask_login import UserMixin
from . import db


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(128))
    agency = db.Column(db.String(64))  # City, County, PD
    role = db.Column(db.String(20), default="user")  # user, admin
    active_flag = db.Column("active", db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship("Post", foreign_keys="Post.author_id", backref="author", lazy=True)

    @property
    def is_active(self):
        return self.active_flag


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(64), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="info")
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    author_name = db.Column(db.String(128))
    agency = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    # Soft-delete fields. "Delete" in the UI never actually destroys a post —
    # it's hidden from every normal view but stays in the database until an
    # admin explicitly purges it. See AuditLog for the accompanying trail of
    # who did what, when. This exists specifically so this software doesn't
    # let routine use become unscheduled destruction of a public record.
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    attachments = db.relationship(
        "Attachment", backref="post", cascade="all, delete-orphan", lazy=True
    )

    @property
    def active_attachments(self):
        """Attachments excluding soft-deleted ones. Use this everywhere an
        attachment list is shown to a user or included in a notification —
        the raw .attachments relationship includes soft-deleted files too,
        which matters specifically when purging a post (needs every file
        cleaned up, deleted or not) but is wrong everywhere else."""
        return [a for a in self.attachments if not a.is_deleted]

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Same soft-delete pattern as Post — see the comment there.
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    @property
    def is_deleted(self):
        return self.deleted_at is not None


class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    label = db.Column(db.String(128))  # optional note, e.g. "Fire Chief" or "Dispatch"
    added_at = db.Column(db.DateTime, default=datetime.utcnow)


class SmsSubscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)  # E.164, e.g. +15551234567
    label = db.Column(db.String(128))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    """Permanent record of every soft-delete, restore, and purge action.
    This survives even a permanent purge of the post/attachment it refers to
    — the whole point is that "we destroyed this record" is itself something
    that must remain provable, with who authorized it and when."""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    # Snapshot of the actor's name at the time, independent of the User row
    # above — stays meaningful even if that account is later renamed or removed.
    actor_name = db.Column(db.String(128))
    action = db.Column(db.String(30))  # soft_delete, restore, purge
    target_type = db.Column(db.String(20))  # post, attachment
    target_id = db.Column(db.Integer)
    # A snapshot of what the record actually contained, so a purge doesn't
    # erase the ability to describe what was destroyed.
    summary = db.Column(db.Text)
