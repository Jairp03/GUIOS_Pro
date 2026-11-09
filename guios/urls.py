from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("ingresar/", views.ingresar, name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("alternativas/", views.alternativas, name="alternativas"),
    path("evaluaciones/nueva/", views.evaluacion_nueva, name="evaluacion_nueva"),
    path("evaluaciones/<int:pk>/", views.evaluacion_detalle, name="evaluacion"),
    path("evaluaciones/<int:pk>/importancia/", views.importancia, name="importancia"),
    path("evaluaciones/<int:pk>/subfactores/", views.subfactores, name="subfactores"),
    path("evaluaciones/<int:pk>/enviar/", views.enviar, name="enviar"),
    path("evaluaciones/<int:pk>/consolidar/", views.consolidar, name="consolidar"),
    path("evaluaciones/<int:pk>/resultados/", views.resultados, name="resultados"),
    path("historial/", views.historial, name="historial"),
    path("catalogo/", views.catalogo, name="catalogo"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("ia/importancia/", views.ia_importancia, name="ia_importancia"),
]
