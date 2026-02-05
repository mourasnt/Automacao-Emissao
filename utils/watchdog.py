"""
RPA Watchdog - Detecção e Recuperação de Travamentos

Este módulo monitora jobs RPA em execução e detecta travamentos automáticamente.
Se um job exceder o tempo máximo permitido, o watchdog força uma limpeza e retry.

Características:
- Monitora tempo de execução de cada job
- Detecta travamentos após 15 minutos
- Força recarregamento de página e retry
- Registra jobs travados com detalhes
- Funciona com ThreadPoolManager
"""

import threading
import time
import json
from loguru import logger
from typing import Dict, Callable, Optional
from datetime import datetime, timedelta
import redis


class JobWatchdog:
    """
    Monitora jobs RPA e detecta travamentos.
    
    Uso:
        watchdog = JobWatchdog(
            redis_client=redis_client,
            max_job_duration=300,      # 5 minutos
            check_interval=30,         # Verificar a cada 30s
        )
        watchdog.iniciar()
        
        # Registrar um job em progresso
        watchdog.registrar_job("LT-001", worker_id=1)
        
        # Job completado
        watchdog.finalizar_job("LT-001")
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        max_job_duration: int = 300,  # 5 minutos
        check_interval: int = 30,      # Verificar a cada 30 segundos
    ):
        """
        Args:
            redis_client: Cliente Redis para persistência
            max_job_duration: Tempo máximo em segundos por job (default: 300s = 5min)
            check_interval: Intervalo de verificação em segundos
        """
        self.redis_client = redis_client
        self.max_job_duration = max_job_duration
        self.check_interval = check_interval
        
        # Dicionário de jobs em progresso
        # {"LT-001": {"inicio": timestamp, "worker_id": 1, "tipo": "conferencia"}}
        self.jobs_em_progresso: Dict[str, dict] = {}
        self.lock = threading.Lock()
        
        # Flag para controlar o watchdog
        self.running = False
        self.thread_monitor = None
    
    def registrar_job(self, job_id: str, worker_id: int, tipo_job: str = "conferencia"):
        """Registra um job como iniciado."""
        with self.lock:
            self.jobs_em_progresso[job_id] = {
                "inicio": datetime.now(),
                "worker_id": worker_id,
                "tipo": tipo_job,
                "duracao_segundos": 0
            }
        
        logger.debug(f"[Watchdog] Job '{job_id}' (worker {worker_id}) registrado. Máximo: {self.max_job_duration}s")
        
        # Persistir em Redis para recuperação em caso de crash
        try:
            self.redis_client.hset(
                "watchdog:jobs_em_progresso",
                job_id,
                json.dumps({
                    "inicio": datetime.now().isoformat(),
                    "worker_id": worker_id,
                    "tipo": tipo_job
                })
            )
        except Exception as e:
            logger.error(f"[Watchdog] Erro ao persistir job '{job_id}' no Redis: {e}")
    
    def finalizar_job(self, job_id: str):
        """Remove um job da lista de progresso (completado ou falhou)."""
        with self.lock:
            if job_id in self.jobs_em_progresso:
                duracao = (datetime.now() - self.jobs_em_progresso[job_id]["inicio"]).total_seconds()
                self.jobs_em_progresso[job_id]["duracao_segundos"] = duracao
                del self.jobs_em_progresso[job_id]
        
        # Remover de Redis
        try:
            self.redis_client.hdel("watchdog:jobs_em_progresso", job_id)
        except Exception as e:
            logger.error(f"[Watchdog] Erro ao remover job '{job_id}' do Redis: {e}")
    
    def detectar_travamentos(self):
        """Verifica quais jobs estão travados (excederam max_job_duration)."""
        agora = datetime.now()
        jobs_travados = []
        
        with self.lock:
            for job_id, info in self.jobs_em_progresso.items():
                duracao = (agora - info["inicio"]).total_seconds()
                
                if duracao > self.max_job_duration:
                    jobs_travados.append({
                        "job_id": job_id,
                        "worker_id": info["worker_id"],
                        "tipo": info["tipo"],
                        "duracao": duracao,
                        "inicio": info["inicio"]
                    })
        
        return jobs_travados
    
    def monitorar(self):
        """Loop principal do watchdog."""
        logger.info(f"[Watchdog] Iniciando monitor de jobs. Máximo: {self.max_job_duration}s, Verificação: {self.check_interval}s")
        
        while self.running:
            try:
                time.sleep(self.check_interval)
                
                if not self.running:
                    break
                
                # Detectar travamentos
                jobs_travados = self.detectar_travamentos()
                
                if jobs_travados:
                    for job in jobs_travados:
                        self._processar_job_travado(job)
                
                # Log de status periodicamente (a cada 5 verificações)
                if int(time.time()) % (self.check_interval * 5) == 0:
                    with self.lock:
                        if self.jobs_em_progresso:
                            logger.debug(
                                f"[Watchdog] {len(self.jobs_em_progresso)} job(s) em progresso. "
                                f"Máximo: {self.max_job_duration}s"
                            )
                
            except Exception as e:
                logger.error(f"[Watchdog] Erro no monitor: {e}")
    
    def _processar_job_travado(self, job_info: dict):
        """Processa um job que foi detectado como travado."""
        job_id = job_info["job_id"]
        duracao = job_info["duracao"]
        worker_id = job_info["worker_id"]
        tipo = job_info["tipo"]
        
        logger.critical(
            f"[Watchdog] 🚨 JOB TRAVADO DETECTADO!\n"
            f"  - Job ID: {job_id}\n"
            f"  - Worker: {worker_id}\n"
            f"  - Tipo: {tipo}\n"
            f"  - Duração: {duracao:.1f}s (Máximo: {self.max_job_duration}s)\n"
            f"  - Iniciado em: {job_info['inicio']}"
        )
        
        # Registrar em Redis para análise posterior
        try:
            travamento = {
                "job_id": job_id,
                "worker_id": worker_id,
                "tipo": tipo,
                "duracao_segundos": duracao,
                "detectado_em": datetime.now().isoformat(),
                "inicio": job_info["inicio"].isoformat()
            }
            
            self.redis_client.rpush(
                "watchdog:jobs_travados",
                json.dumps(travamento)
            )
            logger.warning(f"[Watchdog] Job '{job_id}' registrado em watchdog:jobs_travados para análise")
        except Exception as e:
            logger.error(f"[Watchdog] Erro ao registrar job travado no Redis: {e}")
        
        # ENVIAR KILL SIGNAL para o worker travado
        try:
            kill_signal = json.dumps({
                "worker_id": worker_id,
                "tipo": tipo,
                "job_id": job_id,
                "timestamp": datetime.now().isoformat(),
                "motivo": "timeout_travamento"
            })
            self.redis_client.sadd("watchdog:kill_workers", kill_signal)
            logger.warning(f"[Watchdog] 💀 Kill signal enviado para worker {worker_id} ({tipo})")
        except Exception as e:
            logger.error(f"[Watchdog] Erro ao sinalizar kill do worker: {e}")
        
        # Remover do controle após log (para evitar avisos repetidos)
        self.finalizar_job(job_id)
    
    def iniciar(self):
        """Inicia o watchdog em uma thread daemon."""
        if self.running:
            logger.warning("[Watchdog] Já está rodando")
            return
        
        self.running = True
        self.thread_monitor = threading.Thread(
            target=self.monitorar,
            daemon=True,
            name="RPA-Watchdog"
        )
        self.thread_monitor.start()
        logger.success("[Watchdog] Iniciado com sucesso")
    
    def parar(self):
        """Para o watchdog."""
        self.running = False
        logger.info("[Watchdog] Parando...")
    
    def obter_status(self) -> dict:
        """Retorna status atual do watchdog."""
        with self.lock:
            return {
                "jobs_em_progresso": len(self.jobs_em_progresso),
                "max_duracao": self.max_job_duration,
                "intervalo_verificacao": self.check_interval,
                "running": self.running
            }


class TimeoutDetector:
    """
    Detector de timeout para etapas individuais do RPA.
    
    Usa context manager para rastrear quanto tempo cada etapa leva.
    
    Uso:
        with TimeoutDetector("Buscando LT na tabela", max_seconds=10) as detector:
            # Código RPA aqui
            pass
    """
    
    def __init__(self, etapa: str, max_seconds: int = 30, job_id: str = ""):
        """
        Args:
            etapa: Nome da etapa RPA
            max_seconds: Tempo máximo esperado em segundos
            job_id: ID do job (para logging)
        """
        self.etapa = etapa
        self.max_seconds = max_seconds
        self.job_id = job_id
        self.inicio = None
        self.fim = None
    
    def __enter__(self):
        self.inicio = time.time()
        logger.debug(f"[RPA Etapa] ⏱️  Iniciando: {self.etapa} (timeout: {self.max_seconds}s) - Job: {self.job_id}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fim = time.time()
        duracao = self.fim - self.inicio
        
        if exc_type:
            logger.error(
                f"[RPA Etapa] ❌ ERRO em '{self.etapa}' após {duracao:.2f}s: {exc_val}"
            )
        elif duracao > self.max_seconds:
            logger.warning(
                f"[RPA Etapa] ⚠️  LENTO: '{self.etapa}' levou {duracao:.2f}s "
                f"(máximo: {self.max_seconds}s) - Job: {self.job_id}"
            )
        else:
            logger.debug(
                f"[RPA Etapa] ✓ OK: '{self.etapa}' levou {duracao:.2f}s - Job: {self.job_id}"
            )
        
        return False  # Não suprimir exceções
    
    def obter_duracao(self) -> float:
        """Retorna duração em segundos."""
        if self.inicio and self.fim:
            return self.fim - self.inicio
        return -1


def criar_timeout_com_fallback(
    func: Callable,
    timeout_segundos: int = 30,
    fallback_func: Optional[Callable] = None,
    nome_etapa: str = "RPA",
    job_id: str = ""
):
    """
    Executa função com timeout. Se exceder, executa fallback.
    
    Uso:
        resultado = criar_timeout_com_fallback(
            func=lambda: page.wait_for_selector("button", timeout=10000),
            timeout_segundos=15,
            fallback_func=lambda: page.reload(),
            nome_etapa="Aguardando botão",
            job_id="LT-001"
        )
    """
    import threading
    
    resultado = {"sucesso": False, "valor": None, "erro": None}
    
    def executar():
        try:
            with TimeoutDetector(nome_etapa, max_seconds=timeout_segundos, job_id=job_id):
                resultado["valor"] = func()
                resultado["sucesso"] = True
        except Exception as e:
            resultado["erro"] = str(e)
            resultado["sucesso"] = False
    
    thread = threading.Thread(target=executar, daemon=False)
    thread.start()
    thread.join(timeout=timeout_segundos + 5)  # +5s de margem
    
    if thread.is_alive():
        # Função excedeu timeout
        logger.critical(
            f"[Timeout] 🚨 TIMEOUT em '{nome_etapa}' (>{timeout_segundos}s) - Job: {job_id}. "
            f"Tentando fallback..."
        )
        
        if fallback_func:
            try:
                fallback_func()
                logger.warning(f"[Timeout] Fallback executado para '{nome_etapa}'")
            except Exception as e:
                logger.error(f"[Timeout] Fallback falhou: {e}")
        
        return {
            "sucesso": False,
            "erro": f"Timeout após {timeout_segundos}s em {nome_etapa}",
            "timeout": True
        }
    
    return resultado


# ===================================================================
# EXEMPLO DE USO NO FLUXO DE CONFERÊNCIA
# ===================================================================

"""
# Em main.py, inicializar watchdog junto com ThreadPoolManager:

