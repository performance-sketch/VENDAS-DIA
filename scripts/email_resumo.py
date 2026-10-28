"""Envia por e-mail o resumo de vendas do dia anterior, com as mesmas regras do painel.

Uso:
  python scripts/email_resumo.py --preview arquivo.html   # só gera o HTML, não envia
  SMTP_USER=... SMTP_PASS=... EMAIL_PARA=... python scripts/email_resumo.py

Lê dados.js (gerado por scripts/sync.py). Envio por SMTP do Gmail/Google Workspace
(senha de app). EMAIL_PARA aceita vários endereços separados por vírgula.
"""
import json
import os
import re
import smtplib
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape

TZ = timezone(timedelta(hours=-3))
PAINEL = "https://performance-sketch.github.io/VENDAS-DIA/"
DADOS = os.path.join(os.path.dirname(__file__), "..", "dados.js")
DSEM = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]  # date.weekday()

with open(DADOS, encoding="utf-8") as f:
    dados = json.loads(re.search(r"const DADOS=(\{.*\});", f.read()).group(1))
R = dados["r"]
DESDE = date.fromisoformat(dados["desde"])


# ── datas ──────────────────────────────────────────────────────────────────────
def d26(y, m):
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, 26)


def inicio_ciclo(d):
    return d26(d.year, d.month) if d.day >= 26 else d26(d.year, d.month - 1)


def fim_ciclo(cs):
    return d26(cs.year, cs.month + 1) - timedelta(days=1)


def ciclo_anterior(cs):
    return d26(cs.year, cs.month - 1)


def f_curto(d):
    return d.strftime("%d/%m")


# ── números ────────────────────────────────────────────────────────────────────
def brl(v):
    return "R$ " + f"{round(v):,}".replace(",", ".")


def plural(n, s):
    return f"{n} {s}{'' if n == 1 else 's'}"


def soma(de, ate):
    a = {"b": 0, "l": 0, "e": 0, "f": 0, "n": 0, "px": 0, "o": {}, "x": {}, "v": {}, "pr": {}, "c": {}}
    for r in R:
        if not (str(de) <= r["d"] <= str(ate)):
            continue
        a["b"] += r["b"]; a["l"] += r["l"]; a["e"] += r["e"]; a["f"] += r.get("f", 0)
        a["n"] += 1; a["px"] += r["px"]
        o = "MARKETPLACE" if r["o"].startswith("MARKETPLACE") else ("INTERNAL" if r["o"] == "INTERNAL" else "ONLINE")
        so = a["o"].setdefault(o, {"v": 0, "f": 0, "n": 0})
        so["v"] += r["b"]; so["f"] += r.get("f", 0); so["n"] += 1
        for nome, q, v in r["x"]:
            sx = a["x"].setdefault(nome, {"q": 0, "v": 0})
            sx["q"] += q; sx["v"] += v
        for it in r.get("it", []):
            sp = a["pr"].setdefault(it[0], {"q": 0, "n": 0, "v": 0})
            sp["q"] += it[1]; sp["n"] += 1; sp["v"] += it[2] if len(it) > 2 else 0
        if r.get("c"):
            sc = a["c"].setdefault(r["c"], {"n": 0, "d": 0, "b": 0})
            sc["n"] += 1; sc["d"] += r.get("cd", 0); sc["b"] += r["b"]
        if r.get("v"):
            sv = a["v"].setdefault(r["v"], {"b": 0, "f": 0, "e": 0, "n": 0, "px": 0, "p": {}})
            sv["b"] += r["b"]; sv["f"] += r.get("f", 0); sv["e"] += r["e"]; sv["n"] += 1; sv["px"] += r["px"]
            for it in r.get("it", []):
                sv["p"][it[0]] = sv["p"].get(it[0], 0) + it[1]
    return a


def ou_nada(de, ate):
    return soma(de, ate) if de >= DESDE else None


# ── período: ontem ─────────────────────────────────────────────────────────────
hoje = datetime.now(TZ).date()
D = hoje - timedelta(days=1)
nome_sem = DSEM[D.weekday()] + (" passado" if D.weekday() >= 5 else " passada")

