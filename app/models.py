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

    posts = db.relationship("Post", backref="author", lazy=True)

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

    attachments = db.relationship(
        "Attachment", backref="post", cascade="all, delete-orphan", lazy=True
    )


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


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
