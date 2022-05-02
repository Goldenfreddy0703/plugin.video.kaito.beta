# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, unicode_literals

import abc
import calendar
import codecs
import collections
import datetime
import pickle
import types
from functools import reduce, wraps

from resources.lib.ui import control
from resources.lib.database import Database
from resources.lib.ui.exceptions import UnsupportedCacheParamException
from resources.lib.ui.globals import g

schema = {
    "cache": {
        "columns": collections.OrderedDict(
            [
                ("id", ["TEXT", "PRIMARY KEY", "NOT NULL"]),
                ("expires", ["INTEGER", "NOT NULL"]),
                ("data", ["PICKLE"]),
                ("checksum", ["INTEGER"]),
            ]
        ),
        "table_constraints": ["UNIQUE(id)"],
        "default_seed": [],
        }
    }


class CacheBase:
    """
    Base Class for handling cache calls
    """
    __metaclass__ = abc.ABCMeta
    NOT_CACHED = "____NO_CACHED_OBJECT____"
    _exit = False

    def __init__(self):
        self.global_checksum = None
        self.cache_prefix = "cache"

    def _create_key(self, value):
        return "{}.{}".format(self.cache_prefix, value)

    @staticmethod
    def _get_timestamp(timedelta=None):
        date_time = datetime.datetime.utcnow()
        if timedelta:
            date_time = date_time + timedelta
        return calendar.timegm(date_time.timetuple())

    def _get_checksum(self, checksum):
        if not checksum and not self.global_checksum:
            return None
        if self.global_checksum:
            checksum = "{}-{}".format(self.global_checksum, checksum)
        else:
            checksum = str(checksum)
        return reduce(lambda x, y: x + y, map(ord, checksum))

    @abc.abstractmethod
    def get(self, cache_id, checksum=None):
        """
        Method for fetching values from cache locations
        :param cache_id: ID of cache item to fetch
        :type cache_id: str
        :param checksum: Optional checksum to compare against
        :type checksum: str,int
        :return: Value of cache object if valid and not expired
                 CacheBase.NOT_CACHED if invalid or expired
        :rtype: Any
        """

    @abc.abstractmethod
    def set(self, cache_id, data, checksum=None, expiration=datetime.timedelta(hours=24)):
        """
        Stores new value in cache location
        :param cache_id: ID of cache to create
        :type cache_id: str
        :param data: value to store in cache
        :type data: Any
        :param checksum: Optional checksum to apply to item
        :type checksum: str,int
        :param expiration: Expiration of cache value in seconds since epoch
        :type expiration: int
        :return: None
        :rtype:
        """

    @abc.abstractmethod
    def do_cleanup(self):
        """
        Process cleaning up expired values from cache locations
        :return:
        :rtype:
        """

    @abc.abstractmethod
    def clear_all(self):
        """
        Drop all values in cache locations
        :return:
        :rtype:
        """

    def close(self):
        """
        Close connections to cache location
        :return:
        :rtype:
        """
        self._exit = True