dia = soma(D, D)
anteontem = ou_nada(D - timedelta(days=1), D - timedelta(days=1))
sem_passada = ou_nada(D - timedelta(days=7), D - timedelta(days=7))

seg = D - timedelta(days=D.weekday())
semana, semana_ant = soma(seg, D), ou_nada(seg - timedelta(days=7), D - timedelta(days=7))

cs = inicio_ciclo(D)
pcs = ciclo_anterior(cs)
pate = min(pcs + (D - cs), fim_ciclo(pcs))
ciclo, ciclo_ant = soma(cs, D), ou_nada(pcs, pate)
dia_ciclo, dias_ciclo = (D - cs).days + 1, (fim_ciclo(cs) - cs).days + 1


# ── texto ──────────────────────────────────────────────────────────────────────
def artigo(nome):
    if nome == "anteontem":
        return "de anteontem"
    if nome.endswith("passado") or nome == "ciclo anterior":
        return "do " + nome
    return "da " + nome


def delta_html(atual, ant, nome, cor=True):
    if ant is None:
        return ""
    if not ant:
        return f"sem vendas {artigo(nome)}" if atual else ""
    d = (atual - ant) / ant
    seta, c = ("▲", "#1a7f37") if d >= 0 else ("▼", "#c62f2f")
    estilo = f"color:{c};" if cor else ""
    return f'<b style="{estilo}">{seta} {abs(round(d * 100))}%</b> vs {escape(nome)} ({brl(ant)})'


def compara_txt(atual, ant, nome):
    if ant is None or not ant:
        return ""
    d = (atual - ant) / ant
    if abs(d) < .005:
        return f"igual ao valor {artigo(nome)}"
    return f"<b>{abs(round(d * 100))}% {'acima' if d > 0 else 'abaixo'}</b> {artigo(nome)}"


def resumo_executivo():
    a = dia
    quando = f"Ontem ({DSEM[D.weekday()]}, {f_curto(D)})"
    if not a["n"]:
        return f"{quando}, nenhuma reserva confirmada."
    frases = []
    comps = [c for c in (compara_txt(a["b"], anteontem and anteontem["b"], "anteontem"),
                         compara_txt(a["b"], sem_passada and sem_passada["b"], nome_sem)) if c]
    frases.append(f"{quando}, o dia fechou com <b>{brl(a['b'])}</b> em vendas brutas, com {plural(a['n'], 'reserva')} e "
                  f"{a['px']} pax (ticket médio de {brl(a['b'] / a['n'])})" + (": " + " e ".join(comps) if comps else "") + ".")
    it, on = a["o"].get("INTERNAL"), a["o"].get("ONLINE")
    top = max(a["v"].items(), key=lambda kv: kv[1]["b"]) if a["v"] else None
    dest = f", com destaque para <b>{escape(top[0])}</b> ({brl(top[1]['b'])} em {plural(top[1]['n'], 'reserva')})" if top else ""
    if it and on:
        frases.append(f"O time interno respondeu por <b>{round(it['v'] / a['b'] * 100)}%</b> ({brl(it['v'])}){dest}; "
                      f"o online trouxe {brl(on['v'])} em {plural(on['n'], 'reserva')}.")
    elif it:
        frases.append(f"Todas as vendas vieram do time interno{dest}.")
    elif on:
        frases.append("Todas as vendas vieram do online.")
    ext = ", ".join(f"{v['q']}× {escape(n)}" for n, v in sorted(a["x"].items(), key=lambda kv: -kv[1]["v"]))
    desc = a["b"] - a["l"]
    frases.append((f"Extras somaram <b>{brl(a['e'])}</b> ({ext}). " if a["e"] else "Nenhum extra vendido. ") +
                  f"A receita líquida ficou em <b>{brl(a['l'])}</b>" +
                  (f", depois de {brl(desc)} em cortesias e cupons." if desc > .5 else "."))
    return " ".join(frases)


