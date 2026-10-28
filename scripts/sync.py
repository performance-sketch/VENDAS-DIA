"""Busca no Rezdy as reservas criadas nos últimos ~75 dias e gera dados.js (aberto, sem senha).

Uso: REZDY_API_KEY=... python scripts/sync.py
Grava por reserva: data/hora da criação, valores, pax, origem, produtos, extras e, nas internas,
o vendedor (quem criou no Rezdy). Nenhum dado de cliente (nome, e-mail, telefone) nem número de pedido.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

API = "https://api.rezdy.com/v1/"
TZ = timezone(timedelta(hours=-3))  # America/Sao_Paulo (sem horário de verão)
DIAS = 75  # cobre o ciclo anterior inteiro mesmo navegando ~2 semanas para trás
SAIDA = os.path.join(os.path.dirname(__file__), "..", "dados.js")

KEY = os.environ.get("REZDY_API_KEY") or os.environ.get("REZDY_KEY")
if not KEY:
    sys.exit("REZDY_API_KEY não definido")


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
        "f": round(foc, 2),  # cortesias (free of charge)
        "e": round(sum(v for _, v in ext.values()), 2),
        "px": sum(i.get("totalQuantity") or 0 for i in itens),
        "o": (b.get("source") or "ONLINE").upper(),
        "x": [[n, q, round(v, 2)] for n, (q, v) in ext.items()],
        "it": [[i.get("productName") or "?", i.get("totalQuantity") or 0] for i in itens],
    })
    if linhas[-1]["o"] == "INTERNAL":
        por = b.get("createdBy") or {}
        linhas[-1]["v"] = f"{por.get('firstName', '')} {por.get('lastName', '')}".strip() or "Sem vendedor"
linhas.sort(key=lambda r: (r["d"], r["h"]))

dados = {"desde": str(desde), "atualizado": agora.strftime("%Y-%m-%d %H:%M"), "r": linhas}
with open(SAIDA, "w", encoding="utf-8") as f:
    f.write("// GERADO POR scripts/sync.py: não editar à mão\n")
    f.write("const DADOS=" + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n")
print(f"{len(linhas)} reservas confirmadas desde {desde} · atualizado {dados['atualizado']}")
