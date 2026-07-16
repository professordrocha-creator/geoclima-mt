# Dockerfile para GeoClima MT
FROM python:3.11-slim

# Define variáveis de ambiente para o Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema e do PostGIS/GDAL no Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    postgresql-client \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Configura o diretório de trabalho no container
WORKDIR /app

# Instala as dependências do Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código do projeto para o container
COPY . /app/