class Cache(CacheBase):
    """
    Ease of use class to handle storing and retrieving from both mem and disk cache
    """

    def __init__(self):
        super(Cache, self).__init__()
        self.enable_mem_cache = True
        self._mem_cache = MemCache()
        self._db_cache = DatabaseCache(g.CACHE_DB_PATH, schema, rebuild_callback=self._mem_cache.do_cleanup)
        self._auto_clean_interval = datetime.timedelta(hours=4)

    def set_auto_clean_interval(self, interval):
        """
        Sets the auto clean interval to 4 hours if not interval is provided else set it to the interval provided
        :param interval: Timedelta hours to set for interval
        :type interval: datetime.timedelta
        :return:
        :rtype:
        """
        self._auto_clean_interval = datetime.timedelta(hours=4) if not interval else interval

    def get(self, cache_id, checksum=None):
        checksum = self._get_checksum(checksum)
        result = self.NOT_CACHED
        if self.enable_mem_cache:
            result = self._mem_cache.get(cache_id, checksum)
        if result == self.NOT_CACHED:
            result = self._db_cache.get(cache_id, checksum)
            if not result == self.NOT_CACHED and self.enable_mem_cache:
                self._mem_cache.set(cache_id, result, checksum)
        return result

    def set(
            self, cache_id, data, checksum=None, expiration=datetime.timedelta(hours=24)
            ):
        checksum = self._get_checksum(checksum)
        if self.enable_mem_cache and not self._exit:
            self._mem_cache.set(cache_id, data, checksum, expiration)
        if not self._exit:
            self._db_cache.set(cache_id, data, checksum, expiration)

    def _cleanup_required_check(self, lastexecuted, cur_time):
        return (eval(lastexecuted) + self._auto_clean_interval) < cur_time

    def check_cleanup(self):
        """
        Check if a cleanup should be run according to auto_clean_interval and process if required
        :return:
        :rtype:
        """
        cur_time = datetime.datetime.utcnow()
        lastexecuted = g.get_runtime_setting(self._create_key("clean.lastexecuted"))
        if not lastexecuted:
            g.set_runtime_setting(self._create_key("clean.lastexecuted"), repr(cur_time))
        elif self._cleanup_required_check(lastexecuted, cur_time):
            self.do_cleanup()

    def do_cleanup(self):
        if self._exit or g.abort_requested():
            return
        if g.get_runtime_setting(self._create_key("clean.busy")):
            return
        g.set_runtime_setting(self._create_key("clean.busy"), "busy")

        cur_time = datetime.datetime.utcnow()

        self._db_cache.do_cleanup()
        self._mem_cache.do_cleanup()

        g.set_runtime_setting(self._create_key("clean.lastexecuted"), repr(cur_time))
        g.clear_runtime_setting(self._create_key("clean.busy"))

    def clear_all(self):
        self._db_cache.clear_all()
        self._mem_cache.clear_all()

    def __del__(self):
        if not self._exit:
            self.close()


class DatabaseCache(Database, CacheBase):
    """
    Handles disk stored caching
    """

    def __init__(self, db_file, database_layout, rebuild_callback=None):
        self.rebuild_callback = rebuild_callback
        super(DatabaseCache, self).__init__(db_file, database_layout)
        CacheBase.__init__(self)
        self.cache_table_name = next(iter(database_layout))

    def rebuild_database(self):
        super(DatabaseCache, self).rebuild_database()
        if callable(self.rebuild_callback):
            self.rebuild_callback()

    def do_cleanup(self):
        if self._exit or g.abort_requested():
            return
        cur_time = datetime.datetime.utcnow()
        if g.get_runtime_setting(self._create_key("cache.db.clean.busy")):
            return
        g.set_runtime_setting(self._create_key("cache.db.clean.busy"), "busy")
        query = "DELETE FROM {} where expires < ?".format(self.cache_table_name)
        self.execute_sql(query, (self._get_timestamp(),))
        g.set_runtime_setting(self._create_key("cache.mem.clean.busy"), repr(cur_time))
        g.clear_runtime_setting(self._create_key("cache.mem.clean.busy"))

    def get(self, cache_id, checksum=None):
        cur_time = self._get_timestamp()
        query = "SELECT expires, data, checksum FROM {} WHERE id = ?".format(
            self.cache_table_name
        )
        cache_data = self.fetchone(query, (cache_id,))
        if (
                cache_data
                and cache_data["expires"] > cur_time
                and (not checksum or cache_data["checksum"] == checksum)
        ):
            return cache_data["data"]
        return self.NOT_CACHED

    def set(self, cache_id, data, checksum=None, expiration=datetime.timedelta(hours=24)):
        expires = self._get_timestamp(expiration)
        query = "INSERT OR REPLACE INTO {}( id, expires, data, checksum) " \
                "VALUES (?, ?, ?, ?)".format(self.cache_table_name)
        self.execute_sql(query, (cache_id, expires, data, checksum))

    def clear_all(self):
        self.rebuild_database()

    def close(self):
        super(DatabaseCache, self).close()


