# Relatório — Implementação de Serviços com Docker

**Atividade:** Construção de imagem própria para aplicação Python e persistência de dados em volume
**Disciplina:** Computação em Nuvem
**Alunos:** Davi Teixeira, Nicole França
**Repositório:** https://github.com/davi-teixeira7/atv-docker-servidor

**Ambiente de execução:**

| Item | Versão |
| ---- | ------ |
| Docker Engine | 29.7.2 (build a7dcaa6) |
| Sistema hospedeiro | macOS (Darwin 25.6.0), arquitetura arm64 |
| Imagem base | `python:3.12-slim` (Python 3.12.14, Debian trixie) |
| Framework | Flask 3.1.0 |

---

## 1. A aplicação

Serviço de anotações mínimo, em Flask, que grava as anotações em um arquivo JSON dentro
do diretório apontado por `DATA_DIR` (padrão `/app/data`). São três rotas: `POST /notas`,
`GET /notas` e `GET /health`.

A escolha pelo arquivo JSON em vez de SQLite foi deliberada: o objetivo da atividade é
demonstrar empacotamento e persistência, não modelagem de dados. Com JSON o arquivo
gravado no volume é legível a olho nu (`docker exec ... cat /app/data/notas.json`), o que
torna a prova de persistência mais direta.

`app.py`:

```python
import json
import os
from datetime import datetime

from flask import Flask, jsonify, request

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
ARQUIVO = os.path.join(DATA_DIR, "notas.json")

app = Flask(__name__)


def ler_notas():
    if not os.path.exists(ARQUIVO):
        return []
    with open(ARQUIVO, encoding="utf-8") as f:
        return json.load(f)


def gravar_notas(notas):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(notas, f, ensure_ascii=False, indent=2)


@app.post("/notas")
def criar_nota():
    texto = (request.get_json(silent=True) or {}).get("texto")
    if not texto:
        return jsonify({"erro": "campo 'texto' e obrigatorio"}), 400

    notas = ler_notas()
    nota = {
        "id": len(notas) + 1,
        "texto": texto,
        "criada_em": datetime.now().isoformat(timespec="seconds"),
    }
    notas.append(nota)
    gravar_notas(notas)
    return jsonify(nota), 201


@app.get("/notas")
def listar_notas():
    return jsonify(ler_notas())


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
```

Dois detalhes importam para a atividade:

- `os.environ.get("DATA_DIR", "/app/data")` — o caminho dos dados vem do ambiente, com
  padrão `/app/data`. É isso que permite rodar a mesma aplicação localmente
  (`DATA_DIR=./data`) e dentro do container (`/app/data`), sem alterar uma linha de código.
- `app.run(host="0.0.0.0", ...)` — dentro do container o servidor precisa escutar em todas
  as interfaces. Se escutasse apenas em `127.0.0.1`, o mapeamento `-p 8000:8000` não
  alcançaria o processo, porque o "localhost" do container não é o do hospedeiro.

### Teste local, antes do Docker

```
$ DATA_DIR=./data python app.py &

$ curl http://localhost:8000/health
{"status":"ok"}

$ curl -X POST http://localhost:8000/notas -H "Content-Type: application/json" \
       -d '{"texto": "teste local fora do docker"}'
{"criada_em":"2026-09-18T09:39:11","id":1,"texto":"teste local fora do docker"}

$ curl http://localhost:8000/notas
[{"criada_em":"2026-09-18T09:39:11","id":1,"texto":"teste local fora do docker"}]

$ ls -la ./data
-rw-r--r--@ 1 user  staff  106 Sep 18 09:39 notas.json
```

---

## 2. Explicação linha a linha do Dockerfile

```dockerfile
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
```

**`FROM python:3.12-slim`**
Define a imagem base sobre a qual todas as camadas seguintes serão empilhadas. É a imagem
oficial do Python no Docker Hub, na variante `slim`: um Debian reduzido que traz o
interpretador e o `pip`, mas descarta compiladores, documentação e pacotes de
desenvolvimento. A variante padrão (`python:3.12`) passa de 1 GB; a `slim` fica em torno de
120 MB. Existe ainda a `alpine`, menor ainda, mas ela usa a biblioteca C `musl` em vez da
`glibc`, o que costuma obrigar a compilar pacotes com extensões C na mão — para esta
aplicação, a `slim` é o equilíbrio certo entre tamanho e previsibilidade.

