# notas-api — Serviço de anotações em Docker

Atividade prática de Computação em Nuvem: construção de uma **imagem Docker própria**
para um serviço Python e demonstração de **persistência de dados em volume nomeado**.

O relatório completo da atividade, com as saídas de terminal de todas as etapas,
está em [RELATORIO.md](RELATORIO.md).

## O serviço

API HTTP mínima em Flask que guarda anotações em um arquivo JSON.

| Método | Rota      | Descrição                                          |
| ------ | --------- | -------------------------------------------------- |
| POST   | `/notas`  | Recebe `{"texto": "..."}` e salva com data/hora     |
| GET    | `/notas`  | Lista todas as anotações salvas                     |
| GET    | `/health` | Retorna `{"status": "ok"}`                          |

Os dados ficam em `$DATA_DIR/notas.json`. A variável de ambiente `DATA_DIR` tem
valor padrão `/app/data`.

## Estrutura

```
.
├── app.py             # aplicação Flask (3 rotas)
├── requirements.txt   # dependências (flask)
├── Dockerfile         # receita da imagem
├── compose.yaml        # sobe o serviço com volume nomeado em um comando
├── .dockerignore      # o que não entra no contexto de build
├── README.md
└── RELATORIO.md       # relatório da atividade
```

## Como executar

### Com Docker (modo recomendado)

```bash
# 1. construir a imagem
docker build -t notas-api:1.0 .

# 2. criar o volume nomeado onde os dados vão viver
docker volume create notas-dados

# 3. subir o container montando o volume em /app/data
docker run -d --name notas -p 8000:8000 -v notas-dados:/app/data notas-api:1.0

# 4. usar a API
curl -X POST http://localhost:8000/notas \
  -H "Content-Type: application/json" \
  -d '{"texto": "primeira nota"}'

curl http://localhost:8000/notas
curl http://localhost:8000/health
```

### Prova de persistência

```bash
docker stop notas && docker rm notas          # destrói o container
docker volume ls                              # o volume continua lá
docker run -d --name notas2 -p 8000:8000 -v notas-dados:/app/data notas-api:1.0
curl http://localhost:8000/notas              # as anotações continuam lá
```

### Com Docker Compose

`compose.yaml` já faz o build, cria o volume nomeado e sobe o container em um
comando só — equivalente às etapas 3 e 4 acima.

```bash
docker compose up -d --build
curl -X POST http://localhost:8000/notas \
  -H "Content-Type: application/json" \
  -d '{"texto": "primeira nota"}'
curl http://localhost:8000/notas

docker compose down          # remove o container, mantém o volume notas-dados
docker compose down -v       # remove também o volume (apaga os dados)
```

### Localmente, sem Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=./data python app.py
```

## Limpeza

```bash
docker rm -f notas notas2
docker volume rm notas-dados      # ATENÇÃO: isso apaga as anotações definitivamente
```
