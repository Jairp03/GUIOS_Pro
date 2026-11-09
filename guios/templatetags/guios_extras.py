from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..models import NIVELES, NIVELES_SUB

register = template.Library()

ICONOS = {
    "home": "M3 11l9-8 9 8M5 10v10h14V10",
    "chart": "M4 20V10M10 20V4M16 20v-7M22 20H2",
    "box": "M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8M12 13v8",
    "check": "M5 13l4 4L19 7",
    "rocket": "M5 15c-1 1-2 4-2 6 2 0 5-1 6-2M14 4c3 0 6 3 6 6-3 5-7 8-9 8l-5-5c0-2 3-6 8-9z",
    "clip": "M9 4h6v3H9zM7 5H5v16h14V5h-2M9 12h6M9 16h4",
    "history": "M3 12a9 9 0 109-9M3 4v5h5M12 7v5l3 2",
    "book": "M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2zM4 19V5M9 7h6",
    "users": "M16 20v-1a4 4 0 00-4-4H8a4 4 0 00-4 4v1M10 11a3 3 0 100-6 3 3 0 000 6zM20 20v-1a3 3 0 00-2-2.8M16 5.2a3 3 0 010 5.6",
    "spark": "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
    "bell": "M6 9a6 6 0 1112 0c0 6 2 7 2 7H4s2-1 2-7M10 20a2 2 0 004 0",
    "search": "M11 4a7 7 0 100 14 7 7 0 000-14zM21 21l-5-5",
    "plus": "M12 5v14M5 12h14",
    "logout": "M9 4H5v16h4M16 8l4 4-4 4M20 12H9",
    "arrow": "M5 12h14M13 6l6 6-6 6",
    "menu": "M4 6h16M4 12h16M4 18h16",
    "edit": "M4 20h4L19 9l-4-4L4 16zM13 7l4 4",
    "trash": "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
    "eye": "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 100 6 3 3 0 000-6z",
    "lock": "M6 11h12v9H6zM8 11V8a4 4 0 018 0v3",
}


@register.simple_tag
def icono(nombre, clase=""):
    d = ICONOS.get(nombre, ICONOS["box"])
    return format_html('<svg class="ico {}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
                       'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{}"/></svg>', clase, d)


@register.filter
def nivel(n):
    try:
        return NIVELES[int(n)]
    except (TypeError, ValueError, IndexError):
        return "—"


@register.filter
def nivel_sub(n):
    try:
        return NIVELES_SUB[int(n) - 1]
    except (TypeError, ValueError, IndexError):
        return "—"


@register.filter
def clase_foda(c):
    return {"Fortaleza": "good", "Oportunidad": "good", "Debilidad": "bad", "Amenaza": "bad"}.get(c, "neutral")


@register.filter
def clase_ir(n):
    return {0: "neutral", 1: "amber", 2: "blue", 3: "good"}.get(n, "neutral")


@register.filter
def pct25(x):
    try:
        return round(float(x) * 25)
    except (TypeError, ValueError):
        return 0


@register.filter
def iniciales(user):
    nombre = (user.get_full_name() or user.get_username() or "?").strip()
    p = nombre.split()
    return (p[0][0] + (p[1][0] if len(p) > 1 else "")).upper()
