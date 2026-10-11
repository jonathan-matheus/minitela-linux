# Envio de arquivos

Os GIFs e o layout da minitela ficam na memória flash do dispositivo, num arquivo de
textura `.acf` gerado pela IDE AHMI. Trocar o GIF exibido significa **regravar a textura
inteira**. Este documento descreve como isso é feito com os comandos de
[protocol.md](protocol.md).

Os pontos marcados com ❓ ainda precisam ser confirmados com capturas do dispositivo real.

## Mapa de memória

Endereços usados no campo `endereço` do `REQUEST_DOWNLOAD`, segundo comentários e constantes
do MiniPanel:

| Endereço | Tamanho | Arquivo |
|---|---|---|
| `0x08000000` | | `bootloader.bin` |
| `0x08040000` | 600 KB | `cpu1.bin` (firmware) |
| `0x080F7000` | | `upg_cfg.bin` |
| `0x080F8000` | 4 KB | `cpu0_config.bin` |
| `0x080FB000` | 4 KB | `calibration.bin` |
| `0x080FC000` | 4 KB | `EraseStoreSpace.bin` |
| `0x080FE008` | 4 KB | `hwconfig.bin` |
| `0x080FF008` | 4 KB | `product.bin` |
| `0x08100000` | 3/7/15 MB | **`Texture.acf`** (layout completo) |
| `0x08500000` | | Textura só de GIF (modo "only GIF" do MiniPanel) |

> ⚠️ **Só o endereço `0x08100000` deve ser usado.** Gravar nos outros endereços pode
> sobrescrever o firmware ou o bootloader e inutilizar o dispositivo.

O MiniPanel recusa arquivos maiores que 6436 KB.

## Identificador do arquivo

O `id do arquivo` (16 bytes) é o **MD5 do conteúdo do arquivo**. O dispositivo guarda o id
da última gravação, o que permite:

- não regravar uma textura que já está no dispositivo;
- retomar uma gravação interrompida a partir do último offset.

## Estados do dispositivo

Resposta de `GET_DOWNLOAD_STATUS`:

| Estado | Significado |
|---|---|
| `0x10` | Pronto para receber um arquivo |
| `0x11` | Recebendo um arquivo (gravação em andamento ou interrompida) |
| `0x20` | Executando o layout AHMI (operação normal) |

## Fluxo recomendado

Baseado no MiniPanel, que confere a resposta de cada etapa:

```
1. HANDSHAKE
2. GET_DOWNLOAD_STATUS  → estado, id, offset
     estado 0x20 e id == MD5 do arquivo  → já gravado, fim
     estado 0x20 e id != MD5             → SWITCH_STATE(0x10), exige código 0
     estado 0x10/0x11 e id == MD5        → retoma a partir do offset
     estado 0x10/0x11 e id != MD5        → começa do offset 0
3. REQUEST_DOWNLOAD(0x08100000, tamanho, MD5)
     → tamanho máximo de página, código
     código 0xFFFFFFFF → aguardar nova resposta com código 0 (até 60 s)
4. para cada bloco de até "tamanho máximo de página" bytes:
     DOWNLOAD_DATA(offset, bloco)
       código 0           → próximo bloco
       código 0xFFFFFFFF  → aguardar nova resposta com código 0 (até 60 s)
       outro código       → reenviar o mesmo bloco
5. DOWNLOAD_COMPLETE
     código 0xFFFFFFFF → aguardar nova resposta com código 0 (até 5 s)
     o MiniPanel ignora erros nesta etapa
6. Mostrar a página do GIF: SET_REGISTER página = 5
```

Durante a gravação, nenhum outro comando (registradores, troca de página) deve ser enviado.
Os dois apps oficiais param o envio periódico de dados enquanto gravam.

## Como o app oficial em C++ faz

Mais simples e menos robusto. Não lê o estado nem as respostas:

1. Fecha a porta serial, espera 1 s e reabre.
2. Envia `REQUEST_DOWNLOAD(0x08100000, tamanho, MD5)` e espera 200 ms.
3. Espera 3 s (tempo para apagar a flash ❓).
4. Envia blocos de **1024 bytes** com `DOWNLOAD_DATA`, um a cada 10 ms, sem esperar
   resposta.
5. Envia `DOWNLOAD_COMPLETE`. O quadro tem `ctrl = 0x000A` mas só 4 bytes de conteúdo
   e nenhum campo de CRC, ou seja, está malformado. O dispositivo parece tolerar.
6. Espera 3 s, reabre a porta (até 10 tentativas) e muda para a página 5.

Isso mostra que o dispositivo aceita os dados sem que se espere por cada resposta, e dá
valores de referência para os tempos de espera.

## Formato `.acf`

O app oficial traz 21 texturas prontas (`resources/ACF/Texture1.acf` a `Texture21.acf`),
uma para cada GIF de fábrica. Cada uma contém **o layout completo** com aquele GIF na
página `Gif1`. Escolher um GIF é gravar a textura correspondente.

Cabeçalho observado (valores little-endian):

| Offset | Tamanho | Conteúdo |
|---|---|---|
| `0x00` | 4 B | Tamanho do arquivo − 8 − `0x8000`. Sempre múltiplo de `0x8000`. Confere nos 22 arquivos. |
| `0x04` | 4 B | Soma de verificação ❓ (muda entre texturas de mesmo tamanho) |
| `0x08` | 4 B | Desconhecido ❓ (igual entre texturas de mesmo tamanho) |
| `0x0C` | 24 B | ID do projeto AHMI em ASCII (`67004c7703ad6966e4fe0d13`) |

O conteúdo depois do cabeçalho será estudado na fase experimental de GIFs personalizados.
Para gravar as texturas de fábrica, ele não precisa ser entendido: o arquivo é enviado
byte a byte como está.
