# Ponte de impressão ESP32

Firmware inicial para ESP32 clássico (ex.: ESP32-WROOM-32 / DevKit V1), com Wi-Fi e cliente BLE GATT.

## Configuração

1. Instale o PlatformIO no VS Code.
2. Copie `secrets.example.h` para `secrets.h`.
3. Preencha Wi-Fi, `PRINT_AGENT_TOKEN` e a estação. A estação deve ser igual à sessão usada no iPad: `station-1` para Funcionário ou `station-2` para Administrador.
4. Abra esta pasta no PlatformIO, compile e grave o firmware.
5. Abra o monitor serial a 115200 baud.

## Atenção: estado de protótipo

- O firmware procura o nome BLE exato `KPrinter_a4f1` e seleciona a primeira característica GATT gravável. Isso é uma heurística de descoberta, não uma confirmação do protocolo da LT-8359.
- O relatório da impressora informa `BT, USB PRINT`, mas ainda não confirma BLE GATT, UUIDs, tamanho de pacote, codificação ESC/POS nem se a primeira característica gravável é o canal de impressão. Se a LT-8359 usar Bluetooth clássico SPP, este firmware BLE não será compatível; será necessário adaptar para SPP com um ESP32 que suporte Bluetooth clássico.
- O firmware mantém a conexão BLE antes de reservar um pedido; se a impressora estiver desligada ou fora de alcance, o trabalho continua aguardando na fila. O envio em blocos de 20 bytes é conservador para BLE. A confirmação HTTP indica que os bytes foram aceitos pela característica GATT; não confirma que o mecanismo imprimiu papel.
- A conexão HTTPS valida o certificado usando a raiz ISRG Root X1 incorporada ao firmware. Se o certificado/CA apresentado pelo Railway mudar, atualize a raiz e valide novamente antes de operar.
- Uma queda após o envio e antes da confirmação pode gerar reimpressão duplicada (entrega at-least-once).

## API

A ponte consulta `GET /api/print-agent/jobs/next?station_id=...` e confirma em `POST /api/print-agent/jobs/{id}/result`. Ambas exigem `X-Print-Agent-Token` e `X-Print-Agent-Id`.
