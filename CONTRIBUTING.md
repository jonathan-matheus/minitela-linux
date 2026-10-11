# Contribuindo

## Ambiente de desenvolvimento

Requer Python 3.11+ e o PyGObject da distribuição (`python-gobject` no Arch, `python3-gi` no
Debian/Ubuntu, `python3-gobject` no Fedora), usado para o D-Bus e a interface. O ambiente
virtual precisa enxergar os pacotes do sistema:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e . --group dev
```

Sem o PyGObject, os testes que dependem dele são pulados e o resto funciona normalmente.

## Antes de cada commit

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest
```

O CI roda os mesmos comandos em Python 3.11, 3.12 e 3.13.

## Estrutura do projeto

Cada camada só depende das camadas acima dela na lista e pode ser testada sozinha.

| Caminho | Responsabilidade |
|---|---|
| `minitela/protocol/` | Quadros, CRC, comandos e registradores. Código puro, sem I/O. |
| `minitela/transport/` | Porta serial real, descoberta do dispositivo e `FakeTransport` para testes. |
| `minitela/device.py` | API de alto nível: handshake, brilho, página, tags, envio de arquivos. |
| `minitela/sources/` | Fontes de dados: relógio, bateria, Wi-Fi, Bluetooth, clima, mídia, notificações, lembretes. |
| `minitela/service.py` | Agendador que lê as fontes e envia ao dispositivo só o que mudou. |
| `minitela/cli.py` | CLI de diagnóstico, usada para validar cada etapa no hardware. |
| `minitela/ui/` | App GTK4/libadwaita. |
| `host/` | Arquivos instalados no sistema host: regra udev e hwdb. |
| `build-aux/flatpak/` | Manifesto do Flatpak. |
| `docs/` | Documentação do protocolo e do formato de arquivos. |

## Convenções

- Commits seguem [Conventional Commits](https://www.conventionalcommits.org/) em inglês
  (`feat:`, `fix:`, `test:`, `docs:`, `build:`, `ci:`, `chore:`), com escopo opcional
  (`feat(protocol): ...`).
- Um commit faz uma coisa só, e o projeto continua passando no lint e nos testes depois dele.
- Código e comentários em inglês. README, documentação e interface em pt-BR, com tradução
  via gettext.

## Engenharia reversa e arquivos do fabricante

O protocolo foi documentado a partir do comportamento do app oficial. **Não copie código do
app oficial** e **não adicione ao repositório arquivos do pacote oficial** (`.deb`, `.acf`,
GIFs, imagens). Eles são importados pelo próprio usuário a partir do `.deb` que ele baixou.

Capturas de tráfego serial (só os bytes trocados com o dispositivo) podem ser adicionadas
como fixtures de teste em `tests/fixtures/`.

## Testes no hardware

Etapas que exigem validação no dispositivo real estão marcadas com 🔌 no plano. Antes de
testar, feche o app oficial (e o container do Distrobox, se usado) para não disputar a
porta serial.
