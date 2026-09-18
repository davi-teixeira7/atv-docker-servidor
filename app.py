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