**`WORKDIR /app`**
Cria (se não existir) e entra no diretório `/app`, que passa a ser o diretório corrente de
todas as instruções seguintes — `COPY`, `RUN` e o `CMD`. É o equivalente a um `cd` que
persiste na imagem. Sem ele, seria preciso escrever caminhos absolutos em toda instrução.

**`COPY requirements.txt .`**
Copia apenas o arquivo de dependências do contexto de build para `/app/requirements.txt`.
Copiar só esse arquivo, e não o projeto inteiro, é o ponto central da otimização de cache
explicada abaixo.

**`RUN pip install --no-cache-dir -r requirements.txt`**
Instala as dependências. O `--no-cache-dir` impede que o `pip` guarde os arquivos `.whl`
baixados dentro da imagem: esse cache só serviria para uma reinstalação futura que nunca
acontece em uma imagem imutável, então seria peso morto permanente em uma camada.

> **Por que `requirements.txt` antes do código?** Cada instrução do Dockerfile gera uma
> camada, e o Docker reaproveita do cache toda camada cujas entradas não mudaram — mas
> invalida essa e **todas as seguintes** assim que uma muda. Como o código-fonte muda a
> cada commit e as dependências quase nunca mudam, instalar as dependências *antes* de
> copiar o código faz com que editar `app.py` invalide apenas a última camada. O
> `pip install` inteiro vem do cache. Se a ordem fosse invertida (`COPY . .` e depois
> `pip install`), cada alteração de uma linha do código forçaria a reinstalação completa
> das dependências, de segundos para minutos em projetos reais.

**`COPY app.py .`**
Copia o código da aplicação, já depois da camada cara de instalação. É a última camada
"de conteúdo" e a única que realmente se refaz no dia a dia.

**`ENV DATA_DIR=/app/data`**
Grava uma variável de ambiente na imagem, disponível para qualquer processo do container.
É exatamente a variável que `app.py` lê em `os.environ.get("DATA_DIR", ...)`. Declará-la
aqui documenta a configuração e permite sobrescrevê-la na execução com
`docker run -e DATA_DIR=/outro/caminho`, sem rebuild.

**`EXPOSE 8000`**
Declara que o container escuta na porta 8000. É **documentação** — não abre porta nenhuma
sozinha. Quem de fato publica a porta no hospedeiro é o `-p 8000:8000` do `docker run`. O
valor do `EXPOSE` está em tornar o contrato da imagem explícito e em habilitar
`docker run -P`, que publica automaticamente as portas declaradas.

**`VOLUME /app/data`**
Marca `/app/data` como ponto de montagem de volume. Na prática: se alguém rodar o container
sem montar nada nesse caminho, o Docker cria um **volume anônimo** e o monta ali, de modo
que as gravações caiam fora da camada gravável do container. Isso protege os dados de
acidentes e evita que o arquivo cresça dentro do sistema de arquivos em camadas (que usa
copy-on-write, ineficiente para escrita frequente). Vale registrar a limitação, comprovada
na Etapa 6: o `VOLUME` **não** garante persistência útil — o volume anônimo recebe um nome
aleatório, não é reencontrado por um container novo e vira lixo órfão. Persistência de
verdade exige um volume *nomeado* no `docker run`.

**`CMD ["python", "app.py"]`**
Define o processo principal (PID 1) do container. Está na forma *exec* (lista JSON), e não
na forma *shell* (`CMD python app.py`): na forma exec o Python vira o processo 1 diretamente
e recebe os sinais do Docker, então `docker stop` encerra o servidor de forma limpa. Na
forma shell, o PID 1 seria `/bin/sh -c`, que não repassa `SIGTERM` ao filho — o container só
morreria no `SIGKILL`, após o timeout de 10 segundos.

### `.dockerignore`

