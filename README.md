@"
# Gestio – Panel Web (Flask + Firebase)

## Requisitos
- Python 3.10+
- Firebase (Firestore y service account)

## Configuración
1. Crear y activar venv:
   - Windows PowerShell: `python -m venv venv && .\venv\Scripts\activate`
2. Instalar dependencias: `pip install -r requirements.txt`
3. Configurar variables de entorno:
   - Copiar `.env.example` a `.env` y completar valores.
   - Colocar `serviceAccountKey.json` en la raíz (no subir a GitHub).
4. Ejecutar: `python app.py` y abrir http://127.0.0.1:5000

## Funcionalidad actual
- CRUD de productos (crear, editar, eliminar).
- Dashboard con métricas simples.
- Alertas de bajo stock.
"@ | Out-File -Encoding utf8 README.md
