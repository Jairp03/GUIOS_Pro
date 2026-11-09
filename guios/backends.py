from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsuarioConPerfil(ModelBackend):
    """Carga el perfil junto al usuario al recuperar una sesión."""

    def get_user(self, user_id):
        User = get_user_model()
        try:
            user = User.objects.select_related("perfil").get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
