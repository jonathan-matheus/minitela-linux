# Registradores e páginas

O conteúdo da minitela é um projeto da IDE AHMI gravado no dispositivo como textura
(`Texture.acf`). Esse projeto define as páginas e os **registradores** (tags) que o
computador preenche via `SET_REGISTER` (ver [protocol.md](protocol.md)).

A fonte principal deste documento é o `data.json` do projeto AHMI que acompanha o app
oficial (`resources/ACF/file.zip`). Os dados do projeto são:

| Item | Valor |
|---|---|
| Nome do projeto | `Minitela1.0` |
| ID do projeto | `67004c7703ad6966e4fe0d13` |
| Chip | GC9002 |
| Resolução | 240 × 240 |
| Codificação de texto | UTF-8 |
| Versão da IDE | 1.10.19 (2025-01-09) |

A coluna "Escrito por" indica a função do app oficial em C++ que escreve o registrador.
Os valores de exemplo vêm das capturas em `tests/fixtures/`. Os pontos marcados com ❓ ainda
não foram observados no dispositivo.

## Páginas

O registrador 2 seleciona a página exibida.

| Valor | Página | Conteúdo |
|---|---|---|
| 1 | `WhatsApp` | Última notificação |
| 2 | `Reminder` | Lembrete |
| 3 | `SystemInfo` | Bateria, Wi-Fi, Bluetooth |
| 4 | `Weather` | Clima atual e previsão |
| 5 | `Gif1` | GIF |
| 6 | `Gif2` | GIF |
| 7 | `Gif3` | GIF |
| 8-10 | `New-page` | Não usadas |

O app oficial mostra a página 1 ao iniciar e a página 5 depois de enviar uma textura nova.
As páginas 1 a 5 foram confirmadas nas capturas (`pages.hex`).

## Sequência de inicialização do app oficial

Capturada em `startup.hex`, com ~500 ms entre os quadros:

1. Brilho (7) e página 1 (2)
2. Data e hora (2006)
3. Bateria (1150 e 1082), Bluetooth (1085), Wi-Fi (1083)
4. Fundos de mensagem (2025, 2026) e notificações limpas (1140 a 1143)

## Registradores do sistema

Definidos pela plataforma AHMI. Os nomes originais estão em chinês.

| ID | Tipo | Nome original | Significado | Usado pelo app oficial |
|---|---|---|---|---|
| 1 | num | 动画控制 | Controle de animação | |
| 2 | num | 当前页面序号 | **Página atual** (1-10) | ✅ |
| 3 | num | 传递按键编码 | Código de tecla | |
| 4 | num | 时钟变量年月日 | Data do relógio interno | MiniPanel |
| 5 | num | 时钟变量时分秒 | Hora do relógio interno | MiniPanel |
| 6 | num | 蜂鸣器 | Buzzer | |
| 7 | num | 背光 | **Brilho da luz de fundo** (0-100) | ✅ |
| 8 | num | 帧率 | Taxa de quadros | |
| 9 | num | 触摸屏校准 | Calibração de toque | |
| 10 | str 32 | 一体化软件版本 | Versão do software integrado | |
| 11 | str 32 | IDE版本 | Versão da IDE | |
| 12 | str 32 | CPU0版本 | Versão da CPU0 | |
| 13 | str 32 | CPU1版本 | Versão da CPU1 | |
| 14 | str 32 | CPU0BOOT版本 | Versão do bootloader da CPU0 | |
| 15 | str 32 | CPU1BOOT版本 | Versão do bootloader da CPU1 | |
| 16 | str 32 | 芯片（设备）版本 | Versão do chip | |
| 17 | str 240 | 异常记录 | Registro de erros | |
| 18 | num | 异常记录页面序号 | Página do registro de erros | |
| 19 | num | 复位类型 | Tipo do último reset | |
| 20 | num | 对比度 | Contraste | |
| 21 | num | 饱和度 | Saturação | |
| 22 | num | 亮度 | Brilho da imagem | |
| 23 | num | 变量指针 | Ponteiro de variável | |
| 24 | num | 屏幕的旋转方向 | Rotação da tela | |
| 25 | num | 息屏时间 | Tempo para apagar a tela | |
| 26 | num | 色度 | Matiz | |
| 27 | num | 色温 | Temperatura de cor | |
| 28 | num | 伽马矫正 | Correção de gama | |
| 29 | num | 滑动切换页面隐藏 | Ocultar troca de página por gesto | |
| 30 | num | 音量调节 | Volume | |

Os registradores 10 a 16 são bons candidatos para o comando `probe` (identificação do
dispositivo) por serem somente leitura.

### Data e hora (4 e 5)

O MiniPanel escreve data e hora com os dígitos decimais lidos como hexadecimal:

| Registrador | Formato | Exemplo (11/10/2026 14:05:09) |
|---|---|---|
| 4 | `0xAAAAMMDD` | `0x20261011` |
| 5 | `0x00HHMMSS` | `0x00140509` |

O layout da Positivo não exibe o relógio interno. O app oficial em C++ não escreve esses
registradores e envia a data como texto no registrador 2006.

## Registradores do layout da Positivo

