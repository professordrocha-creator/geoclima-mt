# climate/management/commands/importar_mt_completo.py
"""
Orquestra o backfill completo do CHIRPS (1981 até a última data
publicada) pra TODOS os municípios de Mato Grosso de uma vez — não só
Tangará da Serra/Cáceres. Pensado pra rodar desassistido por muitas
horas (potencialmente o fim de semana inteiro).

NÃO reimplementa a extração/gravação — chama import_chirps via
call_command, um município por vez (nunca em paralelo, pra não
estourar quota concorrente do GEE), mesmo padrão já usado por
climate/tasks.py:atualizar_chirps.

Só processa município já `ativo=True` (mesma regra do próprio
import_chirps) — rodar `Municipio.objects.filter(uf='MT').update(
ativo=True)` antes é responsabilidade de quem chama este comando, não
deste comando (decisão deliberada: ativar municípios é uma operação
de dado que merece ser revisada/confirmada à parte, não escondida
dentro de uma importação de 22h).

Robustez:
- Município já completo (tem registro em 1981-01-01 e na data final)
  é PULADO — retomar depois de uma interrupção não reprocessa o que já
  entrou, e não desperdiça quota do GEE reconsultando anos já corretos.
- Falha num município: loga e segue pro próximo. Não aborta a
  importação inteira por causa de UM município ruim.
- Circuit breaker: 5 falhas SEGUIDAS (não 5 no total) — pausa
  PAUSA_CIRCUIT_BREAKER_SEGUNDOS e tenta o mesmo município mais uma
  vez. Se a segunda tentativa também falhar, é sinal de algo
  sistêmico (quota do GEE esgotada, serviço fora do ar) — a essa
  altura, continuar batendo nos próximos 130+ municípios só queimaria
  quota contra o mesmo problema. Para a execução inteira e avisa,
  bem visível, no fim do log.
- Log em arquivo (import_mt_log.txt, raiz do projeto — visível no
  host via o bind mount), uma linha por município, com timestamp,
  gravada (append + flush) IMEDIATAMENTE — nada se perde se o
  processo cair no meio.

Uso (rodar DETACHED — sobrevive à sessão que o iniciou, só não
sobrevive o container `web` ser reiniciado):
    docker compose exec -d web python manage.py importar_mt_completo

Pra testar em pequena escala antes do run completo (--limite restringe
a quantos municípios processar, --start permite um período curto):
    docker compose exec web python manage.py importar_mt_completo --limite 1 --start 2026-07-25
"""
import time
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from climate.models import ChirpsData
from climate.tasks import _obter_ultima_data_disponivel_no_gee
from maps.models import Municipio

DATA_INICIO_PADRAO = "1981-01-01"
CHUNK_DAYS = 365
PAUSA_ENTRE_MUNICIPIOS_SEGUNDOS = 5
LIMITE_FALHAS_CONSECUTIVAS = 5
PAUSA_CIRCUIT_BREAKER_SEGUNDOS = 300  # 5 minutos
LOG_PATH = "import_mt_log.txt"


