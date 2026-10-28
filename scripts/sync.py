"""Busca no Rezdy as reservas criadas nos últimos ~75 dias e gera dados.js (criptografado).

Uso: REZDY_API_KEY=... SENHA_PAINEL=... python scripts/sync.py
Grava só agregados por reserva (data/hora da criação, valores, pax, origem, extras):
nenhum nome, e-mail, telefone ou número de pedido. Sem SENHA_PAINEL o script falha,
para nunca publicar valores em texto aberto.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

API = "https://api.rezdy.com/v1/"
TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo (sem horário de verão)
DIAS = 75  # cobre o ciclo anterior inteiro mesmo navegando ~2 semanas para trás
SAIDA = os.path.join(os.path.dirname(__file__), "..", "dados.js")

KEY = os.environ.get("REZDY_API_KEY") or os.environ.get("REZDY_KEY")
SENHA = os.environ.get("SENHA_PAINEL") or ""
if not KEY:
    sys.exit("REZDY_API_KEY não definido")
if not SENHA:
    sys.exit("SENHA_PAINEL não definido: valores não serão gravados em texto aberto")


def get(endpoint, params):
    q = urllib.parse.urlencode(dict(params, apiKey=KEY))
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(API + endpoint + "?" + q, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or tentativa == 3:
                raise
            time.sleep(5 * (tentativa + 1))


agora = datetime.now(TZ)
desde = (agora - timedelta(days=DIAS)).date()

bookings, off = [], 0
while True:
    pg = get("bookings", {
        "minDateCreated": f"{desde}T00:00:00-03:00",
        "maxDateCreated": agora.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "limit": 100, "offset": off,
    }).get("bookings") or []
    bookings += pg
    if len(pg) < 100:
        break
    off += 100

linhas = []
for b in bookings:
    if b.get("status") != "CONFIRMED":
        continue
    criado = datetime.fromisoformat((b.get("dateCreated") or "").replace("Z", "+00:00")).astimezone(TZ)
    itens = b.get("items") or []
    pags = b.get("payments") or []
    bruta = float(b.get("totalAmount") or 0)
    foc = sum(float(p.get("amount") or 0) for p in pags if p.get("type") == "FREE")
    cupom = sum(float(p.get("amount") or 0) for p in pags if p.get("type") == "PROMO_CODE")
    ext = defaultdict(lambda: [0, 0.0])
    for i in itens:
        for e in i.get("extras") or []:
            if e.get("quantity"):
                ext[e.get("name") or "?"][0] += e["quantity"]
                ext[e.get("name") or "?"][1] += float(e.get("price") or 0) * e["quantity"]
    linhas.append({
        "d": criado.strftime("%Y-%m-%d"),
        "h": criado.strftime("%H:%M"),
        "b": round(bruta, 2),
        "l": round(bruta - foc - cupom, 2),  # mesma regra do REPORTCLAUDE: vendas − FOC − cupom
        "e": round(sum(v for _, v in ext.values()), 2),
        "px": sum(i.get("totalQuantity") or 0 for i in itens),
        "o": (b.get("source") or "ONLINE").upper(),
        "x": [[n, q, round(v, 2)] for n, (q, v) in ext.items()],
    })
linhas.sort(key=lambda r: (r["d"], r["h"]))

dados = {"desde": str(desde), "atualizado": agora.strftime("%Y-%m-%d %H:%M"), "r": linhas}
sal, iv, it = os.urandom(16), os.urandom(12), 310000
chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=it).derive(SENHA.encode())
ct = AESGCM(chave).encrypt(iv, json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode(), None)
b64 = lambda x: base64.b64encode(x).decode()
with open(SAIDA, "w", encoding="utf-8") as f:
    f.write("// GERADO POR scripts/sync.py: não editar à mão\n")
    f.write(f"const ATUALIZADO={json.dumps(dados['atualizado'])};\n")
    f.write("const COFRE=" + json.dumps({"salt": b64(sal), "iv": b64(iv), "it": it, "ct": b64(ct)}) + ";\n")
print(f"{len(linhas)} reservas confirmadas desde {desde} · atualizado {dados['atualizado']}")