```
__pycache__/
*.pyc
.git/
.gitignore
.venv/
venv/
data/
README.md
RELATORIO.md
```

O `.dockerignore` filtra o que o cliente Docker envia ao daemon como contexto de build. Sem
ele, todo o diretório subiria — incluindo o histórico do `.git/`, o ambiente virtual `.venv/`
(centenas de MB) e, o mais grave nesta atividade, o diretório `data/` gerado pelo teste
local. Dados de teste dentro da imagem seriam um contrassenso: a atividade inteira trata
justamente de manter os dados *fora* da imagem. Além do tamanho, há o efeito no cache —
qualquer arquivo do contexto que mude invalida as camadas de `COPY`, então um `data/` que
muda a cada requisição arruinaria o cache de build. O resultado aparece na saída do build:
`transferring context: 118B`.

---

## 3. Etapa 3 — Build da imagem

```
$ docker build -t notas-api:1.0 .

#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 681B done
#1 DONE 0.0s

#2 [internal] load metadata for docker.io/library/python:3.12-slim
#2 DONE 3.0s

#3 [internal] load .dockerignore
#3 transferring context: 118B done
#3 DONE 0.0s

#5 [1/5] FROM docker.io/library/python:3.12-slim@sha256:78387bc3881b8273120a12eb...
#5 extracting sha256:8aff2d3a9af8ed70ae2aa065663f6a7b99d3cd41564528e8d5f039ec0faae595 0.8s done
#5 DONE 3.1s

#6 [2/5] WORKDIR /app
#6 DONE 0.0s

#7 [3/5] COPY requirements.txt .
#7 DONE 0.0s

#8 [4/5] RUN pip install --no-cache-dir -r requirements.txt
#8 3.574 Installing collected packages: MarkupSafe, itsdangerous, click, blinker, Werkzeug, Jinja2, flask
#8 3.977 Successfully installed Jinja2-3.1.6 MarkupSafe-3.0.3 Werkzeug-3.1.8 blinker-1.9.0 click-8.5.0 flask-3.1.0 itsdangerous-2.2.0
#8 DONE 4.3s

#9 [5/5] COPY app.py .
#9 DONE 0.0s

#10 exporting to image
#10 exporting manifest sha256:b06a0b55dd35e698c28530a78894d599d2cf916d6a02c1d5c52163b851c05597 done
#10 naming to docker.io/library/notas-api:1.0 done
#10 DONE 0.8s
```

### Tamanho final da imagem

```
$ docker image ls notas-api
IMAGE           ID             DISK USAGE   CONTENT SIZE   EXTRA
notas-api:1.0   df17cbea5fea        234MB         51.8MB
```

O Docker 29 separa duas medidas: **DISK USAGE (234 MB)** é o espaço ocupado no disco pelas
camadas descompactadas, e **CONTENT SIZE (51,8 MB)** é o tamanho comprimido que trafegaria
em um `docker push`/`pull`. Das camadas descompactadas, praticamente tudo vem da base —
109 MB do sistema Debian mínimo mais 44,6 MB da compilação do Python. A aplicação em si
custa 15,5 MB (Flask e suas dependências) e 12,3 kB (`app.py`). Ou seja: **mais de 90% da
imagem é a base oficial**, e é exatamente por isso que a escolha da variante `slim` importa
mais do que qualquer otimização no código.

### Lista de camadas

