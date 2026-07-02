# Process Definition Document (PDD): Monitoramento Ativo de Anomalias

## 1. Visão Geral e Escopo
Este documento define o modelo operacional *To-Be* para o processo de teste de gravação de *setupboxes*. O processo evoluiu de um diagnóstico exploratório passivo para um **monitoramento automatizado ativo**. O escopo abrange a ingestão contínua de logs da linha de fábrica, a aplicação de regras estatísticas para detecção de anomalias sistemáticas, o descarte de falsos positivos (ruídos) e o roteamento de alertas para intervenção autônoma ou revisão humana.

## 2. Atores e Responsabilidades
O processo é executado de forma colaborativa entre sistemas e operadores, divididos em duas raias (*Lanes*) operacionais:
* **Monitor Automatizado (Script Python):** Robô responsável pela ingestão de dados em janelas de tempo, cálculo de métricas preditivas, triagem de severidade e emissão autônoma de alertas de baixa/média criticidade.
* **Especialista de Linha (HITL - Human-in-the-Loop):** Operador humano responsável por julgar alertas de alta severidade ou de natureza ambígua, detendo a autoridade final para paralisar a linha de produção ou rejeitar o alerta formulado pelo monitor.

## 3. Regras de Ingestão e Processamento
* **RN01 - Ingestão por Janela:** O monitor não processa o histórico total de tentativas. Ele carrega os logs estritamente dentro de uma janela de tempo (ex: últimos 60 minutos ou fechamento de turno) para garantir baixa latência de detecção.
* **RN02 - Cálculo de Baseline:** O sistema avalia a volumetria de erros contra o comportamento normal da linha, calculando o *Cycle Time* médio e o *First-Pass Yield* (FPY) do lote atual.
* **RN03 - Filtro de Ruído:** Falhas pontuais e isoladas que não possuem uma dimensão dominante (ex: um erro atípico que não se repete) não geram alertas. O monitor descarta o dado ativando a rotina de *Descartar Ruído Isolado* e finaliza o fluxo sem notificar a equipa.

## 4. Matriz de Detecção e Severidade
Quando uma anomalia sistemática é confirmada, o monitor classifica a ocorrência para determinar o fluxo de roteamento:

### Severidade Baixa / Média (Ação Autônoma)
Anomalias de degradação previsível ou problemas de infraestrutura não críticos. O monitor emite o alerta diretamente para o canal configurado e sugere a ação padrão.
* **Drift de Cycle Time:** O tempo de teste estourou a mediana, subindo gradativamente.
* **Jig Crônico:** Um equipamento (jig) específico concentra uma taxa de falha muito superior aos demais.
* **Falha de Conexão:** Queda de acesso remoto na *API key* durante o *download* do *firmware*.

### Severidade Alta / Ambígua (Protocolo HITL)
Anomalias que afetam a integridade dos dados, bloqueiam a produção em massa ou envolvem comportamento inesperado das funcionalidades de *hardware* (Bluetooth, sintonizador de cabo, Wi-Fi). O monitor delega a decisão ao Especialista de Linha.
* **MAC Silencioso:** Tolerância zero. O monitor detecta o mesmo endereço MAC associado a diferentes números de série na linha.
* **Lote de Firmware Ruim:** Falha generalizada de uma versão de *firmware* específica derrubando o FPY de toda a linha.

## 5. Tratamento de Exceções e Intervenção Humana
O Especialista de Linha recebe o contexto da anomalia classificada como Alta/Ambígua e deve tomar uma decisão binária baseada na sugestão do monitor:
* **Caminho de Aprovação:** O humano confirma o achado do robô e executa a tarefa de *Autorizar Intervenção na Linha* (ex: paralisar a produção para investigar o provisionamento de MACs).
* **Caminho de Rejeição (Falso Positivo):** O humano identifica que o alerta do robô é infundado (ex: um erro de leitura já justificado no turno). Ele bloqueia a ação e aciona a tarefa de *Registrar Falso Positivo*. Este dado retroalimenta o sistema para calibrar os limiares futuros.

## 6. Runbook: Catálogo de Ações Sugeridas
| Gatilho do Monitor | Severidade | Ação Sugerida no Alerta |
| :--- | :--- | :--- |
| Falha massiva de *API Key* | Baixa | Renovar chave remota e reprocessar o lote no *jig*. |
| *Cycle Time* subindo | Média | Agendar calibração/inspeção do equipamento (*jig*). |
| *Jig* Crônico (Erro concentrado) | Média | Parar o equipamento específico e abrir ordem de manutenção. |
| Duplicidade de MAC em seriais distintos | Alta (HITL) | Paralisar a linha imediatamente e revisar sistema de provisionamento. |
| Falha crítica de *Firmware* | Alta (HITL) | Realizar *rollback* / bloquear a imagem na linha. |

## 7. Governança e Trilha de Auditoria
A regra fundamental do monitoramento ativo é a rastreabilidade total. O processo garante que não existam instâncias órfãs:
* Se o monitor age sozinho (Baixa/Média), o alerta e a evidência são logados.
* Se o humano autoriza a intervenção, o utilizador e a justificativa são logados.
* Se o humano rejeita o alerta como Falso Positivo, a recusa é logada.

Todos os fluxos de acionamento convergem obrigatoriamente para a rotina de **Gravar Trilha de Auditoria**, gerando um arquivo estruturado de fácil consulta para fins de *compliance* de qualidade.