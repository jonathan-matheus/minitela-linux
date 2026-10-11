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

Resposta de `GET_DOWNLOAD_STATUS`, segundo o MiniPanel:

| Estado | Significado |
|---|---|
| `0x10` | Pronto para receber um arquivo |
| `0x11` | Recebendo um arquivo (gravação em andamento ou interrompida) |
| `0x20` | Executando o layout AHMI (operação normal) |

O firmware da minitela (`1.10.19_build_2024.09.20_GIFTest`) não segue isso: responde `0x10`
mesmo funcionando normalmente, com 3 bytes a mais, e o campo do id não é o MD5 da última
gravação. `GET_OFFSET` não tem resposta. Por isso **não há como retomar** uma gravação
interrompida: um envio que falha deve ser refeito do começo.

## Fluxo usado (confirmado no dispositivo)

Gravação da textura de fábrica 5 (1.622.024 bytes) em `tests/fixtures/device-upload.hex`:

```
1. HANDSHAKE
2. REQUEST_DOWNLOAD(0x08100000, tamanho, MD5)
     resposta em ~2,3 s (apagando a flash): página de 1024 bytes, código 0
     não é repetido em caso de demora: repetir recomeçaria o apagamento
3. DOWNLOAD_DATA(offset, bloco de 1024 bytes), 1585 vezes
     cada bloco é confirmado com código 0 em ~2 ms
     código 0xFFFFFFFF → aguardar a resposta final; outro código → reenviar o bloco
4. DOWNLOAD_COMPLETE → código 0
5. SET_REGISTER página = 5, para mostrar o GIF
```

O envio inteiro levou **7,3 s**. A porta serial continuou aberta, sem reiniciar o USB, mas o
layout foi recarregado: a página voltou para 1, por isso o passo 5 é necessário.

O MiniPanel consulta o estado antes (passo extra entre 1 e 2) para pular texturas já gravadas
e retomar envios; como este firmware não informa isso, o passo é omitido.

Durante a gravação, nenhum outro comando (registradores, troca de página) deve ser enviado.
Os dois apps oficiais param o envio periódico de dados enquanto gravam.

## Como o app oficial em C++ faz

Mais simples e menos robusto. Não lê o estado nem as respostas:

1. Fecha a porta serial, espera 1 s e reabre.
2. Envia `REQUEST_DOWNLOAD(0x08100000, tamanho, MD5)` e espera 200 ms.
3. Espera 3 s, tempo para apagar a flash (no dispositivo, o apagamento levou ~2,3 s).
4. Envia blocos de **1024 bytes** com `DOWNLOAD_DATA`, um a cada 10 ms, sem esperar
   resposta.
5. Envia `DOWNLOAD_COMPLETE`. O quadro tem `ctrl = 0x000A` mas só 4 bytes de conteúdo
   e nenhum campo de CRC, ou seja, está malformado. O dispositivo parece tolerar.
6. Espera 3 s, reabre a porta (até 10 tentativas) e muda para a página 5.

Esse modo continua disponível como alternativa (`minitela upload-acf --paced`), mas o fluxo
confirmado acima é tão rápido quanto e detecta blocos perdidos.

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
