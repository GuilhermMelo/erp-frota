/**
 * Casca do app GM Locações.
 *
 * O que este processo faz, na ordem:
 *   1. garante que o Postgres EMBUTIDO está de pé (sem Docker, sem instalação);
 *   2. sobe o backend empacotado (erp-frota-api.exe) em segundo plano;
 *   3. espera o /health responder;
 *   4. abre a janela com a interface, que a própria API serve.
 *
 * Ao fechar a janela, o backend morre junto e o Postgres é desligado — os dois são nossos.
 * O banco vive num Postgres portátil que empacotamos com o app; o usuário nunca instala
 * nada e nunca vê um terminal.
 */

const { app, BrowserWindow, dialog, shell, Menu } = require('electron')
const { spawn, execFile, execFileSync } = require('child_process')
const net = require('net')
const http = require('http')
const path = require('path')
const fs = require('fs')

const API_PORT = 8010
const DB_PORT = 5434
const DB_USER = 'frota'
const DB_NAME = 'frota'
const API_URL = `http://127.0.0.1:${API_PORT}`

let backend = null
let win = null

// Log de diagnóstico da CASCA (não do backend): registra cada passo do boot num arquivo.
// Um app de desktop sem console não tem outro lugar para explicar por que não abriu.
function logShell(msg) {
  try {
    const base = process.env.LOCALAPPDATA || app.getPath('appData')
    const dir = path.join(base, 'GM Locacoes', 'logs')
    fs.mkdirSync(dir, { recursive: true })
    fs.appendFileSync(path.join(dir, 'shell.log'), `[${new Date().toISOString()}] ${msg}\n`)
  } catch (_) {
    /* nada a fazer se nem o log grava */
  }
}
process.on('uncaughtException', (e) => logShell(`uncaughtException: ${(e && e.stack) || e}`))

logShell(`MODULE LOADED pid=${process.pid} isPackaged=${app.isPackaged} resourcesPath=${process.resourcesPath}`)

// Duas cópias abertas brigariam pela porta 8010 e a segunda morreria sem explicar por quê.
const temLock = app.requestSingleInstanceLock()
logShell(`requestSingleInstanceLock=${temLock}`)
if (!temLock) {
  logShell('outra instância detém o lock — encerrando esta cópia')
  app.quit()
}
app.on('second-instance', () => {
  if (win) {
    if (win.isMinimized()) win.restore()
    win.focus()
  }
})

/* ------------------------------------------------------------------ utilidades */

function portaAberta(port, timeout = 1000) {
  return new Promise((resolve) => {
    const socket = new net.Socket()
    const fim = (ok) => {
      socket.destroy()
      resolve(ok)
    }
    socket.setTimeout(timeout)
    socket.once('connect', () => fim(true))
    socket.once('timeout', () => fim(false))
    socket.once('error', () => fim(false))
    socket.connect(port, '127.0.0.1')
  })
}

function rodar(cmd, args, timeout = 60000) {
  return new Promise((resolve) => {
    execFile(cmd, args, { timeout, windowsHide: true }, (erro, stdout, stderr) =>
      resolve({ ok: !erro, saida: `${stdout || ''}${stderr || ''}`.trim() }),
    )
  })
}

async function esperar(condicao, { tentativas, intervalo = 1000, aoTentar }) {
  for (let i = 1; i <= tentativas; i++) {
    if (await condicao()) return true
    if (aoTentar) aoTentar(i)
    await new Promise((r) => setTimeout(r, intervalo))
  }
  return false
}

/**
 * Atualiza o texto da tela de carregamento.
 *
 * Via executeJavaScript, e não IPC: mandar `webContents.send` exigiria um preload script
 * expondo ipcRenderer, e um canal de IPC aberto só para escrever uma frase na tela não
 * paga o buraco que abre na isolação do contexto.
 */
