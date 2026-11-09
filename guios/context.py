from django.conf import settings


def globales(request):
    """Variables disponibles en todas las plantillas."""
    es_admin = False
    if request.user.is_authenticated:
        perfil = getattr(request.user, "perfil", None)
        es_admin = bool(request.user.is_superuser or (perfil and perfil.rol == "ADMIN"))
    return {"es_admin": es_admin, "ia_llm_disponible": bool(settings.ANTHROPIC_API_KEY)}
