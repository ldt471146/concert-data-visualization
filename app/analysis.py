import re
from collections import Counter, defaultdict
from datetime import datetime

from .extensions import db
from .models import AnalysisResult, CommentInfo, ConcertInfo
from .time_utils import utcnow

try:
    import jieba
except ImportError:  # pragma: no cover - optional dependency fallback
    jieba = None

try:
    from snownlp import SnowNLP
except ImportError:  # pragma: no cover - optional dependency fallback
    SnowNLP = None


STOP_WORDS = {
    "的", "了", "是", "在", "和", "也", "都", "很", "有", "就", "这", "那", "我", "你", "他",
    "她", "它", "我们", "真的", "一个", "可以", "感觉", "还是", "没有", "因为", "不是", "就是",
}
POSITIVE_WORDS = {"喜欢", "惊喜", "精彩", "震撼", "好听", "值得", "感动", "开心", "热爱", "现场", "期待", "绝美"}
NEGATIVE_WORDS = {"失望", "拥挤", "太贵", "排队", "遗憾", "问题", "一般", "模糊", "延迟", "难受"}
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{1,}|[A-Za-z]{2,}|\d+")


def tokenize(text):
    if jieba:
        raw_tokens = jieba.lcut(text)
    else:
        raw_tokens = TOKEN_RE.findall(text)
    return [token.strip().lower() for token in raw_tokens if token.strip() and token.strip() not in STOP_WORDS and len(token.strip()) > 1]


def sentiment_score(text):
    if SnowNLP:
        try:
            return round(float(SnowNLP(text).sentiments), 4)
        except Exception:
            pass
    positive = sum(text.count(word) for word in POSITIVE_WORDS)
    negative = sum(text.count(word) for word in NEGATIVE_WORDS)
    if positive == negative:
        return 0.52
    return round(min(0.95, max(0.08, 0.52 + (positive - negative) * 0.12)), 4)


def _add_results(result_type, values, timestamp):
    for key, value in values.items():
        db.session.add(
            AnalysisResult(
                result_type=result_type,
                result_key=str(key),
                result_value=float(value),
                analysis_time=timestamp,
            )
        )


def run_analysis(sample_limit=8000, sentiment_batch=500):
    """全库聚合分析。

    10 万级评论下逐条 SnowNLP 情感分析会阻塞数十分钟, 因此:
    - 情感/词频/地区/趋势统计基于最多 sample_limit 条评论(均匀抽样),
      保证统计口径稳定且渲染秒级返回;
    - 未计算情感分的评论在导入时分批补算(见 services 导入逻辑),
      这里只对缺失情感分的样本补算, 并用批提交避免长事务阻塞。
    """
    timestamp = utcnow()
    total_comments = CommentInfo.query.count()

    # 1) 采样评论(最多 sample_limit 条, 均匀取)
    ids = [row[0] for row in CommentInfo.query.with_entities(CommentInfo.id).order_by(CommentInfo.id.asc()).all()]
    if len(ids) > sample_limit:
        step = max(1, len(ids) // sample_limit)
        ids = ids[::step][:sample_limit]
    comments = CommentInfo.query.filter(CommentInfo.id.in_(ids)).all() if ids else []

    # 2) 删除旧分析结果(保留历史趋势价值有限)
    for row in AnalysisResult.query.all():
        db.session.delete(row)
    db.session.flush()

    word_counter = Counter()
    sentiment_counter = Counter()
    region_counter = Counter()
    trend_counter = Counter()
    city_counter = Counter()
    price_counter = Counter()

    scored = 0
    for comment in comments:
        if comment.sentiment_score is None:
            comment.sentiment_score = sentiment_score(comment.comment_text)
            scored += 1
            if scored % sentiment_batch == 0:
                db.session.commit()
        bucket = "正面" if comment.sentiment_score >= 0.6 else "负面" if comment.sentiment_score <= 0.4 else "中性"
        sentiment_counter[bucket] += 1
        region_counter[comment.user_region or "未提供"] += 1
        if comment.comment_time:
            trend_counter[comment.comment_time.strftime("%Y-%m")] += 1
        word_counter.update(tokenize(comment.comment_text))

    concerts = ConcertInfo.query.order_by(ConcertInfo.show_time.asc()).all()
    for concert in concerts:
        city_counter[concert.city] += 1
        price = float(concert.min_price or 0)
        price_bucket = "0-499" if price < 500 else "500-999" if price < 1000 else "1000-1499" if price < 1500 else "1500+"
        price_counter[price_bucket] += 1

    _add_results("keyword", dict(word_counter.most_common(14)), timestamp)
    _add_results("sentiment", sentiment_counter, timestamp)
    _add_results("region", region_counter, timestamp)
    _add_results("trend", dict(sorted(trend_counter.items())), timestamp)
    _add_results("city", city_counter, timestamp)
    _add_results("price", price_counter, timestamp)
    db.session.commit()

    return {
        "comments": len(comments),
        "concerts": len(concerts),
        "keywords": len(word_counter),
        "sentiment": dict(sentiment_counter),
        "analysis_time": timestamp.isoformat(),
        "sampled": True,
        "total_comments": total_comments,
    }
