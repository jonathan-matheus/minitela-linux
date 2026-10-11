# Minitela Linux

App nativo e open source para controlar a **minitela** do notebook Positivo Vision R15M
em qualquer distribuição Linux, distribuído como Flatpak.

> ⚠️ Projeto em desenvolvimento inicial. Ainda não há nada utilizável.

## Por quê?

O app oficial só é distribuído como `.deb` (Ubuntu e derivados). Em outras distros é
preciso recorrer a containers (Distrobox). Além disso, ele instala regras udev que liberam
todas as portas seriais e todos os teclados para qualquer usuário (`MODE="0666"`).

Este projeto reimplementa o protocolo de comunicação da minitela do zero para oferecer:

- **Qualquer distro**: empacotado como Flatpak.
- **Mais seguro**: permissão de acesso só para o usuário logado (`uaccess`).
- **Mais leve**: sem Electron, sem binários fechados.
- **Livre**: licença MIT.

## Funcionalidades planejadas

- Relógio, bateria, Wi-Fi e Bluetooth
- Clima (Open-Meteo, sem chave de API)
- Lembretes, mídia tocando e notificações
- Brilho, troca e rotação de telas
- GIFs de fábrica (importados do pacote oficial)
- Apagar a tela ao suspender ou bloquear a sessão

## Aviso

Projeto independente, sem relação com a Positivo Tecnologia ou a PoliCorp Tecnologia.
Nenhum arquivo do software oficial é distribuído aqui.

## Licença

[MIT](LICENSE)
