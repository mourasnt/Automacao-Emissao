"""
Sistema de display de status em tempo real com atualização na mesma linha.
Apenas logs IMPORTANTES são mostrados, com um resumo sempre visível no rodapé.
"""
import threading
import time
import redis
from loguru import logger
from typing import Dict, Any
import sys


class StatusDisplay:
    """
    Gerencia display de status em tempo real.
    
    Status fica FIXO no rodapé da tela, sempre atualizado.
    Apenas logs IMPORTANTES são mostrados acima dele.
    """
    
    # ANSI codes para manipular cursor
    CLEAR_LINE = "\033[2K"
    MOVE_UP_4 = "\033[4A"
    CARRIAGE_RETURN = "\r"
    
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
        
        # Controle de primeira exibição
        self.primeira_exibicao = True
    
    def atualizar_threads(self, tipo_job: str, quantidade: int):
        """Atualiza quantidade de threads ativas de um tipo."""
        with self.lock:
            self.threads_status[tipo_job] = quantidade
    
    def _formatar_status(self) -> str:
        """Formata o box de status."""
        with self.lock:
            conf_threads = self.threads_status.get("conferencia", 0)
            emis_threads = self.threads_status.get("emissao", 0)
            conf_jobs = self.jobs_pending.get("conferencia", 0)
            emis_jobs = self.jobs_pending.get("emissao", 0)
        
        # Cores e formatação
        status_box = (
            f"\n"
            f"╔════════════════════════════════════════════════════════════╗\n"
            f"║ 👷 Conferência: {conf_threads} thread{'s' if conf_threads != 1 else ' ':<7}  │  👷 Emissão: {emis_threads} thread{'s' if emis_threads != 1 else ' ':<8}\n"
            f"║ 📦 Pendentes: {conf_jobs:5d} (conf)    │  {emis_jobs:5d} (emis)\n"
            f"╚════════════════════════════════════════════════════════════╝"
        )
        return status_box
    
    def _limpar_status_anterior(self):
        """Limpa o status anterior (4 linhas) do console."""
        try:
            # Move cursor 4 linhas para cima
            sys.stdout.write(self.MOVE_UP_4)
            # Limpa cada uma das 4 linhas
            for _ in range(4):
                sys.stdout.write(self.CLEAR_LINE)
                sys.stdout.write("\n")
            # Move de volta ao início do status
            sys.stdout.write(self.MOVE_UP_4)
            sys.stdout.flush()
        except Exception:
            # Se falhar (não suporta ANSI), apenas não faz nada
            pass
    
    def _monitorar_status(self):
        """
        Loop que atualiza o status periodicamente.
        Contém jobs pendentes e exibe resumo fixo no rodapé.
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
                
                # Exibe status
                if not self.primeira_exibicao:
                    self._limpar_status_anterior()
                else:
                    self.primeira_exibicao = False
                
                sys.stdout.write(self._formatar_status())
                sys.stdout.flush()
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Erro no monitor de status: {e}")
    
    def iniciar(self):
        """Inicia o display de status em background."""
        self.running = True
        # Exibe status inicial
        sys.stdout.write(self._formatar_status())
        sys.stdout.flush()
        
        # Inicia thread de atualização
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

