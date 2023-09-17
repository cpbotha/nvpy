import timeit
import typing
import datetime


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


AutorangeResult = typing.Tuple[int, float]


class Benchmark(typing.NamedTuple):
    label: str
    setup: typing.Callable
    func: typing.Callable

    def run(self):
        result = timeit.Timer(stmt=self.func, setup=self.setup).autorange()
        self.print_result(self.label, result)

    @staticmethod
    def convert_time_units(seconds: float):
        delta = datetime.timedelta(seconds=seconds)
        if delta < datetime.timedelta(milliseconds=1):
            return delta / datetime.timedelta(microseconds=1), 'us'
        return delta / datetime.timedelta(milliseconds=1), 'ms'

    @staticmethod
    def format_time(seconds: float) -> str:
        val, unit = Benchmark.convert_time_units(seconds)
        return f'{val} {unit}'

    @staticmethod
    def print_result(label: str, result: AutorangeResult):
        loops, elapsed = result
        elapsed, unit = Benchmark.convert_time_units(elapsed / loops)
        print(f'{label:<40} {elapsed:8.2f} {unit}/loop')
