"""
neg35 -- núcleo de inversão e restauração de negativos 35mm.

Pipeline em duas etapas independentes:

    Etapa 1 (determinística, local)  ->  inverter o negativo para positivo
    Etapa 2 (IA, opcional, remota)   ->  restaurar / limpar / ampliar

    from neg35 import pipeline
    res = pipeline.desenvolver("negativo.jpg", filme="gold200", auto=True)

Tudo aqui é float64 em espaço linear até a codificação final em sRGB.
"""

from . import adobe, core, curva, pipeline, post, synthetic

__all__ = ["adobe", "core", "curva", "pipeline", "post", "synthetic", "__version__"]

__version__ = "0.2.0"