# ── HTML do e-mail (tabelas e estilos inline, para funcionar no Gmail/Outlook) ─
F = "font-family:'Plus Jakarta Sans',Helvetica,Arial,sans-serif;"
INK, INK2, INK3, LINE, BG = "#000", "#4a4a4a", "#787375", "#e4e4e4", "#f4f4f4"


def label(t):
    return f'<div style="{F}font-size:12px;color:{INK2};font-weight:500;margin-bottom:6px">{t}</div>'


def kpi(titulo, k, destaque=False):
    fundo, cor = ("#000", "#fcfcfc") if destaque else ("#fcfcfc", INK)
    sub = "#fcfcfc" if destaque else INK3
    d1 = delta_html(dia[k], anteontem and anteontem[k], "anteontem", cor=not destaque)
    d2 = delta_html(dia[k], sem_passada and sem_passada[k], nome_sem, cor=not destaque)
    return (f'<td width="33%" valign="top" style="background:{fundo};border:1px solid {fundo if destaque else LINE};'
            f'border-radius:8px;padding:16px">'
            f'<div style="{F}font-size:12px;color:{sub}">{titulo}</div>'
            f'<div style="{F}font-size:{28 if destaque else 22}px;font-weight:700;color:{cor};margin:6px 0">{brl(dia[k])}</div>'
            f'<div style="{F}font-size:11px;color:{sub};line-height:1.5">{d1}<br>{d2}</div></td>')


def card(conteudo):
    return (f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px"><tr>'
            f'<td style="background:#fcfcfc;border:1px solid {LINE};border-radius:8px;padding:16px">{conteudo}</td></tr></table>')


def tabela(cab, linhas, alinhar):
    th = "".join(f'<th align="{al}" style="{F}font-size:11px;color:{INK3};font-weight:500;padding:4px 6px;'
                 f'border-bottom:1px solid {LINE}">{c}</th>' for c, al in zip(cab, alinhar))
    tr = "".join("<tr>" + "".join(f'<td align="{al}" valign="top" style="{F}font-size:13px;color:{INK};padding:6px;'
                                  f'border-bottom:1px solid {LINE}">{c}</td>' for c, al in zip(l, alinhar)) + "</tr>"
                 for l in linhas)
    return f'<table width="100%" cellpadding="0" cellspacing="0">{th and "<tr>" + th + "</tr>"}{tr}</table>'


def vazio(t):
    return f'<div style="{F}font-size:13px;color:{INK3}">{t}</div>'


def periodo_html(titulo, s, ant, nome, extra=""):
    return (f'<td width="50%" valign="top" style="background:#fcfcfc;border:1px solid {LINE};border-radius:8px;padding:16px">'
            f'<div style="{F}font-size:12px;color:{INK2}">{titulo}</div>'
            f'<div style="{F}font-size:22px;font-weight:700;color:{INK};margin:6px 0">{brl(s["b"])}</div>'
            f'<div style="{F}font-size:11px;color:{INK3}">{delta_html(s["b"], ant and ant["b"], nome)}</div>'
            f'<div style="{F}font-size:11px;color:{INK3};margin-top:6px">líquida {brl(s["l"])} · extras {brl(s["e"])} · '
            f'{plural(s["n"], "reserva")} · {s["px"]} pax{extra}</div></td>')