```
$ docker history notas-api:1.0
IMAGE          CREATED          CREATED BY                                      SIZE      COMMENT
df17cbea5fea   8 seconds ago    CMD ["python" "app.py"]                         0B        buildkit.dockerfile.v0
<missing>      8 seconds ago    VOLUME [/app/data]                              0B        buildkit.dockerfile.v0
<missing>      8 seconds ago    EXPOSE [8000/tcp]                               0B        buildkit.dockerfile.v0
<missing>      8 seconds ago    ENV DATA_DIR=/app/data                          0B        buildkit.dockerfile.v0
<missing>      8 seconds ago    COPY app.py . # buildkit                        12.3kB    buildkit.dockerfile.v0
<missing>      8 seconds ago    RUN /bin/sh -c pip install --no-cache-dir -r…   15.5MB    buildkit.dockerfile.v0
<missing>      12 seconds ago   COPY requirements.txt . # buildkit              12.3kB    buildkit.dockerfile.v0
<missing>      12 seconds ago   WORKDIR /app                                    8.19kB    buildkit.dockerfile.v0
<missing>      2 weeks ago      CMD ["python3"]                                 0B        buildkit.dockerfile.v0
<missing>      2 weeks ago      RUN /bin/sh -c set -eux;  for src in idle3 p…   16.4kB    buildkit.dockerfile.v0
<missing>      2 weeks ago      RUN /bin/sh -c set -eux;   savedAptMark="$(a…   44.6MB    buildkit.dockerfile.v0
<missing>      2 weeks ago      ENV PYTHON_SHA256=5c8462af5790baf43a321a1559…   0B        buildkit.dockerfile.v0
<missing>      2 weeks ago      ENV PYTHON_VERSION=3.12.14                      0B        buildkit.dockerfile.v0
<missing>      2 weeks ago      ENV GPG_KEY=7169605F62C751356D054A26A821E680…   0B        buildkit.dockerfile.v0
<missing>      2 weeks ago      RUN /bin/sh -c set -eux;  apt-get update;  a…   13.1MB    buildkit.dockerfile.v0
<missing>      2 weeks ago      ENV LANG=C.UTF-8                                0B        buildkit.dockerfile.v0
<missing>      2 weeks ago      ENV PATH=/usr/local/bin:/usr/local/sbin:/usr…   0B        buildkit.dockerfile.v0
<missing>      3 weeks ago      # debian.sh --arch 'arm64' out/ 'trixie' '@1…   109MB     debuerreotype 0.17
```

Leitura de baixo para cima: as oito camadas mais antigas ("2/3 weeks ago") vieram prontas da
imagem `python:3.12-slim` e são compartilhadas com qualquer outra imagem que use a mesma
base. As oito de cima foram criadas por este Dockerfile. Note que `ENV`, `EXPOSE`, `VOLUME` e
`CMD` ocupam **0 B**: são apenas metadados gravados no manifesto da imagem, não conteúdo de
sistema de arquivos. O `<missing>` no ID não indica erro — a partir do BuildKit, apenas a
camada final recebe um ID de imagem próprio.

---

## 4. Etapa 4 — Execução com volume nomeado

```
$ docker volume create notas-dados
notas-dados

$ docker run -d --name notas -p 8000:8000 -v notas-dados:/app/data notas-api:1.0
3dbaf4eadba92372fa484fa6b5cde7f3aa872cdef7b9ca516cdf2fd814d8d4d2

$ docker ps
CONTAINER ID   IMAGE           COMMAND           CREATED                  STATUS                  PORTS                                         NAMES
3dbaf4eadba9   notas-api:1.0   "python app.py"   Less than a second ago   Up Less than a second   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp   notas

$ docker logs notas
 * Serving Flask app 'app'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:8000
 * Running on http://172.17.0.4:8000
Press CTRL+C to quit
192.168.65.1 - - [18/Sep/2026 12:40:05] "GET /health HTTP/1.1" 200 -
```

O aviso sobre "development server" é esperado: o servidor embutido do Flask basta para uma
atividade didática; em produção a imagem rodaria um WSGI como Gunicorn ou uWSGI.

### Inserção das três anotações

```
$ curl -X POST http://localhost:8000/notas -H "Content-Type: application/json" -d '{"texto": "primeira nota"}'
{"criada_em":"2026-09-18T12:40:22","id":1,"texto":"primeira nota"}

$ curl -X POST http://localhost:8000/notas -H "Content-Type: application/json" -d '{"texto": "segunda nota"}'
{"criada_em":"2026-09-18T12:40:22","id":2,"texto":"segunda nota"}

$ curl -X POST http://localhost:8000/notas -H "Content-Type: application/json" -d '{"texto": "terceira nota"}'
{"criada_em":"2026-09-18T12:40:22","id":3,"texto":"terceira nota"}

$ curl http://localhost:8000/notas
[{"criada_em":"2026-09-18T12:40:22","id":1,"texto":"primeira nota"},
 {"criada_em":"2026-09-18T12:40:22","id":2,"texto":"segunda nota"},
 {"criada_em":"2026-09-18T12:40:22","id":3,"texto":"terceira nota"}]

$ curl http://localhost:8000/health
{"status":"ok"}
```

