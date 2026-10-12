"""
neg35 -- núcleo de inversão e restauração de negativos 35mm.

Pipeline em duas etapas independentes:

    Etapa 1 (determinística, local)  ->  inverter o negativo para positivo
    Etapa 2 (IA, opcional, remota)   ->  restaurar / limpar / ampliar

    from neg35 import pipeline
    res = pipeline.desenvolver("negativo.jpg", filme="gold200", auto=True)

Tudo aqui é float64 em espaço linear até a codificação final em sRGB.
"""

from . import core, post, pipeline, synthetic

__all__ = ["core", "post", "pipeline", "synthetic", "__version__"]

__version__ = "0.1.0"
