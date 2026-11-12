# D&A Lanche's - Pedidos

Aplicação web local servida pelo Flask. A interface atual está em
`da-lanches-pedidos.html`.

O SQLite fica em `instance/da_lanches.db`. Ao iniciar o Flask, `database.py`
cria as tabelas e cadastra o cardápio inicial somente se ainda não houver
produtos. Pedidos, itens, estoque e alterações de produtos são lidos e gravados
pelos endpoints da API.

Fotos de produtos são salvas como arquivos JPG quadrados, redimensionados para
até 600 × 600 px e 200 KB; o SQLite guarda somente o caminho. A tela de edição
aceita JPG, PNG e WEBP de até 5 MB. As imagens ficam em
`instance/product_images/` e produtos sem foto continuam usando os ícones.
Na lista de produtos, itens adicionados ou editados são movidos para o final;
os cartões usam imagens de 100 px no pedido e miniaturas de 80 px em Produtos.

Os produtos adicionados a pedido do cliente ficam com preço pendente e não
podem ser vendidos até que um preço seja informado em **Produtos > Editar**.
As três pizzas brotinho foram atualizadas para R$ 10,00.

## Iniciar no Windows (PowerShell)

Na primeira execução, crie o arquivo local de configuração se ele ainda não
existir e substitua os valores de exemplo por segredos exclusivos. O arquivo
`.env` não deve ser compartilhado nem enviado ao Git. Neste workspace, as
credenciais locais já foram geradas; consulte `.env` para entrar:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
py -c "import secrets; print(secrets.token_urlsafe(32))"
notepad .env
```

Numa instalação nova, use uma saída aleatória para `FLASK_SECRET_KEY` e defina
um PIN administrativo e um PIN para o funcionário. Em seguida, instale e inicie:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Abra <http://127.0.0.1:5000> no navegador. Com `HOST=0.0.0.0`, outros aparelhos
na mesma rede podem abrir `http://IP-DO-COMPUTADOR:5000`; descubra o IP com
`ipconfig`. Use essa opção somente em uma rede confiável. Para parar o servidor,
pressione `Ctrl+C` no terminal.

Existem somente dois perfis: **Funcionário** (PIN em `STATION_1_PIN`) e
**Administrador** (senha em `ADMIN_PASSWORD`). O funcionário usa a impressora
da estação 1; o administrador usa a impressora da estação 2. Ambos podem criar
pedidos, consultar o histórico e imprimir na própria estação. Só o
administrador pode editar produtos e fotos. O sistema registra a origem do
pedido e impede que o outro perfil o imprima na impressora errada.
`ADMIN_PASSWORD` tem prioridade sobre `STATION_2_PIN` e `ADMIN_PIN`. Para o
funcionário, `STATION_1_PIN` tem prioridade sobre `EMPLOYEE_PIN`.
Após cinco tentativas erradas para uma conta no mesmo endereço, o login fica
bloqueado por cinco minutos.

O fluxo principal usa o Simple Bluetooth Printer no iPhone: selecionar produtos e
clicar em **Imprimir pedido** salva o pedido e solicita impressão automática no
aplicativo, mantendo o catálogo aberto. Não usa fila nem ESP32.
Em hospedagem HTTPS, defina `SESSION_COOKIE_SECURE=true`, `FLASK_DEBUG=false`,
uma `FLASK_SECRET_KEY` persistente e credenciais fortes; não use o servidor
Flask de desenvolvimento em produção.

Se o comando `py` não estiver disponível, use `python` no lugar dele para criar
o ambiente virtual.

## Iniciar no Git Bash

No Git Bash, use barras `/` nos caminhos. Se o prompt já mostrar `(.venv)`,
execute:

```bash
python -m pip install -r requirements.txt
python app.py
```

Se ainda não tiver criado ou ativado o ambiente virtual:

```bash
py -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python app.py
```

## Testar conexão Bluetooth no Windows (sem imprimir)

