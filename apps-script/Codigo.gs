// Google Apps Script da conta automacao.verticalrio@gmail.com
// Envia todo dia, às 8h, o resumo de vendas de ontem gerado pelo GitHub (painel Vendas do Dia).
// Instalação: cole este código em script.google.com, escolha a função "instalar" e clique em Executar.

const PARA = 'performance@verticalrio.com';   // vários: 'a@x.com,b@y.com'
const BASE = 'https://performance-sketch.github.io/VENDAS-DIA/email/';

function enviarResumo() {
  const info = JSON.parse(UrlFetchApp.fetch(BASE + 'ontem.json?t=' + Date.now()).getContentText());
  const ontem = Utilities.formatDate(new Date(Date.now() - 864e5), 'America/Sao_Paulo', 'yyyy-MM-dd');
  if (info.dia !== ontem) throw new Error('Resumo ainda não atualizado (está com ' + info.dia + ', esperado ' + ontem + ')');
  const html = UrlFetchApp.fetch(BASE + 'ontem.html?t=' + Date.now()).getContentText();
  MailApp.sendEmail({ to: PARA, subject: info.assunto, htmlBody: html, body: info.texto, name: 'Vendas do Dia · Vertical Rio' });
}

// Rode uma vez: cria o agendamento diário (8h, horário do Rio) e já envia um e-mail de teste.
function instalar() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('enviarResumo').timeBased().everyDays(1).atHour(8).inTimezone('America/Sao_Paulo').create();
  enviarResumo();
}
