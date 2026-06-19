"""RESERVADO para C-02 (multi-tenancy — resolución y aislamiento de tenant).

Este módulo contendrá:
- La dependency ``get_tenant`` que extrae el ``tenant_id`` del JWT.
- Filtros automáticos de scope de tenant para repositories.
- Lógica de resolución de tenant por subdominio / sesión.

C-01 no implementa nada de esto.
"""
