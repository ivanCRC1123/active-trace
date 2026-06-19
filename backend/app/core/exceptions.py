"""RESERVADO para C-02+ (handlers de error estandarizados).

Este módulo contendrá:
- Clases de excepción personalizadas del dominio.
- Handlers globales ``@app.exception_handler`` para traducción
  consistente a ``HTTPException`` con los códigos definidos en
  ``docs/ARQUITECTURA.md §3`` (400, 401, 403, 404, 422, 500, 502).

C-01 no implementa nada de esto.
"""
