# farms/models.py
from django.contrib.gis.db import models
from django.contrib.auth.models import User


class Farm(models.Model):
    name = models.CharField(max_length=255, verbose_name="Nome da Fazenda")

    # Campo antigo de texto livre — mantido na tabela por compatibilidade,
    # mas não é mais preenchido pelo formulário (ver `municipio` abaixo).
    city = models.CharField(max_length=100, verbose_name="Município (texto livre, legado)", blank=True, null=True)

    # Município oficial (malha do IBGE, Etapa 2.2) — reaproveita o mesmo
    # seletor Estado→Cidade já construído para a Home, em vez de texto
    # livre digitado à mão. PROTECT (não CASCADE) de propósito: Municipio
    # é dado de referência do IBGE, não dado do usuário — apagar um
    # município não deve apagar fazendas silenciosamente.
    municipio = models.ForeignKey(
        'maps.Municipio', on_delete=models.PROTECT, related_name='farms',
        verbose_name="Município",
    )

    latitude = models.FloatField(verbose_name="Latitude")
    longitude = models.FloatField(verbose_name="Longitude")
    area = models.FloatField(verbose_name="Área (hectares)", blank=True, null=True)
    crop = models.CharField(max_length=100, verbose_name="Cultura Agrícola", blank=True, null=True)
    notes = models.TextField(verbose_name="Observações", blank=True, null=True)

    # Campo espacial do PostGIS (Ponto georreferenciado — sede/localização
    # de referência da fazenda). Continua existindo mesmo quando há
    # polígono: é o que os mapas usam pra centralizar/marcar a fazenda.
    geom = models.PointField(srid=4326, verbose_name="Localização Espacial")

    # Contorno da propriedade, opcional — preenchido ao importar um
    # shapefile (Etapa 5, ver docs/DECISOES.md). Quando presente, `geom`
    # acima é recalculado como o centroide deste polígono. Sem shapefile,
    # a fazenda continua funcionando só com o ponto (poligono fica nulo).
    poligono = models.MultiPolygonField(
        srid=4326, null=True, blank=True, verbose_name="Contorno da Propriedade (opcional)",
    )

    # Campo obrigatório de isolamento multiusuário
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='farms', verbose_name="Proprietário")

    class Meta:
        verbose_name = "Fazenda"
        verbose_name_plural = "Fazendas"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} - {self.municipio.nome}/{self.municipio.uf} ({self.owner.username})"


class Talhao(models.Model):
    """Talhão/parcela dentro de uma fazenda (PDF: 'cadastrar talhões')."""

    name = models.CharField(max_length=255, verbose_name="Nome do Talhão")
    area = models.FloatField(verbose_name="Área (hectares)", blank=True, null=True)
    crop = models.CharField(max_length=100, verbose_name="Cultura Agrícola", blank=True, null=True)
    latitude = models.FloatField(verbose_name="Latitude")
    longitude = models.FloatField(verbose_name="Longitude")

    # Ponto georreferenciado, mesmo padrão de Farm/Station. Um polígono
    # de contorno do talhão fica para uma etapa futura, se for pedido.
    geom = models.PointField(srid=4326, verbose_name="Localização Espacial")

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='talhoes', verbose_name="Fazenda")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='talhoes', verbose_name="Proprietário")

    class Meta:
        verbose_name = "Talhão"
        verbose_name_plural = "Talhões"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.farm.name})"
