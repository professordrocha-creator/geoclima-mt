# maps/models.py
from django.contrib.gis.db import models


class Municipio(models.Model):
    """
    Malha municipal do Brasil (IBGE). A tabela guarda TODOS os municípios
    do país — a plataforma é genérica por design; o recorte de pesquisa
    (Tangará da Serra e Cáceres, MT) é só dado marcado nos campos
    `ativo`/`destaque`, nunca uma condição em código. Ver docs/DECISOES.md.
    """

    nome = models.CharField(max_length=100, verbose_name="Nome do Município")
    uf = models.CharField(max_length=2, verbose_name="UF")
    codigo_ibge = models.CharField(
        max_length=7, unique=True, db_index=True, verbose_name="Código IBGE"
    )

    # Polígono do município (malha do IBGE), reprojetado para WGS84 e
    # simplificado no momento da importação — ver import_municipios.
    geom = models.MultiPolygonField(srid=4326, verbose_name="Geometria")

    # Processamento de dados científicos pesados (CHIRPS, SPI, validação)
    # habilitado para este município. Controla o que roda nas Etapas 3/7,
    # não o que aparece no seletor da Home.
    ativo = models.BooleanField(default=False, verbose_name="Ativo (processamento científico)")

    # Aparece como sugestão principal no seletor de localidade da Home.
    destaque = models.BooleanField(default=False, verbose_name="Destaque na Home")

    class Meta:
        verbose_name = "Município"
        verbose_name_plural = "Municípios"
        ordering = ["uf", "nome"]

    def __str__(self):
        return f"{self.nome} ({self.uf})"
