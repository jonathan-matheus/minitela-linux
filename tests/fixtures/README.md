# Fixtures de tráfego serial

Bytes trocados entre o app oficial da minitela (versão 1.0.20) e o dispositivo real,
capturados num Positivo Vision R15M em 11/10/2026 com `tools/capture/`.

## Formato

Linhas começando com `#` são comentários. As demais têm três campos:

```
<segundos desde o primeiro quadro> <direção> <bytes em hexadecimal>
```

A direção é `>` do computador para o dispositivo e `<` do dispositivo para o computador.

O app oficial **nunca lê a porta serial**, então todas as linhas são `>`. As respostas do
dispositivo ainda não foram observadas.

## Arquivos

| Arquivo | Cenário |
|---|---|
| `startup.hex` | Inicialização: brilho, página 1, data, bateria, Bluetooth, Wi-Fi, notificações |
| `pages.hex` | Troca entre as páginas 1 a 5 |
| `brightness.hex` | Slider de brilho de 100 a 0 e de volta a 100 |
| `reminder.hex` | Gravação de um lembrete (com e sem quebras de linha) |
| `clock.hex` | Atualização de data e hora a cada minuto |
| `refresh-after-reconnect.hex` | Reenvio completo depois de reabrir a porta |

## Como reproduzir

```sh
tools/capture/capture.sh <pasta-com-o-.deb> <pasta-de-saída>
tools/capture/extract.py <pasta-de-saída>/trace-*.txt > traffic.hex
```

As capturas brutas não são versionadas. O nome da rede Wi-Fi foi trocado por
`rede-casa...`, com o mesmo tamanho do original.

## Limitações

- **Envio de GIF**: no Linux, o app oficial abre o editor MiniPanel para trocar o GIF, e ele
  depende de um conversor que só existe para Windows. Por isso não há captura do envio de
  textura (ver `docs/file-transfer.md`).
- **Clima**: o app oficial travou (segmentation fault) ao escolher a cidade, então não há
  captura dos registradores de clima.