---

## 5. Etapa 5 — Prova de persistência

### 5.1 Destruição completa do container

```
$ docker stop notas && docker rm notas
notas
notas

$ docker ps -a --filter name=notas
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

A listagem com `-a` (que inclui containers parados) volta vazia: o container não existe mais,
nem sua camada gravável.

### 5.2 O volume continua existindo

```
$ docker volume ls
DRIVER    VOLUME NAME
local     49e84592e84b2a8735b50577021120c9cf84811311ac28f6794614227721ff9c
local     548a41ec408ce9601cf2ade938954283b7fc0d8f0282db5fa260af5ae2e80059
local     21167ae44d7776b51b2a4b903f72ffc884eb67d0d4343acd7f260b820b6414c8
local     49672549b1b8e5f4d18ac6b8dc39dc292ef9909b64688e70c740600266a51b61
local     a29d0c9eec28342443ce3d0c1aa49556e5960abc6bd982b60048c62ed96dabb6
local     docker_mysql_data
local     docker_redis_data
local     notas-dados
local     teste_volumes

$ docker volume inspect notas-dados
[
    {
        "CreatedAt": "2026-09-18T12:40:05Z",
        "Driver": "local",
        "Labels": null,
        "Mountpoint": "/var/lib/docker/volumes/notas-dados/_data",
        "Name": "notas-dados",
        "Options": null,
        "Scope": "local"
    }
]
```

`notas-dados` está lá, intacto, mesmo sem container algum usando-o. É essa independência de
ciclo de vida que define um volume.

### 5.3 Novo container com o mesmo volume

```
$ docker run -d --name notas2 -p 8000:8000 -v notas-dados:/app/data notas-api:1.0
3bbf71c8916367a2527414e502ef253022fe70cee7e8c668bbf76e87de31de65
```

### 5.4 As anotações continuam lá

```
$ curl http://localhost:8000/notas
[{"criada_em":"2026-09-18T12:40:22","id":1,"texto":"primeira nota"},
 {"criada_em":"2026-09-18T12:40:22","id":2,"texto":"segunda nota"},
 {"criada_em":"2026-09-18T12:40:22","id":3,"texto":"terceira nota"}]
```

**Persistência comprovada.** As três anotações têm carimbo `12:40:22`, gravado pelo container
`notas`, que já não existe. Quem responde agora é o container `notas2`, criado depois — e ele
devolve exatamente os mesmos dados, com os mesmos horários. Os dados sobreviveram à destruição
do container porque nunca estiveram *nele*: estiveram no volume, montado sobre `/app/data`.

---

## 6. Etapa 6 — Contraexemplo: a efemeridade sem `-v`

Mesma sequência, com um único comando diferente: `docker run` **sem** a opção `-v`.

```
$ docker run -d --name notas-sem-volume -p 8000:8000 notas-api:1.0
3f6a06b7977c60102f0605e7120b01dfe317d61574a92caf023cd462a53a948e

$ curl -X POST ... (três anotações)
{"criada_em":"2026-09-18T12:40:56","id":1,"texto":"nota efemera 1"}
{"criada_em":"2026-09-18T12:40:56","id":2,"texto":"nota efemera 2"}
{"criada_em":"2026-09-18T12:40:56","id":3,"texto":"nota efemera 3"}

$ curl http://localhost:8000/notas
[{"criada_em":"2026-09-18T12:40:56","id":1,"texto":"nota efemera 1"},
 {"criada_em":"2026-09-18T12:40:56","id":2,"texto":"nota efemera 2"},
 {"criada_em":"2026-09-18T12:40:56","id":3,"texto":"nota efemera 3"}]
