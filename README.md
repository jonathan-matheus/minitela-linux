# Minitela Linux

App nativo e open source para controlar a **minitela** do notebook Positivo Vision R15M
em qualquer distribuição Linux, distribuído como Flatpak.

> ⚠️ Versão de prévia. Testada no Arch Linux (Omarchy, Hyprland); outras distribuições
> devem funcionar do mesmo jeito, mas ainda não foram testadas.

## Por quê?

O app oficial só é distribuído como `.deb` (Ubuntu e derivados). Em outras distros é
preciso recorrer a containers (Distrobox). Além disso, ele instala regras udev que liberam
todas as portas seriais e todos os teclados para qualquer usuário (`MODE="0666"`).

Este projeto reimplementa o protocolo de comunicação da minitela do zero para oferecer:

- **Qualquer distro**: empacotado como Flatpak.
- **Mais seguro**: permissão de acesso só para o usuário logado (`uaccess`).
- **Mais leve**: sem Electron, sem binários fechados.
- **Livre**: licença MIT.

## Funcionalidades

- Relógio, bateria, Wi-Fi e Bluetooth
- Clima (Open-Meteo, sem chave de API)
- Lembrete e notificações do WhatsApp
- Brilho, troca e rotação de telas, pela janela, pela bandeja ou pela tecla da minitela
- GIFs de fábrica (importados do pacote oficial)
- A tela apaga ao suspender ou bloquear a sessão
- Interface em português e inglês

## Instalação

Um comando instala tudo. Baixe o `install.sh` e o `minitela.flatpak` da página de releases
(ou dos artefatos do CI), coloque os dois na mesma pasta e rode, como seu usuário (sem
`sudo`):

```sh
sh install.sh
```

O instalador:

1. instala o Flatpak, se a distro ainda não tiver (com `pacman`, `dnf`, `apt` ou `zypper`);
2. instala o app, que vem do `minitela.flatpak` ao lado do script, do código-fonte (se o
   script estiver dentro do repositório, compilando com o `flatpak-builder`) ou do Flathub;
3. libera o acesso à minitela e à tecla dela (pede a sua senha, veja abaixo);
4. pergunta se você quer as notificações do WhatsApp e se o app deve iniciar com a sessão;
5. mostra como ligar a tecla da minitela no seu desktop e abre o app.

Rodar de novo atualiza o app e permite mudar as respostas. Para remover tudo:

```sh
sh install.sh --uninstall                 # mantém configurações e GIFs importados
sh install.sh --uninstall --delete-data   # apaga também
```

As opções (`--yes`, `--notifications`, `--no-autostart`, `--bundle ARQUIVO`...) estão em
`sh install.sh --help`.

### O que precisa de `sudo`

Só um passo, e só porque um app Flatpak não pode mudar o sistema sozinho: instalar dois
arquivos do udev. O script que faz isso vem dentro do próprio app
(`/app/share/minitela/host-setup.sh`).

- `/etc/udev/rules.d/70-minitela.rules`: dá acesso à porta serial da minitela só ao usuário
  da sessão ativa (`uaccess`), e a nenhuma outra porta.
- `/etc/udev/hwdb.d/70-minitela-keyboard.hwdb`: faz a tecla da minitela gerar
  `KEY_PROG1` (`XF86Launch1`).

Funciona em qualquer distro com systemd (Arch, Fedora, Ubuntu, Debian, openSUSE...).

### Importe os GIFs de fábrica (opcional)

Os GIFs pertencem à fabricante e não são distribuídos aqui. Baixe o pacote oficial
(`minitela_*.deb`) e, na aba **GIFs**, use **Importar pacote oficial…**. O arquivo só é
lido: nada do app oficial é instalado.

### Vindo do app oficial

Feche e desinstale o app oficial antes: dois programas não podem usar a minitela ao mesmo
tempo. O instalador avisa se encontrar as regras `0666` antigas
(`/etc/udev/rules.d/99-ttyacm.rules` e `99-custom-input.rules`); elas podem ser apagadas.

<details>
<summary>Instalação manual, sem o <code>install.sh</code></summary>

