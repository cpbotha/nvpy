def show_profile(fn):
    """ Decorator for unittest cases.
    This decorator enables profiler in a test case and prints result. It is useful for investigating bottlenecks.

    Usage:
        Decorate test methods by show_profile function.
        >>> import benchmarks
        ... class Benchmark(unittest.TestCase)
        ...     @benchmarks.show_profile    # <---
        ...     def test_something(self):
        ...         # Do something.
        ...         pass
    """
    import unittest
    import functools
    import cProfile

    @functools.wraps(fn)
    def wrapper(self: unittest.TestCase, *args, **kwargs):
        pr = cProfile.Profile()
        with pr:
            ret = fn(self, *args, **kwargs)
        pr.print_stats()
        return ret

    return wrapper