O agente local é uma etapa isolada para identificar e testar conexões com impressoras. Ele não altera o fluxo de pedidos, não se conecta ao Railway e não envia dados para a impressora.

Instale as dependências e inicie o agente no PowerShell:

```powershell
py -m pip install -r requirements-print-agent.txt
py windows_print_agent.py
```

Abra http://127.0.0.1:8765 no computador Windows. A página lista portas COM disponíveis (possíveis conexões Bluetooth clássico/SPP) e permite procurar dispositivos BLE. Selecione uma porta ou dispositivo para testar a conexão. Mantenha o terminal do agente aberto.

O serviço escuta somente em 127.0.0.1 e não deve ser exposto à rede ou à internet. Para Bluetooth clássico, o Windows precisa ter pareado a impressora e criado uma porta COM. BLE e SPP são transportes diferentes; a identificação do modelo e do protocolo de impressão ainda será necessária. A taxa serial inicial é 9600 baud e poderá precisar ser ajustada após confirmar o modelo/manual. Encerrar o processo do agente fecha a conexão.

Esta etapa não imprime e não envia comandos para a impressora. Uma conexão estabelecida não confirma compatibilidade com ESC/POS ou outro protocolo.

## Estrutura


```text
catalog-pastel/
├── app.py
├── database.py
├── da-lanches-pedidos.html
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── instance/
│   ├── da_lanches.db
│   └── product_images/
└── tests/
    ├── test_app.py
    └── test_database.py
```

Execute os testes de banco/API com `python -m unittest discover -s tests`.
Eles usam um banco temporário e não alteram `instance/da_lanches.db`.
Execute os testes dos adaptadores com `node --test tests/test_*.js` (Node 20+).

## Impressão direta no iPhone

O usuário confirmou impressão física no teste oficial:
<https://bluetoothprinter.in/print-test/>. Configure uma vez no aplicativo
Simple Bluetooth Printer a impressora da estação, papel de 58 mm e permissões.
Esse teste não comprova instalação do aplicativo no iPad 2.

No D&A, selecione os produtos e toque em **Imprimir pedido**. O servidor salva o
pedido e desconta estoque uma única vez; a página solicita a impressão por
`thermalprint://print?text=` com `encodeURIComponent()` e `autoprint=true`.
O aplicativo recebe a solicitação para imprimir automaticamente. Não é preciso
abrir o histórico, preparar outro botão ou revisar o texto antes de cada pedido.

Em **Configurar impressora**, ficam Simple Bluetooth Printer, Web Bluetooth e
**iPad via Android (Print Bridge)**.
A escolha é guardada neste navegador por estação, não precisa ser repetida a cada
pedido. Web Bluetooth exige navegador e hardware BLE compatíveis; Safari/iPad 2
não fornecem essa combinação. A opção AirPrint foi removida.

Se o aplicativo estiver ausente ou o iOS bloquear a abertura após uma resposta
lenta do servidor, o pedido continua salvo. O mesmo botão passa a permitir
reimprimir o último pedido sem cadastrá-lo nem descontar estoque novamente.
Não há reenvio automático: toques repetidos rápidos na mesma comanda são
ignorados. O iOS pode mostrar sua própria confirmação para abrir o aplicativo.

A abertura do aplicativo e a volta ao navegador não confirmam saída de papel.
O sistema não marca automaticamente `impresso`. A reimpressão do histórico
revalida sessão, CSRF, estação e cancelamento e abre a impressão diretamente.

Os adaptadores ES5 ficam em `static/`; Babel e polyfills existentes foram
preservados. O formatador `ticketText()` foi recuperado do histórico, com 32
colunas, quantidades e nomes dos itens, sem preços/total. Os caracteres de
controle legados são removidos antes de codificar o texto do aplicativo.
Teste acentos, nomes longos e a maior comanda real no iPhone.

## Fila antiga desativada

Pedidos novos não geram trabalhos em `print_jobs`. As rotas antigas de agente
ESP32 e enfileiramento retornam HTTP 410 e não processam trabalhos anteriores.
Os registros históricos são preservados. Clientes antigos que enviam destino
`padrao` também passam a salvar para impressão direta no aplicativo.