| ID | Tipo | Nome | Página | Escrito por | Conteúdo |
|---|---|---|---|---|---|
| 1082 | str 32 | `Battery_Percent` | SystemInfo | `CheckSystem` | Porcentagem da bateria com `%`: `"100%"` |
| 1083 | str 32 | `Wifi_SSID` | SystemInfo | `CheckSystem` | Nome da rede Wi-Fi, cortado em 9 caracteres + `...` quando é maior; `"Desconectado"` sem rede |
| 1085 | str 32 | `BT_Name` | SystemInfo | `CheckSystem` | Dispositivo Bluetooth conectado; `"Desconectado"` sem dispositivo |
| 1150 | num | `Battery_Type` | SystemInfo | `CheckSystem` | Ícone da bateria: 0 (1 barra, vermelho) a 3 (4 barras, verde); `3` com 100%. ❓ Faixas usadas pelo app oficial |
| 1090 | str 100 | `Reminder1` | Reminder | `GetTaskFromFile`, `on_button_task_pressed` | Texto do lembrete, pode ter `\n`. O app limpa (`" "`) antes de gravar |
| 2006 | str 32 | `dateHour` | várias | `UpdateDateInfo` | Data e hora `"DD/MM HH:MM"`, enviada uma vez por minuto: `"11/10 02:21"` |
| 2027 | str 32 | `city` | Weather | `SendWeatherToHardware` | Nome da cidade |
| 1110 | num | `Weather_1_Type` | Weather | `SendWeatherToHardware` | Ícone do clima de hoje (tabela abaixo) |
| 2030 | str 32 | `currentTemp` | Weather | `SendWeatherToHardware` | Mínima e máxima de hoje: `"25°/26°"` |
| 1115 | num | `Weather_2_Type` | Weather | `SendWeatherToHardware` | Ícone da previsão 1 |
| 2031 | str 32 | `forecastTemp1` | Weather | `SendWeatherToHardware` | Mínima e máxima da previsão 1 |
| 1119 | str 32 | `Weather_2_Temp_Desc` | Weather | `SendWeatherToHardware` | Rótulo da previsão 1: `"Sáb 29"` |
| 1120 | num | `Weather_3_Type` | Weather | `SendWeatherToHardware` | Ícone da previsão 2 |
| 2032 | str 32 | `forecastTemp2` | Weather | `SendWeatherToHardware` | Mínima e máxima da previsão 2 |
| 1124 | str 32 | `Weather_3_Temp_Desc` | Weather | `SendWeatherToHardware` | Rótulo da previsão 2 |
| 1140 | str 36 | `notification1Sender` | WhatsApp | `monitorNotifications`, `SendNotifications` | Remetente |
| 1141 | str 96 | `notification_1_content` | WhatsApp | `monitorNotifications`, `SendNotifications` | Texto da mensagem |
| 2005 | num | `whatsapp_logo` | WhatsApp | `monitorNotifications` | 0 ou 1: mostra o logo (há notificação) ❓ |
| 2025 | num | `MessageBackground1` | WhatsApp | `monitorNotifications`, `SendNotifications` | Fundo da mensagem. `1` sem notificações. ❓ Outros valores |
| 2026 | num | `MessageBackground2` | WhatsApp | `SendNotifications` | Fundo da mensagem. `1` sem notificações. ❓ Outros valores |

O app oficial também escreve `1142` e `1143` (segunda notificação) em `SendNotifications`,
mas esses IDs não existem no layout da Positivo. Sem notificações, ele limpa `1140` a `1143`
com `" "`. Os registradores com ID `0` no `data.json`
(`notification2Sender`, `notification_2_content`) estão desligados (`register: false`).

### Registradores internos do layout

Existem no projeto mas não são escritos pelos apps. Provavelmente são usados por animações
do próprio layout.

| ID | Tipo | Nome |
|---|---|---|
| 65 | num | 主题1_动画 (animação do tema 1) |
| 2000 | num | `MoveTrigger` |
| 2001 | num | `MoveX` |
| 2002 | num | `MoveY` |

## Registradores do MiniPanel que não existem no layout

O MiniPanel é um editor genérico e conhece registradores para outros layouts: uso de CPU e
GPU (1080, 1081), qualidade e status do Wi-Fi (1084, 1087), status do Bluetooth (1086),
lembretes 2 e 3 (1092-1095), mídia (1100-1102, 2003), clima de 5 dias (1111-1114,
1116-1118, 1121-1123, 1125-1134) e notificações 2 e 3 (1142-1145).

Eles **não fazem parte** do layout gravado de fábrica e não devem ser enviados. Se o layout
mudar no futuro (fase experimental de GIFs personalizados), esta lista pode ser revista.

## Textos e ícones do clima

Os formatos vêm dos textos de exemplo do próprio layout (`São Paulo`, `25°/26°`, `Sáb 29`) e
das strings do app oficial, que usa só `mintemp_c` e `maxtemp_c` da previsão.

Os ícones (registradores 1110, 1115 e 1120) são uma textura de 8 imagens no layout:

| Valor | Ícone |
|---|---|
| 0 | Sol |
| 1 | Sol com nuvem |
| 2 | Nuvem |
| 3 | Chuva |
| 4 | Lua |
| 5 | Lua com nuvem |
| 6 | Neve |
| 7 | Vazio |

O app oficial em C++ tinha 7 ícones próprios (`weather_icons/0.png` a `6.png`) e o MiniPanel
usava outra tabela (abaixo), feita para outro layout.

## Mapeamento do clima no MiniPanel

Referência para o ❓ dos ícones de clima. O MiniPanel converte as condições da OpenWeather
para estes valores:

| Condição | Valor |
|---|---|
| `Clear` | 1 |
| `Clouds`, `Mist`, `Smoke`, `Haze`, `Dust`, `Fog`, `Sand`, `Ash`, `Squall`, `Tornado` | 2 |
| `Thunderstorm`, `Drizzle`, `Rain`, `Snow` | 4 |

O app oficial em C++ usa a weatherapi.com e tem 7 ícones (`weather_icons/0.png` a `6.png`),
então o mapeamento dele provavelmente é outro. ❓ Descobrir na captura ou testando os valores
0 a 6 na página Weather.
