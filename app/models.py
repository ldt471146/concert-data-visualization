from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .time_utils import utcnow


class ConcertInfo(db.Model):
    __tablename__ = "concert_info"

    id = db.Column(db.Integer, primary_key=True)
    artist_name = db.Column(db.String(80), nullable=False, index=True)
    concert_name = db.Column(db.String(160), nullable=False)
    city = db.Column(db.String(60), nullable=False, index=True)
    venue = db.Column(db.String(120), nullable=False)
    show_time = db.Column(db.DateTime, nullable=False, index=True)
    price_text = db.Column(db.String(160), nullable=False, default="")
    min_price = db.Column(db.Numeric(10, 2), nullable=True)
    max_price = db.Column(db.Numeric(10, 2), nullable=True)
    sale_status = db.Column(db.String(30), nullable=False, default="待定")
    source_url = db.Column(db.String(500), nullable=False, default="local://data/raw/concerts.csv")
    collected_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    comments = db.relationship(
        "CommentInfo",
        back_populates="concert",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    price_details = db.relationship(
        "TicketPriceDetail",
        back_populates="concert",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def comment_count(self):
        return len(self.comments)

    def to_dict(self):
        return {
            "id": self.id,
            "artist_name": self.artist_name,
            "concert_name": self.concert_name,
            "city": self.city,
            "venue": self.venue,
            "show_time": self.show_time.isoformat(),
            "show_date": self.show_time.strftime("%m.%d"),
            "show_weekday": self.show_time.strftime("%a").upper(),
            "price_text": self.price_text,
            "min_price": float(self.min_price) if self.min_price is not None else None,
            "max_price": float(self.max_price) if self.max_price is not None else None,
            "sale_status": self.sale_status,
            "source_url": self.source_url,
            "comment_count": self.comment_count,
        }


class TicketPriceDetail(db.Model):
    __tablename__ = "ticket_price_detail"

    id = db.Column(db.Integer, primary_key=True)
    concert_id = db.Column(db.Integer, db.ForeignKey("concert_info.id"), nullable=False)
    price_label = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    price_text = db.Column(db.String(160), nullable=False, default="")

    concert = db.relationship("ConcertInfo", back_populates="price_details")


class CommentInfo(db.Model):
    __tablename__ = "comment_info"

    id = db.Column(db.Integer, primary_key=True)
    concert_id = db.Column(db.Integer, db.ForeignKey("concert_info.id"), nullable=True, index=True)
    comment_text = db.Column(db.Text, nullable=False)
    comment_time = db.Column(db.DateTime, nullable=True, index=True)
    like_count = db.Column(db.Integer, nullable=True, default=0)
    user_region = db.Column(db.String(60), nullable=True)
    source_url = db.Column(db.String(500), nullable=False, default="local://data/raw/comments.csv")
    collected_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    sentiment_score = db.Column(db.Float, nullable=True)

    concert = db.relationship("ConcertInfo", back_populates="comments")

    def to_dict(self):
        return {
            "id": self.id,
            "concert_id": self.concert_id,
            "comment_text": self.comment_text,
            "comment_time": self.comment_time.isoformat() if self.comment_time else None,
            "like_count": self.like_count or 0,
            "user_region": self.user_region or "未提供",
            "sentiment_score": self.sentiment_score,
        }


class AnalysisResult(db.Model):
    __tablename__ = "analysis_result"

    id = db.Column(db.Integer, primary_key=True)
    result_type = db.Column(db.String(40), nullable=False, index=True)
    result_key = db.Column(db.String(120), nullable=False)
    result_value = db.Column(db.Float, nullable=False, default=0)
    analysis_time = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_dict(self):
        return {
            "result_type": self.result_type,
            "result_key": self.result_key,
            "result_value": self.result_value,
            "analysis_time": self.analysis_time.isoformat(),
        }


class AdminUser(UserMixin, db.Model):
    __tablename__ = "admin_user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def active(self):
        return self.is_active


class JobRun(db.Model):
    __tablename__ = "job_run"

    id = db.Column(db.Integer, primary_key=True)
    job_type = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="running")
    input_count = db.Column(db.Integer, nullable=False, default=0)
    success_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    message = db.Column(db.String(500), nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "input_count": self.input_count,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "message": self.message or "",
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
