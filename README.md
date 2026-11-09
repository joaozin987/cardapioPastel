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

Para testar Web Bluetooth em outro aparelho, o site precisa de HTTPS ou ser
aberto em `localhost`. A rede local por HTTP permite testar o login, o catálogo
e os pedidos compartilhados, mas não habilita Web Bluetooth no Android. O
Com a sessão aberta, o botão **Atualizar dados (sem desconectar)** e os atalhos
`F5`/`Ctrl+R` atualizam os dados sem recarregar a página, mantendo a conexão
Bluetooth. O carrinho também é salvo por estação e restaurado após uma recarga
completa. O botão de atualizar do navegador ainda recarrega a página; o
navegador encerra a conexão e mostra um aviso antes de continuar. Depois da
recarga, o Chrome tenta reconectar à impressora previamente autorizada e
vinculada à estação. Se não conseguir, use **Conectar impressora**. Atualizar
durante o envio de uma nota pode interromper a impressão. O Safari do iPad não
oferece Web Bluetooth; a impressão Bluetooth nele ainda
precisa de uma integração compatível com a impressora. Portanto, valide essa
impressora separadamente antes de considerar a impressão do iPad pronta.

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