class Command(BaseCommand):
    help = "Importa CHIRPS histórico completo para todos os municípios de MT (ativo=True), um por vez, com log e circuit breaker."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start", type=str, default=DATA_INICIO_PADRAO,
            help=f"Data inicial AAAA-MM-DD (padrão: {DATA_INICIO_PADRAO}).",
        )
        parser.add_argument(
            "--limite", type=int, default=None,
            help="Processa só os N primeiros municípios (ordenados por código IBGE) — útil pra testar em escala pequena antes do run completo.",
        )

    def handle(self, *args, **options):
        data_inicio = date.fromisoformat(options["start"])
        limite = options["limite"]
        inicio_execucao = time.monotonic()

        with open(LOG_PATH, "a", encoding="utf-8") as log:
            self._log(log, "=" * 70)
            self._log(log, "Início da importação completa de MT")

            data_fim = self._descobrir_data_fim(log)

            municipios = list(Municipio.objects.filter(uf="MT", ativo=True).order_by("codigo_ibge"))
            if limite:
                municipios = municipios[:limite]
            total = len(municipios)

            if total == 0:
                raise CommandError(
                    "Nenhum município de MT com ativo=True encontrado. Rode "
                    "Municipio.objects.filter(uf='MT').update(ativo=True) antes."
                )

            self._log(log, f"Municípios a processar: {total}. Período: {data_inicio.isoformat()} a {data_fim.isoformat()}.")

            ok, falhas, pulados = [], [], []
            falhas_consecutivas = 0

            for indice, municipio in enumerate(municipios, start=1):
                prefixo = f"{indice}/{total} | {municipio.nome}/{municipio.uf} ({municipio.codigo_ibge})"

                if self._ja_completo(municipio, data_inicio, data_fim):
                    pulados.append(municipio.nome)
                    self._log(log, f"{prefixo} | PULADO (já completo até {data_fim.isoformat()})")
                    continue

                sucesso, detalhe = self._importar_municipio(municipio, data_inicio, data_fim)

                if sucesso:
                    ok.append(municipio.nome)
                    falhas_consecutivas = 0
                    self._log(log, f"{prefixo} | OK | {detalhe}")
                    time.sleep(PAUSA_ENTRE_MUNICIPIOS_SEGUNDOS)
                    continue

                # Falhou.
                falhas_consecutivas += 1
                self._log(log, f"{prefixo} | ERRO | {detalhe} (falhas seguidas: {falhas_consecutivas})")

                if falhas_consecutivas < LIMITE_FALHAS_CONSECUTIVAS:
                    falhas.append(municipio.nome)
                    time.sleep(PAUSA_ENTRE_MUNICIPIOS_SEGUNDOS)
                    continue

                # Circuit breaker: LIMITE_FALHAS_CONSECUTIVAS seguidas.
                self._log(
                    log,
                    f"CIRCUIT BREAKER: {LIMITE_FALHAS_CONSECUTIVAS} falhas seguidas. "
                    f"Pausando {PAUSA_CIRCUIT_BREAKER_SEGUNDOS}s e retentando "
                    f"{municipio.nome} uma vez antes de decidir se para...",
                )
                time.sleep(PAUSA_CIRCUIT_BREAKER_SEGUNDOS)
                sucesso_retry, detalhe_retry = self._importar_municipio(municipio, data_inicio, data_fim)

                if sucesso_retry:
                    ok.append(municipio.nome)
                    falhas_consecutivas = 0
                    self._log(log, f"{prefixo} | OK (retry pós-pausa do circuit breaker) | {detalhe_retry}")
                    time.sleep(PAUSA_ENTRE_MUNICIPIOS_SEGUNDOS)
                    continue

                # Falha persistiu mesmo depois da pausa — para tudo e avisa.
                falhas.append(municipio.nome)
                self._log(log, f"{prefixo} | ERRO PERSISTENTE após pausa do circuit breaker | {detalhe_retry}")
                self._log(log, "!" * 70)
                self._log(
                    log,
                    "EXECUÇÃO INTERROMPIDA PELO CIRCUIT BREAKER — falha persistiu mesmo "
                    "após pausa. Provável esgotamento de quota do GEE ou serviço fora do "
                    "ar. Revisar manualmente antes de rodar de novo — municípios já "
                    "importados (marcados OK acima) NÃO serão reprocessados na retomada.",
                )
                self._log(log, "!" * 70)
                self._resumo_final(log, ok, falhas, pulados, total, inicio_execucao, interrompido=True)
                raise CommandError(
                    f"Circuit breaker acionado em {municipio.nome} — importação interrompida. "
                    f"Ver {LOG_PATH}."
                )

            self._resumo_final(log, ok, falhas, pulados, total, inicio_execucao, interrompido=False)

    def _descobrir_data_fim(self, log):
        """
        Consulta a última data REALMENTE publicada no CHIRPS UMA ÚNICA
        VEZ (não "hoje", não recalculada por município) — pra manter
        os 142 municípios com exatamente o mesmo período, mesmo numa
        execução que atravessa vários dias. Reaproveita a mesma função
        já usada pela task diária (climate/tasks.py), não duplica essa
        lógica.
        """
        try:
            data_fim = _obter_ultima_data_disponivel_no_gee()
        except Exception as exc:
            raise CommandError(f"Não foi possível consultar a última data publicada no CHIRPS: {exc}")
        self._log(log, f"Última data publicada no CHIRPS (consultada agora, fixa pro resto da execução): {data_fim.isoformat()}")
        return data_fim

    def _ja_completo(self, municipio, data_inicio, data_fim):
        """
        Município considerado completo se já tem registro na data de
        início E na data de fim do período pedido — evita reprocessar
        em caso de retomada. Município parcialmente importado (ex.:
        processo interrompido no meio dele) é reprocessado por
        inteiro; import_chirps já é idempotente (update_or_create),
        então isso não duplica nada, só é um pouco menos eficiente
        pra esse único município.
        """
        datas = ChirpsData.objects.filter(municipio=municipio)
        tem_inicio = datas.filter(date=data_inicio).exists()
        tem_fim = datas.filter(date=data_fim).exists()
        return tem_inicio and tem_fim

    def _importar_municipio(self, municipio, data_inicio, data_fim):
        """
        Chama import_chirps pra um único município, capturando a
        saída (não a lógica) — devolve (sucesso, mensagem_curta) pro
        log, nunca deixa uma exceção subir e derrubar o loop inteiro.
        """
        buffer = StringIO()
        try:
            call_command(
                "import_chirps",
                municipio=municipio.codigo_ibge,
                start=data_inicio.isoformat(),
                end=data_fim.isoformat(),
                chunk_days=CHUNK_DAYS,
                stdout=buffer,
                stderr=buffer,
            )
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"

        saida = buffer.getvalue().strip().splitlines()
        resumo = next((linha for linha in reversed(saida) if "Import concluído" in linha), None)
        return True, (resumo.strip() if resumo else "concluído (sem linha de resumo capturada)")

    def _resumo_final(self, log, ok, falhas, pulados, total, inicio_execucao, interrompido):
        duracao_horas = (time.monotonic() - inicio_execucao) / 3600
        total_chirps_mt = ChirpsData.objects.filter(municipio__uf="MT").count()

        self._log(log, "=" * 70)
        self._log(log, "RESUMO — " + ("INTERROMPIDA PELO CIRCUIT BREAKER" if interrompido else "CONCLUÍDA"))
        self._log(log, f"Duração: {duracao_horas:.2f}h")
        self._log(log, f"Municípios processados com sucesso: {len(ok)}/{total}")
        self._log(log, f"Municípios pulados (já completos): {len(pulados)}/{total}")
        self._log(log, f"Municípios com falha: {len(falhas)}/{total}")
        if falhas:
            self._log(log, f"  Falharam (reprocessar depois): {', '.join(falhas)}")
        self._log(log, f"Total de registros ChirpsData de MT no banco agora: {total_chirps_mt}")
        self._log(log, "=" * 70)

    def _log(self, arquivo, mensagem):
        linha = f"[{timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}] {mensagem}"
        arquivo.write(linha + "\n")
        arquivo.flush()
        self.stdout.write(linha)