function status(texto) {
  if (!win || win.isDestroyed()) return
  const js = `(() => { const e = document.getElementById('status'); if (e) e.textContent = ${JSON.stringify(texto)} })()`
  win.webContents.executeJavaScript(js).catch(() => {
    /* a página ainda não carregou — o próximo status pega */
  })
}

/* ------------------------------------------------------------------ 1. banco */

// Onde ficam os binários do Postgres portátil. No app instalado vêm em resources\pgsql;
// em desenvolvimento, na pasta vendor\ (baixada uma vez, fora do git).
function pgRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'pgsql')
    : path.join(__dirname, 'vendor', 'pgsql')
}
function pgBin(exe) {
  return path.join(pgRoot(), 'bin', `${exe}.exe`)
}

// O cluster de dados fica junto do resto dos dados do usuário, em %LOCALAPPDATA%\GM Locacoes.
// É a MESMA raiz que o backend usa para fotos e contratos, e sobrevive a reinstalações do app
// (o instalador troca o programa, nunca os dados).
function pgData() {
  const base = process.env.LOCALAPPDATA || app.getPath('appData')
  return path.join(base, 'GM Locacoes', 'pgdata')
}

async function garantirPostgres() {
  logShell(`garantirPostgres: pgRoot=${pgRoot()} isPackaged=${app.isPackaged}`)
  // Porta já aberta = servidor já de pé (segunda instância, ou não desligou na última vez).
  if (await portaAberta(DB_PORT)) {
    logShell('garantirPostgres: porta 5434 já aberta — reaproveitando servidor existente')
    return
  }

  const data = pgData()
  const primeiraVez = !fs.existsSync(path.join(data, 'PG_VERSION'))
  logShell(`garantirPostgres: data=${data} primeiraVez=${primeiraVez}`)

  if (primeiraVez) {
    status('Preparando o banco na primeira execução…')
    fs.mkdirSync(path.dirname(data), { recursive: true })
    // -A trust: o servidor só escuta em localhost, então toda conexão vem do próprio backend
    // desta máquina. Sem senha para não guardar credencial em texto dentro do app.
    // --locale=C e UTF8: previsível, sem depender do locale do Windows do usuário.
    const init = await rodar(
      pgBin('initdb'),
      ['-D', data, '-U', DB_USER, '-A', 'trust', '-E', 'UTF8', '--locale=C'],
      120000,
    )
    logShell(`initdb ok=${init.ok} saida=${init.saida.slice(-300)}`)
    if (!init.ok) {
      throw new Error(`Não consegui preparar o banco de dados (initdb).\n\nDetalhe técnico: ${init.saida}`)
    }
  }

  status('Iniciando o banco de dados…')
  const log = path.join(data, 'postgres.log')
  // pg_ctl com -w espera o servidor aceitar conexões antes de retornar. listen_addresses
  // fixo em localhost fecha o banco para a rede — é um banco de uma máquina só.
  const start = await rodar(
    pgBin('pg_ctl'),
    ['-D', data, '-l', log, '-o', `-p ${DB_PORT} -c listen_addresses=localhost`, '-w', '-t', '60', 'start'],
    90000,
  )
  logShell(`pg_ctl start ok=${start.ok} saida=${start.saida.slice(-300)}`)
  if (!start.ok && !(await portaAberta(DB_PORT))) {
    throw new Error(`O banco de dados não iniciou.\n\nDetalhe técnico: ${start.saida}\n\nLog: ${log}`)
  }

  const subiu = await esperar(() => portaAberta(DB_PORT), { tentativas: 60 })
  if (!subiu) throw new Error('O banco de dados não respondeu a tempo (60s).')

  // O banco lógico 'frota' não é criado pelo initdb. Tentamos criar sempre e ignoramos o
  // erro de "já existe": é a forma idempotente de garantir que ele exista sem checagem extra.
  await rodar(pgBin('createdb'), ['-h', '127.0.0.1', '-p', String(DB_PORT), '-U', DB_USER, DB_NAME], 30000)
}