```

Até aqui, tudo funciona igual. Agora a destruição e a recriação:

```
$ docker stop notas-sem-volume && docker rm notas-sem-volume
notas-sem-volume
notas-sem-volume

$ docker run -d --name notas-sem-volume -p 8000:8000 notas-api:1.0
74c1f2c0ed15009e71779fc24c366c2049c8123cdb8a13b50dd7a73a94f10bf9

$ curl http://localhost:8000/notas
[]
```

**As três anotações desapareceram.**

### Por que isso acontece

Uma imagem Docker é uma pilha de camadas **somente leitura**. Ao criar um container, o Docker
acrescenta no topo dessa pilha uma única camada **gravável**, que pertence àquele container e
só a ele. Toda escrita feita pelo processo — inclusive `/app/data/notas.json` — vai parar
nessa camada (mecanismo de *copy-on-write*). O `docker rm` apaga o container e, junto, a sua
camada gravável: tudo o que foi escrito ali some. O container seguinte nasce da mesma imagem
imutável, sem nenhuma das escritas do anterior — daí a lista vazia. Esse é exatamente o
sentido de "o sistema de arquivos de um container é efêmero".

O `-v notas-dados:/app/data` muda essa história: ele monta, sobre o caminho `/app/data`, um
diretório gerenciado pelo Docker Engine que vive **fora** da pilha de camadas. As escritas
nesse caminho passam ao largo do copy-on-write e não têm relação alguma com o ciclo de vida do
container.

### Um detalhe revelado pela inspeção

O Dockerfile declara `VOLUME /app/data`, e vale conferir o que isso de fato fez no
contraexemplo:

```
$ docker inspect notas-sem-volume --format "{{json .Mounts}}"
[{"Type":"volume",
  "Name":"db042e592bb1b851b57d1f2a7f10ea904ed6e35e4871d05633b4f88488282b18",
  "Source":"/var/lib/docker/volumes/db042e59.../_data",
  "Destination":"/app/data","Driver":"local","RW":true}]

$ docker volume ls -f dangling=true
DRIVER    VOLUME NAME
local     87b38607181242c69bb107f21446dd0d23ed98a34a3137bbc007b4383123ceb1
```

Tecnicamente, os dados não foram destruídos: por causa do `VOLUME` do Dockerfile, o Docker
criou para cada container um **volume anônimo**, de nome aleatório. O primeiro container usou
o volume `87b38607...`, que sobrou órfão (`dangling`) depois do `docker rm`; o segundo ganhou
um volume novinho e vazio, `db042e59...`. Do ponto de vista da aplicação o efeito é idêntico à
perda total: os dados estão em um volume de nome imprevisível, que nenhum container novo
reencontra e que ninguém sabe que precisa limpar — vira lixo acumulando disco. É por isso que
o `VOLUME` do Dockerfile **não substitui** o volume nomeado: ele garante que a escrita saia da
camada gravável, mas só o `-v <nome>:/app/data` dá aos dados uma identidade estável, que pode
ser reencontrada, inspecionada e versionada.

---

## 7. Etapa 7 — Inspeção

### 7.1 Onde, no host, o Docker armazena fisicamente o volume `notas-dados`?

```
$ docker volume inspect notas-dados --format "{{ .Mountpoint }}"
/var/lib/docker/volumes/notas-dados/_data

$ docker inspect notas2 --format "{{json .Mounts}}"
[{"Type":"volume","Name":"notas-dados",
  "Source":"/var/lib/docker/volumes/notas-dados/_data",
  "Destination":"/app/data","Driver":"local","Mode":"z","RW":true,"Propagation":""}]
