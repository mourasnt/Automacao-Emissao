# ThreadPoolManager - Gerenciador de Thread Pool Dinâmico

## 📋 Visão Geral

O **ThreadPoolManager** é um novo sistema de gerenciamento de workers que **escala dinamicamente** o número de threads baseado na quantidade de jobs pendentes nas filas Redis.

### 🎯 Problema Resolvido

**Antes**: Sistema com 2 threads fixas (conferência + emissão)
- Não acompanhava picos de volume
- Deixava jobs aguardando desnecessariamente
- Subutilizava recursos em períodos de baixa demanda

**Depois**: Sistema com threads dinâmicas
- Cria automaticamente novas threads quando jobs aumentam
- Finaliza threads quando jobs diminuem
- Distribuição inteligente: 1 thread por 50 jobs

---

## ⚙️ Arquitetura

### Fórmula de Escaling

```
threads_necessárias = ceil(jobs_pendentes / 50)
```

**Exemplos**:
| Jobs | Threads |
|------|---------|
| 1-50 | 1 |
| 51-100 | 2 |
| 101-150 | 3 |
| 322 | 7 |

### Componentes Principais

#### 1. **ThreadPoolManager** (`utils/fluxo_utils.py`)
- Classe responsável por gerenciar o pool dinâmico
- Monitora filas Redis periodicamente
- Cria/finaliza threads conforme necessário
- Thread-safe com locks

#### 2. **Monitor de Rebalanceamento** (`utils/fluxo_utils.py`)
- Thread daemon que verifica a cada 60s se há mudanças
- Calcula threads necessárias
- Executa rebalanceamento automático

#### 3. **Main Refatorado** (`main.py`)
- Inicializa ThreadPoolManager
- Passa configurações e credenciais
- Aguarda encerramento gracioso

---

## 🚀 Como Funciona

### Inicialização

```python
# main.py
pool_manager = ThreadPoolManager(
    redis_client=redis_client,
    config=config,
    ejecutor_function=executar_fluxo,
    usuario=USUARIO,
    senha=SENHA,
    rebalance_interval=60,        # Verifica a cada 60s
    max_threads_per_type=10,      # Máx 10 por tipo
    max_total_threads=20,         # Máx 20 no total
)

pool_manager.iniciar()
pool_manager.aguardar_encerramento()
```

### Ciclo de Rebalanceamento (a cada 60s)

1. **Verificação**
   ```python
   jobs_conferencia = redis_client.llen("fila:conferencia")  # ex: 322
   jobs_emissao = redis_client.llen("fila:emissao")          # ex: 3
   ```

2. **Cálculo**
   ```python
   threads_conf = ceil(322 / 50) = 7  threads
   threads_emis = ceil(3 / 50) = 1 thread
   ```

3. **Ação**
   - Se necessárias > atuais: **cria** novas threads
   - Se necessárias < atuais: **log de aviso** (threads finalizam naturalmente)
   - Se necessárias = atuais: **sem mudanças**

### Logs de Rebalanceamento

```log
[16:30:00] [ESCALAR] conferencia: 322 jobs → criando 5 thread(s) (total: 2 → 7)
[16:30:01] [INFO] Thread 'Worker-conferencia-3' iniciada. Total de conferencia: 3
[16:30:02] [INFO] Thread 'Worker-conferencia-4' iniciada. Total de conferencia: 4
[16:30:03] [INFO] Thread 'Worker-conferencia-5' iniciada. Total de conferencia: 5
[16:30:04] [INFO] Thread 'Worker-conferencia-6' iniciada. Total de conferencia: 6
[16:30:05] [INFO] Thread 'Worker-conferencia-7' iniciada. Total de conferencia: 7
[16:30:05] [INFO] Thread 'Worker-emissao-1' iniciada. Total de emissao: 1

[16:40:00] [EQUILIBRIO] conferencia: 150 jobs → 7 thread(s) ativa(s). Sem mudanças.
[16:40:00] [EQUILIBRIO] emissao: 1 jobs → 1 thread(s) ativa(s). Sem mudanças.

[17:00:00] [REDUZIR] conferencia: 20 jobs → 6 thread(s) em excesso (total: 7 → 1). Threads finalizarão quando jobs terminarem.
```

---

## 🔧 Configuração

### Variáveis de Ambiente Necessárias (já existentes)
```bash
RPA_USUARIO=35036755820
RPA_SENHA=120487@Ka
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

### Parâmetros do ThreadPoolManager

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `rebalance_interval` | 60s | Intervalo para verificar jobs e rebalancear |
| `max_threads_per_type` | 10 | Máximo de threads por tipo (conf/emis) |
| `max_total_threads` | 20 | Máximo total de threads (prevenção de sobrecarga) |
| `ejecutor_function` | `executar_fluxo` | Função que executa os workers |

---

## 📊 Fluxo Completo (Exemplo Real)

### Cenário: 322 jobs de conferência + 3 de emissão

```
T=0s (Início)
├─ Poller detecta 322 jobs de conferência
├─ Poller detecta 3 jobs de emissão
├─ ThreadPoolManager inicia
└─ Calcula: ceil(322/50)=7 threads conferência, ceil(3/50)=1 thread emissão

