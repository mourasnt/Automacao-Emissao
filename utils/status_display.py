"""
Sistema de display de status em tempo real.
Status é atualizado a cada 5 segundos em uma linha única (funciona em Docker).
Apenas logs IMPORTANTES são mostrados.
"""
import threading
import time
import redis
from loguru import logger
from typing import Dict, Any
import sys


class StatusDisplay:
    """
    Gerencia display de status em tempo real na mesma linha.
    
    Usa carriage return (\r) para atualizar a mesma linha.
    Funciona em qualquer ambiente, incluindo Docker/Portainer.
    """
    
    def __init__(self, redis_client: redis.Redis, update_interval: int = 5):
        """
        Args:
            redis_client: Cliente Redis para contar jobs
            update_interval: Intervalo em segundos para atualizar status (padrão: 5s)
        """
        self.redis_client = redis_client
        self.update_interval = update_interval
        self.running = False
        self.monitor_thread = None
        
        # Estado compartilhado (thread-safe)
        self.lock = threading.Lock()
        self.threads_status: Dict[str, int] = {
            "conferencia": 0,
            "emissao": 0
        }
        self.jobs_pending: Dict[str, int] = {
            "conferencia": 0,
            "emissao": 0
        }
    
    def atualizar_threads(self, tipo_job: str, quantidade: int):
        """Atualiza quantidade de threads ativas de um tipo."""
        with self.lock:
            self.threads_status[tipo_job] = quantidade
    
    def _formatar_status_linha(self) -> str:
        """Formata o status em UMA ÚNICA linha (para atualizar com \r)."""
        with self.lock:
            conf_threads = self.threads_status.get("conferencia", 0)
            emis_threads = self.threads_status.get("emissao", 0)
            conf_jobs = self.jobs_pending.get("conferencia", 0)
            emis_jobs = self.jobs_pending.get("emissao", 0)
        
        # Uma linha única, comprimento fixo, fácil de sobrescrever
        linha = (
            f"[STATUS] Conf: {conf_threads}🧵 ({conf_jobs:3d}📦) | "
            f"Emis: {emis_threads}🧵 ({emis_jobs:3d}📦)                    "
        )
        return linha
    
    def _formatar_status_caixa(self) -> str:
        """Formata o status em forma de caixa (para exibição estática)."""
        with self.lock:
            conf_threads = self.threads_status.get("conferencia", 0)
            emis_threads = self.threads_status.get("emissao", 0)
            conf_jobs = self.jobs_pending.get("conferencia", 0)
            emis_jobs = self.jobs_pending.get("emissao", 0)
        
        status_box = (
            f"\n"
            f"╔════════════════════════════════════════════════════════════╗\n"
            f"║ 👷 Conferência: {conf_threads} thread{'s' if conf_threads != 1 else ' ':<7}  │  👷 Emissão: {emis_threads} thread{'s' if emis_threads != 1 else ' ':<8}\n"
            f"║ 📦 Pendentes: {conf_jobs:5d} (conf)    │  {emis_jobs:5d} (emis)\n"
            f"╚════════════════════════════════════════════════════════════╝\n"
        )
        return status_box
    
    def _monitorar_status(self):
        """
        Loop que atualiza o status periodicamente na mesma linha.
        Para Docker/Portainer, usa \r (carriage return) ao invés de ANSI codes.
        """
        while self.running:
            try:
                # Atualiza contadores de jobs
                with self.lock:
                    try:
                        self.jobs_pending["conferencia"] = self.redis_client.llen("fila:conferencia")
                        self.jobs_pending["emissao"] = self.redis_client.llen("fila:emissao")
                    except Exception as e:
                        logger.error(f"Erro ao contar jobs: {e}")
                
                # Escreve status na mesma linha usando \r (carriage return)
                # Isso funciona em qualquer terminal, incluindo Docker
                linha_status = self._formatar_status_linha()
                sys.stderr.write(f"\r{linha_status}")
                sys.stderr.flush()
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Erro no monitor de status: {e}")
    
    def iniciar(self):
        """Inicia o display de status em background."""
        self.running = True
        
        # Exibe status inicial em forma de caixa
        sys.stderr.write(self._formatar_status_caixa())
        sys.stderr.flush()
        
        # Inicia thread de atualização (usa stderr para não interferir com stdout)
        self.monitor_thread = threading.Thread(
            target=self._monitorar_status,
            daemon=True,
            name="StatusDisplay"
        )
        self.monitor_thread.start()
        logger.info("Status display iniciado")
    
    def parar(self):
        """Para o display de status."""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        # Limpa a linha de status final
        sys.stderr.write("\r" + " " * 100 + "\r")
        sys.stderr.flush()
        logger.info("Status display parado")
    
    def get_resumo_json(self) -> Dict[str, Any]:
        """Retorna resumo em formato JSON (útil para APIs)."""
        with self.lock:
            return {
                "threads": self.threads_status.copy(),
                "jobs_pendentes": self.jobs_pending.copy(),
                "total_threads": sum(self.threads_status.values()),
                "total_jobs": sum(self.jobs_pending.values())
            }


