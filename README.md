# Vendas do Dia · Vertical Rio

Resumo diário das vendas do Rezdy: receita bruta, líquida e extras do dia, origem (online × interno),
semana e ciclo (26→25) comparados com o período anterior até o mesmo horário, e extras mais vendidos.

- `scripts/sync.py` busca as reservas confirmadas dos últimos 75 dias (pela data de criação) e grava
  `dados.js` **criptografado** (AES-256-GCM, chave PBKDF2-SHA256 da senha). Sem nomes, e-mails ou números de pedido.
- `index.html` pede a senha e descriptografa no navegador.
- GitHub Action `sync.yml` roda a cada 15 min, das 07h às 23h. Secrets: `REZDY_API_KEY`, `SENHA_PAINEL`.

Regras: Bruta = valor total da reserva · Líquida = bruta − cortesias (FOC) − cupons ·
Origem = campo `source` do Rezdy (INTERNAL = interno; MARKETPLACE_* = marketplace; o resto = online).
