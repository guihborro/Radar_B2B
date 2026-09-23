"""FinIntegra — sistema de prospecção outbound B2B.

Pipeline (Fase 2):
    sourcing -> enrichment -> validation -> routing -> messaging -> sending

Cada camada externa (provedor de dados, verificador, LLM, envio) vive atrás de
uma interface abstrata e é selecionada por config/config.yaml. Os defaults
("mock"/"dry_run") rodam sem serviço pago e sem enviar nada.
"""

__version__ = "0.2.0"  # 0.x = Fase 2