```sh
# O app (o runtime do GNOME vem do Flathub)
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user minitela.flatpak

# Acesso à minitela (uma vez); troque install por status ou uninstall
flatpak run --command=cat dev.pragmatico.Minitela /app/share/minitela/host-setup.sh | sudo sh -s install
```

Para compilar a partir do código:

```sh
flatpak install --user flathub org.flatpak.Builder
flatpak run org.flatpak.Builder --user --install --force-clean --install-deps-from=flathub \
    build-dir build-aux/flatpak/dev.pragmatico.Minitela.yml
```

</details>

## Integração com o desktop

### Notificações do WhatsApp

Para ler as notificações, o app precisa observar o barramento da sessão, uma permissão
ampla que o Flatpak não concede por padrão. O instalador pergunta se você quer liberá-la;
sem ela, todo o resto funciona normalmente. Manualmente:

```sh
flatpak override --user --socket=session-bus dev.pragmatico.Minitela
```

### Tecla da minitela

A tecla troca de tela depois de configurada como atalho do desktop, executando:

```sh
flatpak run --command=minitela dev.pragmatico.Minitela next-page
```

- **GNOME**: Configurações → Teclado → Ver e personalizar atalhos → Atalhos
  personalizados; pressione a tecla da minitela ao definir o atalho.
- **KDE**: Configurações do sistema → Teclado → Atalhos → Adicionar novo → Comando.
- **Hyprland** (`hyprland.conf`):
  `bind = , XF86Launch1, exec, flatpak run --command=minitela dev.pragmatico.Minitela next-page`.
  Com a configuração em Lua:
  `hl.bind("XF86Launch1", hl.dsp.exec_cmd("flatpak run --command=minitela dev.pragmatico.Minitela next-page"))`.

### Iniciar com a sessão

O instalador pergunta se o app deve abrir escondido no login, continuando a atualizar a
minitela com a janela fechada (há um ícone na bandeja, se o desktop tiver uma). Ele cria a
entrada `~/.config/autostart/dev.pragmatico.Minitela.desktop`, que funciona em qualquer
desktop, inclusive no Hyprland.

No GNOME e no KDE também dá para mudar isso na aba **Tela** do app (**Iniciar com a
sessão**). No Hyprland, que não oferece o portal usado pelo app, rode o instalador de novo.

### Bloqueio de tela

A minitela apaga ao bloquear a sessão no GNOME, no KDE e em desktops que informam o
bloqueio ao systemd-logind, além do Hyprland (hyprlock).

## Permissões do Flatpak

| Permissão | Para quê |
|---|---|
| `--device=all` | Porta serial da minitela (o Flatpak não tem uma opção só para portas seriais) |
| `--share=network` | Previsão do tempo e busca de cidades |
| UPower, NetworkManager, BlueZ | Bateria, Wi-Fi e Bluetooth |
| `org.freedesktop.login1` | Apagar a tela ao suspender e ao bloquear |
| ScreenSaver | Apagar a tela ao bloquear (GNOME, KDE) |
| `org.kde.StatusNotifierWatcher` | Ícone na bandeja |
| `xdg-run/hypr` | Detectar o bloqueio do Hyprland |

## Problemas comuns

- **"Sem permissão para usar a minitela"**: rode `sh install.sh` de novo (ou o comando da
  instalação manual com `status` para conferir). A permissão vale para a sessão local
  ativa; uma sessão remota (SSH) não recebe acesso.
- **"Outro processo do Minitela está controlando a minitela"**: outra cópia (ou o
  `minitela run` da linha de comando) já está rodando. Feche-a, ou use a bandeja dela.
- **Diagnóstico**: `flatpak run --command=minitela dev.pragmatico.Minitela probe` mostra
  se o app encontra e consegue falar com a minitela.

## Desenvolvimento

Veja [CONTRIBUTING.md](CONTRIBUTING.md). A documentação do protocolo está em
[docs/](docs/).

## Aviso

Projeto independente, sem relação com a Positivo Tecnologia ou a PoliCorp Tecnologia.
Nenhum arquivo do software oficial é distribuído aqui.

## Licença

[MIT](LICENSE)