watchdog = JobWatchdog(
    redis_client=redis_client,
    max_job_duration=300,   # 5 minutos máximo por job
    check_interval=30       # Verificar a cada 30 segundos
)
watchdog.iniciar()

# Em fluxo_conferencia.py, ao iniciar um job:

watchdog.registrar_job(numero_lt, worker_id=thread_id, tipo_job="conferencia")

try:
    # ... processamento do job ...
    
    # Ao final:
    watchdog.finalizar_job(numero_lt)
finally:
    watchdog.finalizar_job(numero_lt)

# Para usar TimeoutDetector em etapas críticas:

with TimeoutDetector("Buscando na tabela", max_seconds=15, job_id=numero_lt) as detector:
    row_locator = page.locator(f"tr:has-text('{numero_lt}')")
    expect(row_locator).to_be_visible(timeout=10000)
    
# Para usar com fallback:

resultado = criar_timeout_com_fallback(
    func=lambda: page.get_by_role("textbox", name="Expedidor").fill(carga.origem),
    timeout_segundos=10,
    fallback_func=lambda: page.reload(),
    nome_etapa="Preenchendo Expedidor",
    job_id=numero_lt
)
if not resultado["sucesso"]:
    logger.error(f"Erro ao preencher Expedidor: {resultado['erro']}")
"""
