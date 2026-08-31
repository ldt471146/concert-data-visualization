"""Pure CSV validation helpers used by preview and import workflows."""

import csv
import io
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation


SALE_STATUSES = frozenset(
    {
        "待定",
        "售票中",
        "即将开售",
        "已售罄",
        "停售",
        "预售",
        "预售中",
        "暂停售票",
        "已结束",
        "未开售",
        "已下架",
        "筹备中",
        "场次待定",
    }
)
MAX_COMMENT_LENGTH = 2000

FIELD_ALIASES = {
    "artist_name": ("artist_name", "明星名称", "艺人", "艺术家"),
    "concert_name": ("concert_name", "name", "演唱会名称", "演出名称"),
    "city": ("city", "城市"),
    "venue": ("venue", "场馆", "演出场馆"),
    "show_time": ("show_time", "time", "演出时间", "演出日期"),
    "price_text": ("price_text", "原始票价文本", "票价", "票价文本"),
    "sale_status": ("sale_status", "售票状态", "销售状态"),
    "source_url": ("source_url", "来源页面地址", "来源"),
    "collected_at": ("collected_at", "采集时间"),
    "comment_text": ("comment_text", "评论内容", "评论"),
    "comment_time": ("comment_time", "评论时间"),
    "like_count": ("like_count", "点赞数"),
    "user_region": ("user_region", "用户地区"),
}

REQUIRED_FIELDS = {
    "concerts": ("concert_name", "city", "venue", "show_time"),
    "comments": ("comment_text",),
}

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d",
)
_PRICE_PATTERN = re.compile(r"\d+(?:[,.]\d+)?")


def _text(value):
    return "" if value is None else str(value).strip()


def value(row, *keys):
    """Return the first non-empty value for canonical or source field names."""
    for key in keys:
        aliases = FIELD_ALIASES.get(key, (key,))
        for alias in aliases:
            if alias in row and _text(row.get(alias)):
                return _text(row.get(alias))
    return ""


def parse_datetime_strict(raw):
    text = _text(raw).replace("/", "-").replace("T", " ")
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def parse_price_values(raw):
    text = _text(raw)
    if not text:
        return []
    values = []
    for match in _PRICE_PATTERN.findall(text):
        try:
            values.append(Decimal(match.replace(",", "")))
        except InvalidOperation:
            continue
    return values


def price_text_is_parseable(raw):
    text = _text(raw)
    if not text:
        return True
    if parse_price_values(text):
        return True
    return text in {"免费", "面议", "待定", "暂无", "未知"}


def concert_fingerprint(row):
    """Build the source-independent duplicate key used during import."""
    show_time = parse_datetime_strict(value(row, "show_time"))
    date_text = show_time.strftime("%Y-%m-%d") if show_time else value(row, "show_time")
    return (
        value(row, "concert_name").casefold(),
        value(row, "city").casefold(),
        date_text,
        value(row, "venue").casefold(),
    )


def _safe_preview_row(row):
    safe = {}
    for key, raw in row.items():
        if key is None:
            continue
        if any(token in key.casefold() for token in ("password", "passwd", "secret", "token")):
            safe[key] = "***"
        else:
            safe[key] = raw if raw is not None else ""
    return safe


def parse_csv_rows(content):
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    elif not isinstance(content, str):
        content = str(content)
    reader = csv.DictReader(io.StringIO(content))
    return list(reader), list(reader.fieldnames or [])


def _error(row_number, field, code, message):
    return {"row": row_number, "field": field, "code": code, "message": message}


def validate_rows(rows, fields, kind, filename=""):
    errors = []
    missing_fields = []
    invalid_date_count = 0
    invalid_price_count = 0
    unknown_status_count = 0
    overlong_comment_count = 0
    duplicate_count = 0
    fingerprints = set()

    for field in REQUIRED_FIELDS[kind]:
        if not any(alias in fields for alias in FIELD_ALIASES[field]):
            missing_fields.append(field)
            errors.append(_error(0, field, "missing_field", "缺少关键字段"))

    for row_number, row in enumerate(rows, start=2):
        for field in REQUIRED_FIELDS[kind]:
            if not value(row, field):
                errors.append(_error(row_number, field, "missing_value", "关键字段为空"))

        if kind == "concerts":
            show_time = value(row, "show_time")
            if show_time and parse_datetime_strict(show_time) is None:
                invalid_date_count += 1
                errors.append(_error(row_number, "show_time", "invalid_date", "日期格式无法解析"))

            price_text = value(row, "price_text")
            if not price_text_is_parseable(price_text):
                invalid_price_count += 1
                errors.append(_error(row_number, "price_text", "invalid_price", "票价格式无法解析"))

            status = value(row, "sale_status")
            if status and status not in SALE_STATUSES:
                unknown_status_count += 1
                errors.append(_error(row_number, "sale_status", "unknown_status", "售票状态不在允许范围内"))

            fingerprint = concert_fingerprint(row)
            if all(fingerprint):
                if fingerprint in fingerprints:
                    duplicate_count += 1
                    errors.append(_error(row_number, "concert_name", "duplicate", "演唱会指纹重复"))
                fingerprints.add(fingerprint)

        else:
            text = value(row, "comment_text")
            if len(text) > MAX_COMMENT_LENGTH:
                overlong_comment_count += 1
                errors.append(_error(row_number, "comment_text", "comment_too_long", "评论长度超过限制"))
            comment_time = value(row, "comment_time")
            if comment_time and parse_datetime_strict(comment_time) is None:
                invalid_date_count += 1
                errors.append(_error(row_number, "comment_time", "invalid_date", "日期格式无法解析"))

    return {
        "filename": filename or "未命名.csv",
        "kind": kind,
        "fields": fields,
        "total_rows": len(rows),
        "preview": [_safe_preview_row(row) for row in rows[:5]],
        "missing_fields": missing_fields,
        "invalid_date_count": invalid_date_count,
        "invalid_price_count": invalid_price_count,
        "unknown_status_count": unknown_status_count,
        "overlong_comment_count": overlong_comment_count,
        "duplicate_count": duplicate_count,
        "errors": errors,
        "valid": not errors,
    }


def validate_csv(content, kind, filename=""):
    """Validate CSV content without touching Flask, SQLAlchemy, or the database."""
    if kind not in REQUIRED_FIELDS:
        return {
            "filename": filename or "未命名.csv",
            "kind": kind,
            "fields": [],
            "total_rows": 0,
            "preview": [],
            "missing_fields": [],
            "duplicate_count": 0,
            "errors": [_error(0, "kind", "unsupported_kind", "不支持的数据类型")],
            "valid": False,
        }
    try:
        rows, fields = parse_csv_rows(content)
        return validate_rows(rows, fields, kind, filename)
    except (UnicodeDecodeError, csv.Error, TypeError, ValueError):
        return {
            "filename": filename or "未命名.csv",
            "kind": kind,
            "fields": [],
            "total_rows": 0,
            "preview": [],
            "missing_fields": [],
            "duplicate_count": 0,
            "errors": [_error(0, "file", "invalid_csv", "CSV 文件无法解析")],
            "valid": False,
        }


# Explicit aliases make the helper convenient for callers that distinguish these actions.
def preview_csv(content, kind, filename=""):
    return validate_csv(content, kind, filename)


def validate_csv_file(file_obj, kind, filename=""):
    return validate_csv(file_obj.read(), kind, filename)