// Desliga o Postgres embutido. Síncrono e no fechamento: se o processo do Electron morresse
// antes, o próximo boot faria recovery (mais lento) ou acharia a porta presa.
function pararPostgres() {
  try {
    execFileSync(pgBin('pg_ctl'), ['-D', pgData(), '-m', 'fast', 'stop'], {
      windowsHide: true,
      timeout: 15000,
    })
  } catch (_) {
    /* já parado, ou nunca chegou a subir */
  }
}

/* ------------------------------------------------------------------ 2. backend */

function caminhoBackend() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'backend', 'erp-frota-api.exe')
    : path.join(__dirname, '..', 'backend', 'dist', 'erp-frota-api', 'erp-frota-api.exe')
}

function saudavel() {
  return new Promise((resolve) => {
    const req = http.get(`${API_URL}/health`, { timeout: 2000 }, (res) => {
      let corpo = ''
      res.on('data', (c) => (corpo += c))
      res.on('end', () => resolve(res.statusCode === 200 && corpo.includes('"ok"')))
    })
    req.on('error', () => resolve(false))
    req.on('timeout', () => {
      req.destroy()
      resolve(false)
    })
  })
}

async function subirBackend() {
  status('Iniciando o sistema…')
  logShell(`subirBackend: exe=${caminhoBackend()} existe=${fs.existsSync(caminhoBackend())}`)

  backend = spawn(caminhoBackend(), [], {
    env: { ...process.env, ERP_PORT: String(API_PORT) },
    windowsHide: true,
    stdio: 'ignore', // o backend escreve o próprio log em %LOCALAPPDATA%\GM Locacoes\logs
  })
  backend.on('error', (e) => logShell(`backend não subiu: ${e && e.message}`))

  // A primeira execução roda as migrações antes de servir — pode demorar. 60s é folga.
  const ok = await esperar(saudavel, {
    tentativas: 60,
    aoTentar: (i) => i === 8 && status('Preparando o banco na primeira execução…'),
  })

  if (!ok) {
    throw new Error(
      'O sistema não respondeu a tempo.\n\n' +
        'O log está em:\n%LOCALAPPDATA%\\GM Locacoes\\logs\\backend.log',
    )
  }
}

/* ------------------------------------------------------------------ 3. janela */

function criarJanela() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: true,
    backgroundColor: '#f8fafc',
    title: 'GM Locações',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  })

  Menu.setApplicationMenu(null) // sem menu "File / Edit / View" de navegador
  win.loadFile(path.join(__dirname, 'loading.html'))

  // Link externo abre no navegador, não sequestra a janela do app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
}

function mostrarErro(erro) {
  dialog.showMessageBoxSync({
    type: 'error',
    title: 'GM Locações',
    message: 'Não foi possível iniciar o sistema.',
    detail: String(erro.message || erro),
    buttons: ['Fechar'],
  })
}

/* ------------------------------------------------------------------ ciclo de vida */

app.whenReady().then(async () => {
  logShell('app pronto — iniciando boot')
  criarJanela()
  try {
    await garantirPostgres()
    await subirBackend()
    await win.loadURL(API_URL)
    logShell('boot concluído — janela carregada')
  } catch (erro) {
    logShell(`ERRO no boot: ${(erro && erro.stack) || erro}`)
    mostrarErro(erro)
    app.quit()
  }
})

function matarBackend() {
  if (!backend || backend.killed) return
  // taskkill /T mata a árvore: o uvicorn deixa processo filho, e um órfão segurando a
  // porta 8010 faria a PRÓXIMA abertura do app falhar sem explicação.
  spawn('taskkill', ['/pid', String(backend.pid), '/T', '/F'], { windowsHide: true })
  backend = null
}

// Ordem importa: primeiro o backend (solta as conexões com o banco), depois o Postgres.
function encerrar() {
  matarBackend()
  pararPostgres()
}

app.on('window-all-closed', () => app.quit())
app.on('before-quit', encerrar)
process.on('exit', encerrar)
