"""Minimal colorama stand-in for asm-differ on hosts without pip.

We run asm-differ with --format plain, so color codes are never rendered;
every attribute resolves to an empty string. (watchdog/ beside this module
is an empty package for the same reason — watch mode is never used.)
"""


class _Plain:
    def __getattr__(self, _name):
        return ""


Fore = _Plain()
Back = _Plain()
Style = _Plain()


def init(*_args, **_kwargs):
    pass
