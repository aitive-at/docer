"""Template helpers for the schema editor's recursive includes."""
from django import template

register = template.Library()


@register.filter(name="suffix")
def suffix(prefix, value) -> str:
    """Concatenate a string prefix with a stringified value (e.g., 'c'|suffix:0 -> 'c0')."""
    return f"{prefix}{value}"


@register.filter(name="incr")
def incr(value) -> int:
    """Return value + 1 as int. Used to bump recursion depth in template includes."""
    return int(value) + 1
