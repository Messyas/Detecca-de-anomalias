# Process Definition Document (PDD): Teste de Gravação de Setupbox
## 1. Objetivo
Mapear e documentar o processo atual (*as-is*) do teste de gravação (*flashing*) de *setupboxes* na linha de fábrica, visando o entendimento do processo e a identificação de anomalias sistêmicas antes de avançar para a automação.
## 2. Escopo
O processo documentado engloba desde a entrada da *setupbox* na estação de gravação (*jig*), passando pelo download do *firmware* via API remota, gravação de funcionalidades em sequência, testes de integridade por *checksum* MD5, até a classificação final da unidade (*disposition*).
## 3. Entradas
 * **Dados do Equipamento:** Modelo, SKU, Número de Série e Endereço MAC.
 * **Dados do Sistema:** *API key* remota e versão do *firmware*.
 * **Dados de Rastreabilidade:** Linha, estação, *jig*, operador e turno.
## 4. Saídas
 * **Resultado de Execução:** Log indicando se o MD5 conferiu (OK) para cada etapa gravada.
 * **Métricas de Desempenho:** Tempo de ciclo (*cycle time*) em segundos para cada etapa.
 * **Classificação Final (*Disposition*):** Atribuição do status final da unidade como PASS, REWORK ou SCRAP.
## 5. Regras de Negócio e Políticas
 * **RN01 - Política de Retrabalho (Rework):** Se uma tentativa de gravação falha, o mesmo número de série é regravado na linha, reaparecendo como tentativa 2 (*attempt = 2*).
 * **RN02 - Política de Sucata (Scrap):** Se a unidade submetida ao *rework* falhar de novo, ela deve ser classificada definitivamente como sucata (*scrap*).
 * **RN03 - Integridade de Identificação:** O endereço MAC e o Número de Série devem ser únicos. O reaproveitamento do mesmo número de série é legítimo apenas no *rework*. Um problema crítico (e silencioso) é encontrar o mesmo MAC associado a seriais diferentes.
 * **RN04 - Modelos Híbridos:** Os modelos diferem em suas funcionalidades, podendo incluir Bluetooth, sintonizador de cabo (varredura de canais) e variação de banda Wi-Fi (2.4 GHz ou 5 GHz).
## 6. Exceções e Eventos de Parada
 * **Paradas de Linha:** A linha possui uma tabela à parte de eventos de *downtime* (registrando linha, início, fim, duração e motivo) que afeta a disponibilidade geral e deve ter seus cruzamentos avaliados contra quedas de qualidade.
 * **Anomalias de Desempenho:** Testes lentos com *cycle time* estourado, seja em picos isolados ou subindo ao longo do tempo.
 * **Falhas de Conexão:** Acesso remoto falho onde a *API key* ou o *download* do *firmware* falham em uma janela de tempo específica.
## 7. Ponte para a Hiperautomação
A análise exploratória deste fluxo através do *dashboard* serve como etapa de descoberta de processo para embasar a automação. O entendimento profundo de onde e por quanto tempo as anomalias ocorrem (como um *jig* específico com falha crônica ou lote de *firmware* problemático) permitirá monitoramento contínuo e futuras intervenções sistêmicas.