T=0-5s (Criação de Threads)
├─ [ESCALAR] conferencia: 322 jobs → criando 2 thread(s) (total: 0 → 2)
├─ [INFO] Thread 'Worker-conferencia-1' iniciada
├─ [INFO] Thread 'Worker-conferencia-2' iniciada
├─ [ESCALAR] conferencia: 322 jobs → criando 5 thread(s) (total: 2 → 7)
├─ [INFO] Thread 'Worker-conferencia-3' até 'Worker-conferencia-7' iniciadas
├─ [ESCALAR] emissao: 3 jobs → criando 1 thread(s) (total: 0 → 1)
└─ [INFO] Thread 'Worker-emissao-1' iniciada

T=60s (Primeira verificação de rebalanceamento)
├─ blpop reduz jobs conforme workers completam
├─ Exemplo: 150 jobs conferência restantes
├─ ceil(150/50) = 3 threads necessárias
└─ [REDUZIR] conferencia: 150 jobs → 4 thread(s) em excesso

T=300s (Quando workers completam todos os jobs)
├─ Redis filas vazias: llen("fila:conferencia") = 0
├─ ThreadPoolManager calcula: ceil(0/50) = 0 threads
└─ [REDUZIR] Threads finalizarão naturalmente (daemon)
```

---

## 🛡️ Segurança e Limitações

### Limites de Proteção

1. **Máximo por tipo**: 10 threads (conferência + emissão) = até 20 threads
   - Previne esgotamento de memória
   - Cada thread = 1 instância Playwright (browser + contexto)

2. **Total máximo**: 20 threads
   - Dobra de segurança
   - Evita DoS de recursos

3. **Graceful Shutdown**
   - Threads daemon morrem com a aplicação
   - Jobs em progresso completam antes de finalizarem
   - `pool_manager.parar()` sinaliza encerramento

### Thread-Safety

```python
self.lock = threading.Lock()  # Protege acesso a self.threads
```
- Operações de leitura/escrita em dicts de threads são sincronizadas
- Evita race conditions

---

## 🐛 Troubleshooting

### Threads não estão escalando?

1. **Verificar Redis**
   ```bash
   redis-cli LLEN fila:conferencia  # Deve retornar número > 0
   redis-cli LLEN fila:emissao
   ```

2. **Verificar logs**
   ```bash
   tail -f logs/main_rpa.log | grep "ESCALAR\|REDUZIR"
   ```

3. **Verificar limites**
   - Atingiu `max_threads_per_type`? Aumentar em `main.py`
   - Atingiu `max_total_threads`? Aumentar limite total

### Muitas threads criadas?

- Reduza `max_threads_per_type` em `main.py` (padrão: 10)
- Aumente divisor de jobs (ex: 100 ao invés de 50)

```python
# Em ThreadPoolManager.calcular_threads_necessarias():
threads_necessarias = ceil(jobs_pendentes / 100)  # Invés de 50
```

### Threads morrendo frequentemente?

- Verificar se há erros de login em `logs/main_rpa.log`
- Validar credenciais RPA_USUARIO/RPA_SENHA
- Verificar conexão Playwright/browser

---

## 📈 Monitoramento

### Métricas a Acompanhar

```bash
# Jobs pendentes
redis-cli LLEN fila:conferencia
redis-cli LLEN fila:emissao

# Threads ativas (via logs)
grep "Thread.*iniciada\|em execução" logs/main_rpa.log

# Taxa de rebalanceamento
grep "ESCALAR\|REDUZIR\|EQUILIBRIO" logs/main_rpa.log
```

### KPIs Recomendados

| KPI | Ótimo | Aceitável | Crítico |
|-----|--------|-----------|---------|
| Jobs/Thread | ~50 | ~100 | >200 |
| Taxa de conclusão | >30/min | >20/min | <10/min |
| Threads ativas | =ceil(jobs/50) | ≤max | >max |

---

## 🔄 Ciclo de Vida de uma Thread

```
[Criação] → [Início] → [executar_fluxo] 
  ↓          ↓          ↓
Novo        viva       blpop (aguarda job)
            
[Job recebido] → [RPA executa] → [Resultado enviado]
     ↓               ↓                ↓
blpop retorna   Page + Config      redis.rpush()
  
[Loop continua ou finaliza]
     ↓
Sem jobs + timeout = thread morre (daemon)
```

---

## 📝 Próximas Melhorias (Roadmap)

- [ ] Persistência de métricas em Redis (tempo de rebalanceamento)
- [ ] Dashboard de monitoramento em tempo real
- [ ] Alertas customizáveis (ex: >15 threads ativas)
- [ ] Ajuste automático de divisor (aprendizado do histórico)
- [ ] Suporte a múltiplas máquinas (workers distribuídos)

---

## 📚 Referências

- **Arquivo principal**: [main.py](main.py)
- **Classe ThreadPoolManager**: [utils/fluxo_utils.py](utils/fluxo_utils.py#L380)
- **Executores de thread**: [utils/fluxo_utils.py:executar_fluxo](utils/fluxo_utils.py) (antiga localização em main.py)
- **Poller**: [poller.py](poller.py) (alimenta as filas)
- **Writer**: [writer.py](writer.py) (consume resultados)
