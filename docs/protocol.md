# Protocolo serial da minitela

Documentação do protocolo de comunicação entre o computador e a minitela do Positivo Vision
R15M, obtida por engenharia reversa do comportamento do app oficial (versão 1.0.20) e do
editor MiniPanel 0.1.6 que o acompanha.

O controlador da tela é um **GC9002**, programado com a IDE AHMI. O protocolo é o protocolo
genérico de comunicação dessa plataforma.

> **Status**: lido no código dos apps oficiais e conferido com capturas do tráfego real
> (`tests/fixtures/`). Os pontos marcados com ❓ ainda não foram confirmados no dispositivo.

Veja também:

- [registers.md](registers.md): mapa de registradores e páginas.
- [file-transfer.md](file-transfer.md): envio de arquivos (texturas `.acf`).

## Camada física

| Item | Valor |
|---|---|
| Interface | USB CDC ACM, aparece como `/dev/ttyACM*` |
| VID:PID | `0324:0324`, produto `sxw-admin_CDC_DEMO` |
| Velocidade | 115200 baud, 8N1 |

Os bytes podem chegar fragmentados em várias leituras, ou vários quadros podem chegar na mesma
leitura. O receptor precisa de um decodificador incremental.

## Formato do quadro

Todos os valores com mais de um byte são **big-endian**.

```
+-------+-------+-------+------------------+-------+-------+
| 41 48 | ctrl  | tipo  | conteúdo (N)     |  crc  | 4D 49 |
+-------+-------+-------+------------------+-------+-------+
  2 B     2 B     2 B     N bytes            2 B     2 B
```

| Campo | Descrição |
|---|---|
| Início | `41 48` (ASCII `AH`) |
| `ctrl` | Bit 15: CRC habilitado. Bits 14-0: tamanho de `tipo` + `conteúdo` (ou seja, `N + 2`). |
| `tipo` | Código do comando (tabela abaixo). |
| `conteúdo` | Depende do comando. Pode ser vazio. |
| `crc` | CRC-16 de `ctrl + tipo + conteúdo` quando o bit 15 está ligado; `00 00` quando não. |
| Fim | `4D 49` (ASCII `MI`) |

Tamanho total do quadro: `N + 10` bytes.

### CRC

O MiniPanel usa a função `crc16` do pacote npm `crc`, que é o **CRC-16/ARC** (polinômio
`0x8005` refletido = `0xA001`, valor inicial `0x0000`, sem XOR final). Porém, ele nunca liga
o CRC: todos os comandos são enviados com o bit 15 desligado e `crc = 00 00`.

O app oficial em C++ envia **sempre os bytes fixos `E2 CB`** no campo de CRC, tanto com o
bit 15 ligado (registrador numérico) quanto desligado (registrador de string). `E2CB` não é o
CRC desses quadros em nenhuma das variantes comuns de CRC-16 (ARC, MODBUS, CCITT, XMODEM).

**Conclusão**: o dispositivo não valida o CRC. ❓ Confirmar se ele responde normalmente a
quadros com CRC desligado e `00 00`, que é o que esta implementação vai enviar.

## Tipos de comando

O código da resposta é o código do comando **mais** `0x40` (`0x0070` → `0x00B0`, `0x0080` →
`0x00C0`). Não é um bit: em `0x0070` e `0x0071` o bit 6 já está ligado.

| Código | Comando | Resposta | Uso |
|---|---|---|---|
| `0x0080` | `HANDSHAKE` | `0x00C0` | Início da comunicação |
| `0x0081` | `REQUEST_DOWNLOAD` | `0x00C1` | Pedir para gravar um arquivo |
| `0x0082` | `DOWNLOAD_DATA` | `0x00C2` | Enviar um bloco do arquivo |
| `0x0083` | `UPLOAD_DATA` | `0x00C3` | Ler dados do dispositivo |
| `0x0085` | `GET_DOWNLOAD_STATUS` | `0x00C5` | Estado da gravação |
| `0x0086` | `GET_OFFSET` | `0x00C6` | Offset atual da gravação |
| `0x008F` | `DOWNLOAD_COMPLETE` | `0x00CF` | Fim da gravação |
| `0x0070` | `REBOOT` | `0x00B0` | Reiniciar o dispositivo |
| `0x0071` | `SWITCH_STATE` | `0x00B1` | Trocar o modo do dispositivo |
| `0x0090` | `SET_REGISTER` | `0x00D0` | Ler ou escrever registradores |

