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

O iPad usa o sistema web normalmente. Os pedidos são salvos no servidor e entram na fila persistente de impressão; uma ponte ESP32, conectada ao Wi-Fi do estabelecimento, consulta a fila e envia a comanda à impressora por Bluetooth. O navegador não precisa acessar Bluetooth e não depende de AirPrint.
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


## Impressão por ponte ESP32

O navegador não conversa mais diretamente com a impressora. Ao salvar um pedido, o servidor grava o pedido e um trabalho em `print_jobs` na mesma transação. A ponte ESP32 consulta a fila pela internet, reserva um trabalho por 90 segundos e informa o resultado. Trabalhos com falha são tentados novamente até cinco vezes; reservas abandonadas expiram e podem ser recuperadas. A reimpressão cria um novo trabalho sem duplicar o pedido nem alterar o estoque.

### Configuração do servidor (Railway)

Defina `PRINT_AGENT_TOKEN` com um segredo aleatório longo, igual ao configurado no firmware. Gere um valor com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Não publique esse valor no Git. A persistência da fila depende de o banco SQLite e seu volume estarem persistentes no Railway.

### Firmware e compatibilidade

O firmware da ponte ficará em `firmware/esp32-print-bridge`. A comunicação inicial será por BLE GATT, procurando uma característica gravável. O relatório `BT, USB PRINT` não confirma por si só o perfil Bluetooth, UUIDs, característica gravável ou protocolo de impressão da LT-8359. Portanto, a ponte ainda exige validação física antes de considerar a impressão pronta.

A fila usa entrega com repetição (at-least-once). Se a ponte perder a conexão depois de a impressora receber os bytes, mas antes de confirmar o resultado, uma nova tentativa poderá imprimir a mesma comanda novamente. O servidor só marca o pedido como impresso após receber a confirmação da ponte.