class MemCache(CacheBase):
    """
    Handles in memory caching
    """

    def __init__(self):
        super(MemCache, self).__init__()
        self._index_key = self._create_key("cache.index")
        self._index = set()
        self._get_index()

    def _get_index(self):
        index = g.get_runtime_setting(self._index_key)
        if index:
            self._index = set(index)

    def _save_index(self):
        cached_string = list(self._index)
        g.set_runtime_setting(self._index_key, cached_string)

    def _clear_index(self):
        self._get_index()
        g.clear_runtime_setting(self._index_key)
        self.index = set()

    def get(self, cache_id, checksum=None):
        cached = g.get_runtime_setting(cache_id)
        cur_time = self._get_timestamp()
        if cached:
            cached = pickle.loads(codecs.decode(cached.encode(), "base64"))
            if cached[0] > cur_time:
                if not checksum or checksum == cached[2]:
                    return cached[1]
            else:
                g.clear_runtime_setting(cache_id)
        return self.NOT_CACHED

    def set(
            self, cache_id, data, checksum=None, expiration=datetime.timedelta(hours=24)
            ):
        expires = self._get_timestamp(expiration)
        cached = (expires, data, checksum)
        g.set_runtime_setting(
            cache_id,
            codecs.encode(pickle.dumps(cached), "base64").decode(),
            )
        self._get_index()
        self._index.add((cache_id, expires))
        self._save_index()

    def do_cleanup(self):
        if self._exit or g.abort_requested():
            return
        cur_time = datetime.datetime.utcnow()
        cur_timestamp = self._get_timestamp()
        if g.get_runtime_setting(self._create_key("cache.mem.clean.busy")):
            return
        g.set_runtime_setting(self._create_key("cache.mem.clean.busy"), "busy")

        self._get_index()
        for cache_id, expires in self._index:
            if expires < cur_timestamp:
                g.clear_runtime_setting(cache_id)

        g.set_runtime_setting(self._create_key("cache.mem.clean.busy"), repr(cur_time))
        g.clear_runtime_setting(self._create_key("cache.mem.clean.busy"))

    def clear_all(self):
        self._get_index()
        for cache_id, expires in self._index:
            g.clear_runtime_setting(cache_id)
        self._clear_index()

    def close(self):
        super(MemCache, self).close()


def use_cache(cache_hours=12):
    """
    Ease of use decorator to automate caching of method calls
    :param cache_hours: Hours to cache return value for
    :type cache_hours: int
    :return: Functions return value
    :rtype: Any
    """

    def _get_checksum(class_name, func_name):
        relative_methods = {"TraktAPI": {"get_json_cached": ("item.limit",)}}

        settings = relative_methods.get(class_name, {}).get(func_name, [])
        checksum = ""
        for setting in settings:
            checksum += g.get_setting(setting)

        return checksum

    def _decorator(func):
        @wraps(func)
        def _decorated(*args, **kwargs):
            method_class = args[0]

            for a in args[1:]:
                if isinstance(a, types.GeneratorType):
                    raise UnsupportedCacheParamException("generator")

            for k, v in kwargs.items():
                if isinstance(v, types.GeneratorType):
                    raise UnsupportedCacheParamException("generator")

            try:
                global_cache_ignore = g.get_runtime_setting("ignore.cache")
            except Exception:
                global_cache_ignore = False
            checksum = _get_checksum(method_class.__class__.__name__, func.__name__)
            ignore_cache = kwargs.pop("ignore_cache", False)
            if ignore_cache or global_cache_ignore:
                return func(*args, **kwargs)
            overwrite_cache = kwargs.pop("overwrite_cache", False)
            hours = kwargs.pop("cache_hours", cache_hours)
            cache_str = "{}.{}.{}.{}".format(
                method_class.__class__.__name__,
                func.__name__,
                control.md5_hash(args[1:]),
                control.md5_hash(kwargs))
            cached_data = g.CACHE.get(cache_str, checksum=checksum)
            if cached_data == CacheBase.NOT_CACHED or overwrite_cache:
                fresh_result = func(*args, **kwargs)
                if func.__name__ == "get_sources" and (not fresh_result or len(fresh_result[1]) == 0):
                    return fresh_result
                try:
                    g.CACHE.set(
                        cache_str,
                        fresh_result,
                        expiration=datetime.timedelta(hours=hours),
                        checksum=checksum,
                        )
                except TypeError:
                    g.log_stacktrace()
                    pass
                return fresh_result
            else:
                return cached_data

        return _decorated

    return _decorator
