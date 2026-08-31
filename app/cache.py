"""Redis 缓存层：为分析类接口提供短 TTL 缓存，Redis 不可用时自动降级为无缓存。

设计目标（毕业设计可解释）：
- 分析接口（overview / map / trend / calendar / prices / topics / artists / sources）
  在十万级数据下每次请求都要做聚合，通过缓存把重复请求的响应时间从秒级降到毫秒级。
- 缓存键由接口名 + 筛选参数构成，筛选条件变化时自动失效。
- Redis 连接失败/超时不会让接口报错 —— 捕获异常后走原逻辑（fail-open）。
"""

import hashlib
import json

try:
    import redis as _redis
except ImportError:  # pragma: no cover - optional dependency fallback
    _redis = None

# 模块级惰性客户端：首次使用时才连接
_client = None
_client_error = None


def _get_client():
    global _client, _client_error
    if _redis is None:
        return None
    if _client is not None:
        return _client
    if _client_error is not None:
        return None  # 之前连接失败，直接降级，避免每次请求都尝试重连
    try:
        _client = _redis.Redis(
            host="127.0.0.1", port=6379, db=0,
            socket_connect_timeout=0.5, socket_timeout=1.0,
            decode_responses=True,
        )
        _client.ping()
    except Exception as exc:  # pragma: no cover - 环境依赖
        _client_error = str(exc)
        _client = None
    return _client


def cache_key(prefix, **parts):
    """构造稳定缓存 key：prefix + 参数 JSON 的 sha1 摘要。"""
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"pulse:{prefix}:{digest}"


def get_cached(key):
    """读取缓存；超时/失败返回 None（fail-open）。"""
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:  # pragma: no cover
        return None


def set_cached(key, value, ttl=300):
    """写入缓存；失败静默忽略。"""
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    except Exception:  # pragma: no cover
        pass


def clear_cache(prefix=None):
    """清空缓存（管理后台数据变更后调用）。prefix 为 None 时清空全部 pulse:* 键。"""
    client = _get_client()
    if client is None:
        return 0
    try:
        if prefix:
            keys = list(client.scan_iter(f"pulse:{prefix}:*"))
        else:
            keys = list(client.scan_iter("pulse:*"))
        if keys:
            return client.delete(*keys)
        return 0
    except Exception:  # pragma: no cover
        return 0