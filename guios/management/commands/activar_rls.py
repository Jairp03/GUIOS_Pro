from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = ("Activa Row Level Security en todas las tablas (solo PostgreSQL/Supabase). Así la API pública de "
            "Supabase no puede leer los datos; Django se conecta con el rol 'postgres', que no se ve afectado.")

    def handle(self, *args, **opts):
        if connection.vendor != "postgresql":
            self.stdout.write("La base de datos actual no es PostgreSQL; no hay nada que hacer.")
            return
        tablas = connection.introspection.table_names()
        with connection.cursor() as c:
            for t in tablas:
                c.execute(f'ALTER TABLE "public"."{t}" ENABLE ROW LEVEL SECURITY')
        self.stdout.write(self.style.SUCCESS(f"RLS activado en {len(tablas)} tablas."))