def montar():
    a = dia
    org = " &nbsp;·&nbsp; ".join(
        f'<b>{nome}</b> {brl(a["o"][k]["v"])} <span style="color:{INK3}">({plural(a["o"][k]["n"], "reserva")} · '
        f'{round(a["o"][k]["v"] / a["b"] * 100)}%)</span>'
        for k, nome in (("ONLINE", "Online"), ("INTERNAL", "Interno"), ("MARKETPLACE", "Marketplace")) if k in a["o"])

    vend = sorted(a["v"].items(), key=lambda kv: -kv[1]["b"])
    it = a["o"].get("INTERNAL")
    time_html = label("Time interno") + (
        f'<div style="{F}font-size:12px;color:{INK3};margin-bottom:8px">{brl(it["v"])} com FOC · {brl(it["v"] - it["f"])} sem FOC · '
        f'{plural(it["n"], "reserva")} · {round(it["v"] / a["b"] * 100)}% da receita bruta</div>' if it else "") + (
        tabela(["Vendedor", "Reservas", "Pax", "Com FOC", "Sem FOC", "Produtos"],
               [[f"<b>{escape(n)}</b>", v["n"], v["px"], f"<b>{brl(v['b'])}</b>", brl(v["b"] - v["f"]),
                 " · ".join(f"{q}× {escape(p.replace(' | ', ' '))}" for p, q in sorted(v["p"].items(), key=lambda kv: -kv[1]))]
                for n, v in vend],
               ["left", "right", "right", "right", "right", "left"]) if vend else vazio("Nenhuma venda interna."))

    prods = sorted(a["pr"].items(), key=lambda kv: -kv[1]["q"])
    prod_html = label("Produtos vendidos") + (tabela(
        ["Produto", "Pax", "Reservas", "Valor do voo"],
        [[escape(n), v["q"], v["n"], brl(v["v"])] for n, v in prods], ["left", "right", "right", "right"])
        if prods else vazio("Nenhum produto vendido."))

    exts = sorted(a["x"].items(), key=lambda kv: -kv[1]["q"])
    ext_html = label("Extras mais vendidos") + (tabela(
        ["Extra", "Unidades", "Valor"], [[escape(n), v["q"], brl(v["v"])] for n, v in exts], ["left", "right", "right"])
        if exts else vazio("Nenhum extra vendido."))

    cups = sorted(a["c"].items(), key=lambda kv: -kv[1]["n"])
    cup_html = card(label("Cupons de desconto") + tabela(
        ["Cupom", "Usos", "Reservas", "Desconto"],
        [[f"<b>{escape(n)}</b>", v["n"], brl(v["b"]), f'<span style="color:#c62f2f">−{brl(v["d"])}</span>'] for n, v in cups],
        ["left", "right", "right", "right"])) if cups else ""

    ciclo_extra = f" · dia {dia_ciclo} de {dias_ciclo}"
    corpo = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="background:{BG}"><tr><td align="center" style="padding:24px 12px">
<table width="680" cellpadding="0" cellspacing="0" style="max-width:680px;width:100%">
  <tr><td style="background:#000;border-radius:8px;padding:18px 20px">
    <span style="{F}font-size:18px;font-weight:700;letter-spacing:.12em;color:#fcfcfc">VERTICAL RIO</span>
    <span style="{F}font-size:12px;letter-spacing:.08em;color:#c4c4c4;text-transform:uppercase">&nbsp;&nbsp;|&nbsp;&nbsp;Vendas de {DSEM[D.weekday()]}, {f_curto(D)}</span>
  </td></tr>
  <tr><td style="padding-top:12px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      {kpi("Receita bruta", "b", True)}<td width="8"></td>{kpi("Receita líquida", "l")}<td width="8"></td>{kpi("Extras", "e")}
    </tr></table>
  </td></tr>
  <tr><td>{card(label("Resumo do dia") + f'<div style="{F}font-size:14px;color:{INK2};line-height:1.6">{resumo_executivo()}</div>')}</td></tr>
  <tr><td>{card(label("Origem das vendas") + f'<div style="{F}font-size:13px;color:{INK}">{org or "Sem vendas."}</div>')}</td></tr>
  <tr><td style="padding-top:12px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      {periodo_html(f"Semana · seg {f_curto(seg)} → {f_curto(D)}", semana, semana_ant, "semana anterior")}<td width="8"></td>
      {periodo_html(f"Ciclo · {f_curto(cs)} → {f_curto(fim_ciclo(cs))}", ciclo, ciclo_ant, "ciclo anterior", ciclo_extra)}
    </tr></table>
  </td></tr>
  <tr><td>{card(time_html)}</td></tr>
  <tr><td>{cup_html}</td></tr>
  <tr><td>{card(prod_html)}</td></tr>
  <tr><td>{card(ext_html)}</td></tr>
  <tr><td align="center" style="padding:20px 0 8px">
    <a href="{PAINEL}" style="{F}display:inline-block;background:#000;color:#fcfcfc;text-decoration:none;font-size:14px;font-weight:600;padding:12px 22px;border-radius:8px">Abrir o painel Vendas do Dia</a>
  </td></tr>
  <tr><td style="{F}font-size:11px;color:{INK3};line-height:1.5;padding:8px 4px">
    Reservas confirmadas, pela data em que foram feitas (Rezdy). Bruta = valor total da reserva · Líquida = bruta − cortesias (FOC) − cupons ·
    Comparações: ontem contra anteontem e contra o mesmo dia da semana passada; semana e ciclo contra o mesmo ponto do período anterior.
    Ciclo = dia 26 a 25. Dados de {dados["atualizado"][8:10]}/{dados["atualizado"][5:7]} às {dados["atualizado"][11:]}.
  </td></tr>