## Atualização do banco e reversão

O destino fica registrado em `pedidos.impressao_destino`, com padrão
`simple_bluetooth`. Na primeira inicialização sobre um banco anterior, a
migração aditiva cria uma cópia consistente pelo SQLite antes de adicionar o
campo. O backup fica ao lado do banco, no padrão
`da_lanches.before-impressao-destino-*.db`, com acesso restrito. Bancos novos e
reinicializações após a migração não repetem a cópia. O volume precisa continuar
persistente no Railway.

Uma reversão deve preservar o campo e não reativar a fila antiga. Restaurar um
backup de banco perde os pedidos criados depois daquela cópia; faça isso somente
com o serviço parado e após validar os dados que precisam ser preservados.

## Teste real: iPad via Android

O iPad envia pela internet ao Print Bridge; o aplicativo Android recebe e imprime
pela conexão Bluetooth. O Android e o servidor precisam ter internet. Nenhum
aplicativo é necessário no iPad, e os aparelhos não precisam estar na mesma rede.

1. No Android, use **Bluetooth-USB Thermal Printer+**, da **Techpuram**:
   <https://play.google.com/store/apps/details?id=com.iyaltamizh.app.btprinter>.
   O guia detalha a recepção remota nesse aplicativo. Conecte a térmica e confirme
   uma impressão pelo app; a função **Print From Web** do Simple Bluetooth Printer
   não comprova a presença do menu que gera o código remoto na versão instalada.
2. Abra **Developer Space → Print From Anywhere / Quick Print** (Print Bridge).
   Mantenha essa tela aberta e anote o código temporário de 12 dígitos.
3. No iPad, abra o D&A, entre na estação e escolha **Configurar impressora →
   iPad via Android**. Digite o código no campo destacado.
   **Enviar código** confere os 12 dígitos somente na página, sem imprimir nem
   consultar o Android; a comunicação continua ocorrendo ao imprimir o pedido.
4. Selecione os itens e toque em **Imprimir pedido**. A página permanece no
   catálogo. Não é necessário tocar em abrir aplicativo no iPad.

O código fica apenas na memória desta página e é apagado ao sair/recarregar;
não envie o código em mensagens nem o compartilhe publicamente. Se a tela no
Android fechar, o código pode expirar. O plano gratuito permite **10 impressões
totais por aparelho**, compartilhadas com Order Print; não é uma cota diária.
Este primeiro modo é para validar o conjunto real, não para operação contínua
em segundo plano. O modo persistente Order Print exige conta, pareamento e chave
de API no servidor e não foi incluído neste teste.

O adaptador ES5 `static/print-bridge.js` reutiliza `ticketText()` e o transporte
do aplicativo; os pedidos continuam registrados como `simple_bluetooth`, sem
migração de banco. A configuração atual decide entre abrir o app local ou enviar
ao Android, inclusive ao reimprimir pedidos desse destino. Web Bluetooth mantém
seu próprio destino. Falha no envio preserva o pedido e o estoque já descontado.

O endpoint autenticado/CSRF `/api/pedidos/<id>/impressao/android` valida estação,
cancelamento, código e texto (máximo 4.000 caracteres). O servidor usa o contrato
Firebase documentado pelo fabricante, com host fixo, sessão existente, impressora
determinada e PUT condicional por ETag. Uma impressão pendente não é sobrescrita.
Não há fila local, novo cadastro, reenvio automático ou alteração de `impresso`.
HTTP 202 significa **enviado ao serviço**, não confirmação de saída de papel.
Se houver timeout, confira o Android e a impressora antes de repetir.

Fontes e contrato utilizado:
<https://printbridge.bluetoothprinter.in/06-print-from-anywhere.html>,
<https://printbridge.bluetoothprinter.in/js/quick-print.js> e
<https://firebase.google.com/docs/database/rest/save-data#section-conditional-requests>.
