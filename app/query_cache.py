"""Redis-backed search cache with an in-process fallback for local development."""

import os
import pickle
from collections import OrderedDict
from collections.abc import MutableMapping

from redis import Redis


class QueryCache(MutableMapping):
    def __init__(self, max_items: int = 200, ttl_seconds: int = 86400):
        self.local = OrderedDict()
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        url = os.environ.get("REDIS_URL")
        self.redis = Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5) if url else None

    def _key(self, key):
        return f"query:{key}"

    def __getitem__(self, key):
        if key in self.local:
            self.local.move_to_end(key)
            return self.local[key]
        if self.redis is not None:
            try:
                raw = self.redis.get(self._key(key))
                if raw is not None:
                    value = pickle.loads(raw)  # Redis is private infrastructure; clients never provide this value.
                    self._remember(key, value)
                    return value
            except Exception:
                pass
        raise KeyError(key)

    def __setitem__(self, key, value):
        self._remember(key, value)
        if self.redis is not None:
            try:
                self.redis.setex(self._key(key), self.ttl_seconds, pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
            except Exception:
                pass

    def _remember(self, key, value):
        self.local[key] = value
        self.local.move_to_end(key)
        while len(self.local) > self.max_items:
            self.local.popitem(last=False)

    def __delitem__(self, key):
        del self.local[key]
        if self.redis is not None:
            try:
                self.redis.delete(self._key(key))
            except Exception:
                pass

    def __iter__(self):
        return iter(self.local)

    def __len__(self):
        return len(self.local)

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False

    def popitem(self, last=True):
        key, value = self.local.popitem(last=last)
        if self.redis is not None:
            try:
                self.redis.delete(self._key(key))
            except Exception:
                pass
        return key, value