### Conteúdo dos comandos

| Comando | Conteúdo |
|---|---|
| `HANDSHAKE` | vazio |
| `GET_DOWNLOAD_STATUS` | vazio |
| `GET_OFFSET` | vazio |
| `REQUEST_DOWNLOAD` | `endereço (u32)` `tamanho (u32)` `id do arquivo (16 B)` |
| `DOWNLOAD_DATA` | `offset (u32)` `dados` |
| `DOWNLOAD_COMPLETE` | vazio |
| `UPLOAD_DATA` | `endereço (u32)` `tamanho (u32)` |
| `SWITCH_STATE` | `estado (u8)`. O único valor usado é `0x10` (modo download). |
| `REBOOT` | vazio |
| `SET_REGISTER` | ver [abaixo](#set_register) |

### Conteúdo das respostas

| Resposta | Conteúdo |
|---|---|
| `HANDSHAKE` | `tamanho máximo de pacote (u32)` |
| `GET_DOWNLOAD_STATUS` | `estado (u8)` `id do arquivo (16 B)` `offset (u32)` |
| `GET_OFFSET` | `offset (u32)` |
| `REQUEST_DOWNLOAD` | `tamanho máximo de página (u32)` `código (u32)` |
| `DOWNLOAD_DATA` | `código (u32)` |
| `DOWNLOAD_COMPLETE` | `código (u32)` |
| `UPLOAD_DATA` | `código (u32)`, e se `código = 0`: `offset (u32)` `dados` |
| `SWITCH_STATE` | `código (u32)` |
| `REBOOT` | `código (u32)` |
| `SET_REGISTER` | `cabeçalho (u8)` `dados` (ver abaixo) |

Códigos de resposta:

| Código | Significado |
|---|---|
| `0x00000000` | Sucesso |
| `0xFFFFFFFF` | Processando. Uma nova resposta do mesmo tipo chega depois, com o resultado final. |
| outro | Erro |

## SET_REGISTER

O primeiro byte do conteúdo é um cabeçalho:

```
bit 7      bits 6-4         bits 3-0
reply      função           contagem - 1
```

### Escrever registradores numéricos

Até 16 registradores por comando. Cada valor é um inteiro de 32 bits.

```
cabeçalho = 0x80 | (n - 1)
repetido n vezes:  id (u16)  valor (u32)
```

Exemplo, brilho (registrador 7) em 100%:

```
41 48 | 00 09 | 00 90 | 80 00 07 00 00 00 64 | 00 00 | 4D 49
```

### Escrever registrador de string

Um registrador por comando.

```
cabeçalho = 0xD0
id (u16)  tamanho (u16)  bytes
```

O texto é codificado em **UTF-8** (é o `encoding` do projeto AHMI) e pode conter quebras de
linha (`\n`). Cada registrador tem um tamanho máximo (ver [registers.md](registers.md)).
❓ Comportamento ao exceder o limite.

O app oficial nunca envia string vazia: para limpar um registrador ele envia um espaço
(`tamanho = 1`, byte `0x20`).

### Ler registradores numéricos

```
cabeçalho = 0xC0 | (n - 1)
repetido n vezes:  id (u16)
```

### Ler registrador de string

```
cabeçalho = 0xE0
id (u16)  tamanho a ler (u16)
```

### Resposta

A resposta a qualquer `SET_REGISTER` traz o valor atual dos registradores envolvidos:

| Função na resposta (bits 6-4) | Dados |
|---|---|
| `0` (numérico) | repetido `contagem` vezes: `id (u16)` `valor (u32)` |
| `3` (string) | `id (u16)` `tamanho (u16)` `bytes` |

## Comportamento dos apps oficiais

Úteis para decidir tempos de espera e repetição:

- **MiniPanel**: espera a resposta do tipo esperado. Se ela não chega, reenvia o mesmo
  comando a cada 5 s. Só considera o tipo da resposta, não confere qual registrador foi
  respondido.
- **App oficial (C++)**: envia os quadros e não espera resposta. Nas capturas ele nunca
  chamou `read()` na porta. Envia um quadro a cada ~500 ms durante a atualização completa e
  um quadro por mudança do slider de brilho, sem limitar a taxa. Quando a porta falha, fecha
  e reabre.
- O MiniPanel reenvia todos os registradores a cada 5 s, mesmo os que não mudaram.

Proposta para esta implementação: esperar a resposta com timeout curto (≈1 s), poucas
tentativas, e reconectar ao detectar erro de porta.