```

O caminho é **`/var/lib/docker/volumes/notas-dados/_data`**. O padrão é sempre
`/var/lib/docker/volumes/<nome-do-volume>/_data` para o driver `local`, e esse diretório é
área gerenciada pelo Docker Engine — não se mexe nele à mão.

Há uma ressalva importante neste ambiente, e ela é verificável:

```
$ ls -la /var/lib/docker/volumes/notas-dados/_data
ls: /var/lib/docker/volumes/notas-dados/_data: No such file or directory
```

Em Linux esse caminho existiria diretamente no sistema de arquivos do hospedeiro. Em macOS
(e Windows), o Docker Engine roda dentro de uma **máquina virtual Linux** gerenciada pelo
Docker Desktop, e `/var/lib/docker` é o sistema de arquivos *dessa VM*, não o do macOS. Por
isso o `ls` do macOS não encontra nada. Para enxergar o conteúdo real, monta-se o volume em um
container auxiliar:

```
$ docker run --rm -v notas-dados:/vol alpine ls -la /vol
total 12
drwxr-xr-x    2 root     root          4096 Sep 18 12:40 .
drwxr-xr-x    1 root     root          4096 Sep 18 12:41 ..
-rw-r--r--    1 root     root           274 Sep 18 12:40 notas.json
```

### 7.2 Qual é o conteúdo do diretório `/app/data` dentro do container?

```
$ docker exec notas2 ls -la /app/data
total 12
drwxr-xr-x 2 root root 4096 Sep 18 12:40 .
drwxr-xr-x 1 root root 4096 Sep 18 12:40 ..
-rw-r--r-- 1 root root  274 Sep 18 12:40 notas.json

$ docker exec notas2 cat /app/data/notas.json
[
  {
    "id": 1,
    "texto": "primeira nota",
    "criada_em": "2026-09-18T12:40:22"
  },
  {
    "id": 2,
    "texto": "segunda nota",
    "criada_em": "2026-09-18T12:40:22"
  },
  {
    "id": 3,
    "texto": "terceira nota",
    "criada_em": "2026-09-18T12:40:22"
  }
]
```

Um único arquivo, `notas.json`, com 274 bytes — o mesmo tamanho e o mesmo horário mostrados
pelo container auxiliar `alpine` no item anterior. São duas visões do mesmo diretório físico:
`/app/data` dentro do container **é** `/var/lib/docker/volumes/notas-dados/_data`. O ponto de
montagem apenas conecta os dois caminhos.

### 7.3 O que acontece com os dados ao executar `docker volume rm notas-dados` com o container parado e removido?

Primeiro, uma constatação: com o container apenas **parado** (mas ainda existente), o Docker
se recusa a remover o volume.

```
$ docker stop notas2
$ docker volume rm notas-dados
Error response from daemon: remove notas-dados: volume is in use - [3bbf71c8916367a2527414e502ef253022fe70cee7e8c668bbf76e87de31de65]
```

O daemon considera "em uso" qualquer volume referenciado por um container existente, esteja
ele rodando ou não. É uma trava de segurança: um container parado pode ser reiniciado e
esperaria seus dados no lugar.

Removido o container, o volume sai sem resistência:

```
$ docker rm notas2
notas2

$ docker volume rm notas-dados
notas-dados

$ docker volume ls | grep notas-dados
(nenhum resultado: o volume nao existe mais)

$ docker volume inspect notas-dados
[]
Error response from daemon: get notas-dados: no such volume
```

E os dados vão junto, de forma **definitiva e irreversível**. Um container novo apontando para
um volume de mesmo nome não recupera nada: o Docker simplesmente cria um volume novo e vazio
com aquele nome.

```
$ docker run -d --name notas3 -p 8000:8000 -v notas-dados:/app/data notas-api:1.0
cba02832430e39bc367752cb28ce21122433e8caeea513a3c12153167ca3a3ce