</table></td></tr></table>"""
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head><body style="margin:0;background:{BG}">{corpo}</body></html>'


def texto_simples():
    a = dia
    linhas = [f"Vendas de {DSEM[D.weekday()]}, {f_curto(D)} · Vertical Rio", "",
              f"Receita bruta: {brl(a['b'])} · líquida: {brl(a['l'])} · extras: {brl(a['e'])}",
              f"{plural(a['n'], 'reserva')} · {a['px']} pax", "",
              re.sub(r"<[^>]+>", "", resumo_executivo()), "",
              f"Semana: {brl(semana['b'])} · Ciclo: {brl(ciclo['b'])} (dia {dia_ciclo} de {dias_ciclo})", "",
              f"Painel: {PAINEL}"]
    return "\n".join(linhas)


html = montar()
assunto = f"Vendas de ontem ({DSEM[D.weekday()]}, {f_curto(D)}): {brl(dia['b'])} · {plural(dia['n'], 'reserva')}"

if "--preview" in sys.argv:
    saida = sys.argv[sys.argv.index("--preview") + 1]
    with open(saida, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"prévia gravada em {saida} · assunto: {assunto}")
    sys.exit(0)

# a senha de app do Google aparece em blocos com espaços; ignora espaços e quebras de linha coladas junto
USER = (os.environ.get("SMTP_USER") or "").strip()
SENHA = re.sub(r"\s", "", os.environ.get("SMTP_PASS") or "")
PARA = [e.strip() for e in (os.environ.get("EMAIL_PARA") or "").split(",") if e.strip()]
if not (USER and SENHA and PARA):
    sys.exit("defina SMTP_USER, SMTP_PASS e EMAIL_PARA")

msg = EmailMessage()
msg["Subject"] = assunto
msg["From"] = f"Vendas do Dia · Vertical Rio <{USER}>"
msg["To"] = ", ".join(PARA)
msg.set_content(texto_simples())
msg.add_alternative(html, subtype="html")
# diagnóstico sem expor a senha (os logs do Actions são públicos): só tamanho e tipo de caractere
print(f"remetente {USER} · senha com {len(SENHA)} caracteres · só letras: {SENHA.isalpha()} · ascii: {SENHA.isascii()}")


def enviar(s):
    s.ehlo()
    print("métodos de login do servidor:", s.esmtp_features.get("auth", "?"))
    try:
        s.login(USER, SENHA)
    except smtplib.SMTPAuthenticationError as e:
        sys.exit(f"login recusado pelo Gmail ({e.smtp_code}): confira a senha de app de {USER}")
    s.send_message(msg)


HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
try:
    with smtplib.SMTP_SSL(HOST, 465, timeout=30) as s:
        enviar(s)
except smtplib.SMTPServerDisconnected as e:
    print(f"porta 465 caiu ({e}); tentando 587 com STARTTLS")
    with smtplib.SMTP(HOST, 587, timeout=30) as s:
        s.ehlo()
        s.starttls()
        enviar(s)
print(f"enviado para {len(PARA)} destinatário(s) · {assunto}")
