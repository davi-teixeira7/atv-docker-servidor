# Imagem base oficial do Python, variante enxuta (Debian slim)
FROM python:3.12-slim

# Diretorio de trabalho padrao dentro da imagem
WORKDIR /app

# Dependencias primeiro: essa camada so e reconstruida se o requirements.txt mudar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codigo da aplicacao depois, para aproveitar o cache da camada acima
COPY app.py .

# Caminho do diretorio de dados lido pela aplicacao
ENV DATA_DIR=/app/data

# Porta em que o servidor escuta
EXPOSE 8000

# Marca /app/data como ponto de montagem de volume
VOLUME /app/data

# Processo principal do container
CMD ["python", "app.py"]
