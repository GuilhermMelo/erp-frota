/**
 * Casca do app GM Locações.
 *
 * O que este processo faz, na ordem:
 *   1. garante que o Postgres (container Docker) está de pé;
 *   2. sobe o backend empacotado (erp-frota-api.exe) em segundo plano;
 *   3. espera o /health responder;
 *   4. abre a janela com a interface, que a própria API serve.
 *
 * Ao fechar a janela, o backend morre junto. O Postgres fica de pé — é um container com
 * `restart: unless-stopped`, sobe com o Windows e não é nosso para desligar.
 */

const { app, BrowserWindow, dialog, shell, Menu } = require('electron')
const { spawn, execFile } = require('child_process')
const net = require('net')
const http = require('http')
const path = require('path')

const API_PORT = 8010
const DB_PORT = 5434
const DB_CONTAINER = 'erp-frota-db'
const API_URL = `http://127.0.0.1:${API_PORT}`

let backend = null
let win = null

// Duas cópias abertas brigariam pela porta 8010 e a segunda morreria sem explicar por quê.
if (!app.requestSingleInstanceLock()) app.quit()
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

async function garantirPostgres() {
  if (await portaAberta(DB_PORT)) return

  status('Iniciando o banco de dados…')

  // O container quase sempre já existe e só está parado (o Docker Desktop acabou de subir).
  // `docker start` é o caminho rápido e — importante — não recria volume nenhum.
  const start = await rodar('docker', ['start', DB_CONTAINER])

  if (!start.ok) {
    // Container não existe (primeira execução numa máquina nova). Cria pelo compose.
    // O nome do projeto vai FIXO: se o Docker derivasse do nome da pasta, uma pasta
    // diferente criaria um volume novo — e o banco apareceria vazio, com os dados
    // "sumidos" no volume antigo.
    const compose = app.isPackaged
      ? path.join(process.resourcesPath, 'docker-compose.yml')
      : path.join(__dirname, '..', 'docker-compose.yml')

    const up = await rodar('docker', ['compose', '-p', 'erp-frota-v1', '-f', compose, 'up', '-d'], 180000)
    if (!up.ok) {
      throw new Error(
        'Não consegui iniciar o banco de dados.\n\n' +
          'O Docker Desktop precisa estar rodando. Abra o Docker Desktop, espere ele ' +
          'terminar de iniciar (o ícone da baleia para de animar) e abra o ERP de novo.\n\n' +
          `Detalhe técnico: ${up.saida || 'comando `docker` não encontrado'}`,
      )
    }
  }

  const subiu = await esperar(() => portaAberta(DB_PORT), { tentativas: 60 })
  if (!subiu) throw new Error('O banco de dados não respondeu a tempo (60s).')
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

  backend = spawn(caminhoBackend(), [], {
    env: { ...process.env, ERP_PORT: String(API_PORT) },
    windowsHide: true,
    stdio: 'ignore', // o backend escreve o próprio log em %LOCALAPPDATA%\ERP Frota\logs
  })
  backend.on('error', (e) => console.error('backend não subiu:', e))

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
  criarJanela()
  try {
    await garantirPostgres()
    await subirBackend()
    await win.loadURL(API_URL)
  } catch (erro) {
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

app.on('window-all-closed', () => app.quit())
app.on('before-quit', matarBackend)
process.on('exit', matarBackend)
