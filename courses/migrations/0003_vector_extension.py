from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("courses", "0002_documentchunk")]

    operations = [CreateExtension("vector")]