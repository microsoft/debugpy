# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, print_function, unicode_literals

import threading


class Singleton(object):
    """A base class for a class of a singleton object.

    For any derived class T, the first invocation of T() will create the instance,
    and any future invocations of T() will return that instance.

    Concurrent invocations of T() from different threads are safe.
    """

    # All singletons share a single global construction lock, since we need to lock
    # before we can construct any objects - it cannot be created per-class in __new__.
    _lock = threading.RLock()

    # Specific subclasses will get their own _instance set in __new__.
    _instance = None

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = object.__new__(cls)
        return cls._instance

    def __init__(self):
        """For singletons, __init__ is called on every access, not just on initial
        creation. Initialization of attributes in derived classes should be done
        on class level instead.
        """
        pass


class ThreadSafeSingleton(Singleton):
    """A singleton that incorporates a lock for thread-safe access to its members.

    The lock can be acquired using the context manager protocol, and thus idiomatic
    use is in conjunction with a with-statement. For example, given derived class T::

        with T() as t:
            t.x = t.frob(t.y)

    All access to the singleton from the outside should follow this pattern for both
    attributes and method calls. Singleton members can assume that self is locked by
    the caller while they're executing, but recursive locking of the same singleton
    on the same thread is also permitted.
    """

    # TODO: use a separate data lock for each subclass to reduce contention.

    def __enter__(self):
        type(self)._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        type(self)._lock.release()

    # Prevent callers from reading or writing attributes without locking, except for
    # methods specifically marked @threadsafe_method. Such methods should perform
    # the necessary locking to guarantee safety for the callers.

    @staticmethod
    def assert_locked(self):
        lock = type(self)._lock
        assert lock.acquire(blocking=False), (
            "ThreadSafeSingleton accessed without locking. Either use with-statement, "
            "or if it is a method or property, mark it as @threadsafe_method or with "
            "@autolocked_method, as appropriate."
        )
        lock.release()

    def __getattribute__(self, name):
        value = object.__getattribute__(self, name)
        if not getattr(value, 'is_threadsafe_method', False):
            ThreadSafeSingleton.assert_locked(self)
        return value

    def __setattr__(self, name, value):
        ThreadSafeSingleton.assert_locked(self)
        return object.__setattr__(self, name, value)


def threadsafe_method(func):
    """Marks a method of a ThreadSafeSingleton-derived class as inherently thread-safe.

    A method so marked must either not use any singleton state, or lock it appropriately.
    """

    func.is_threadsafe_method = True
    return func


def autolocked_method(func):
    """Automatically synchronizes all calls of a method of a ThreadSafeSingleton-derived
    class by locking the singleton for the duration of each call.
    """

    @threadsafe_method
    def lock_and_call(self, *args, **kwargs):
        with self:
            return func(self, *args, **kwargs)

    return lock_and_call