$ curl http://localhost:8000/notas
[]
```

**Resposta:** `docker volume rm` apaga o diretório `_data` do volume no disco. Não existe
lixeira, `undo` nem histórico — o único caminho de volta é um backup feito antes. É o comando
mais destrutivo desta atividade, e a assimetria vale ser notada: destruir o *container* é uma
operação rotineira e sem consequências (foi a Etapa 5 inteira), enquanto destruir o *volume* é
perda de dados permanente. Volume é o estado; container é descartável. O mesmo vale para
`docker volume prune`, que remove de uma vez todos os volumes órfãos — inclusive os anônimos
que a Etapa 6 revelou, mas também qualquer volume nomeado que esteja temporariamente sem
container.

---

## 8. Síntese das etapas

| Cenário | Comando de execução | Após `docker rm` + novo container |
| ------- | ------------------- | --------------------------------- |
| Com volume nomeado | `docker run -v notas-dados:/app/data ...` | As 3 anotações continuam lá |
| Sem `-v` (volume anônimo) | `docker run ...` | Lista vazia — volume anônimo órfão |
| Volume nomeado removido | `docker volume rm notas-dados` | Lista vazia — perda definitiva |

---

## 9. Dificuldades e aprendizados

A parte que eu imaginava ser a mais trabalhosa acabou sendo a mais tranquila: subir a API
HTTP em si. Com o Flask, as três rotas couberam em poucas linhas, e o único ajuste que
exigiu atenção foi lembrar de escutar em `0.0.0.0` em vez de `127.0.0.1` — dentro do
container, o "localhost" não é o mesmo da minha máquina, e sem isso o `-p 8000:8000` não
alcançaria o processo. Fora esse detalhe, a aplicação estava rodando localmente em poucos
minutos, o que confirmou na prática a dica do enunciado de manter o serviço pequeno: o
aprendizado da atividade não estava no código.

A documentação oficial do Docker assustou no começo pelo volume de conteúdo — são muitas
páginas, muitas opções e muitas instruções de Dockerfile que eu ainda não sabia se
precisava ou não. Depois de me acostumar com o formato, porém, percebi que ela é bastante
clara e direta: cada instrução tem sua página, com exemplo e explicação do efeito prático.
O que mudou foi o meu jeito de ler. Parei de tentar ler tudo de uma vez e passei a
procurar a instrução específica que estava usando naquele momento, o que tornou a consulta
muito mais rápida.

A maior dificuldade real foi o conceito de **tag de imagem**, que era novo para mim. Levei
um tempo para entender que `notas-api:1.0` não é o nome de um arquivo, e sim um rótulo que
aponta para uma imagem identificada por um hash, e que a mesma imagem pode ter várias tags
apontando para ela. Também demorou a cair a ficha de que `python:3.12-slim` segue
exatamente a mesma lógica — `python` é o repositório e `3.12-slim` é a tag que escolhe a
variante da base. Confundi tag com "versão da minha aplicação" algumas vezes antes de
entender que ela é apenas um apelido mutável, e que quem identifica a imagem de forma
única é o digest `sha256:...` que aparece na saída do build.

Por fim, as perguntas da Etapa 7 foram o que mais me ajudou. Até ali eu estava
basicamente seguindo comandos; ao ter que responder onde o volume fica no host, o que
existe dentro de `/app/data` e o que acontece ao removê-lo, fui obrigado a rastrear o
caminho completo do dado — da requisição `curl`, para o `notas.json` em `/app/data` dentro
do container, para o diretório do volume gerenciado pelo Docker Engine, e de volta na
leitura feita por um container diferente. Foi nesse ponto que o funcionamento deixou de
ser decoreba de comando e passou a fazer sentido: o ponto de montagem é só a ligação entre
dois caminhos, e o que decide se o dado sobrevive é de que lado dessa ligação ele foi
escrito.

---

## 10. Referências

DOCKER INC. **Docker Docs: Get started**. Disponível em: https://docs.docker.com/get-started/. Acesso em: 18 set. 2026.

DOCKER INC. **Dockerfile reference**. Disponível em: https://docs.docker.com/reference/dockerfile/. Acesso em: 18 set. 2026.

DOCKER INC. **Volumes**. Disponível em: https://docs.docker.com/engine/storage/volumes/. Acesso em: 18 set. 2026.

DOCKER INC. **Building best practices**. Disponível em: https://docs.docker.com/build/building/best-practices/. Acesso em: 18 set. 2026.

DOCKER INC. **python – Official Image**. Docker Hub. Disponível em: https://hub.docker.com/_/python. Acesso em: 18 set. 2026.

MOUAT, Adrian. **Usando Docker: desenvolvendo e implantando software com containers**. São Paulo: Novatec, 2017.
