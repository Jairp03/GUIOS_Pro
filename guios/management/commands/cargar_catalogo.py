import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from guios.models import Dimension, Factor, Subfactor

DATA = Path(__file__).resolve().parents[2] / "data"
ORDEN_DIM = {"Tecnológica": 1, "Organizacional": 2, "Económica": 3}


class Command(BaseCommand):
    help = "Carga el catálogo inicial de GUIOS (3 dimensiones, 18 factores, 61 subfactores) desde la tesis."

    @transaction.atomic
    def handle(self, *args, **opts):
        subs = list(csv.reader(open(DATA / "subfactores.csv", encoding="utf-8"), delimiter="\t"))[1:]
        dim_de = {f: d for d, f, _ in subs}
        for nombre, orden in ORDEN_DIM.items():
            Dimension.objects.get_or_create(nombre=nombre, defaults={"orden": orden})
        nf = 0
        for i, (nombre, sug, alcance) in enumerate(list(csv.reader(open(DATA / "factores.csv", encoding="utf-8"), delimiter="\t"))[1:], 1):
            nivel = int(sug) - 1
            f, creado = Factor.objects.get_or_create(
                dimension=Dimension.objects.get(nombre=dim_de[nombre]), nombre=nombre,
                defaults={"alcance": alcance, "importancia_sugerida": nivel, "importancia_base": nivel, "orden": i})
            nf += creado
        ns = 0
        for i, (_, fac, texto) in enumerate(subs):
            _, creado = Subfactor.objects.get_or_create(factor=Factor.objects.get(nombre=fac), texto=texto, defaults={"orden": i})
            ns += creado
        self.stdout.write(self.style.SUCCESS(
            f"Catálogo listo: {Dimension.objects.count()} dimensiones, {Factor.objects.count()} factores, "
            f"{Subfactor.objects.count()} subfactores ({nf} factores y {ns} subfactores nuevos)."))
