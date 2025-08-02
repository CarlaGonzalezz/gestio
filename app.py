# --- imports ---------------------------------------------------------------
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_cors import CORS

# .env
import os
from dotenv import load_dotenv

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore
# ---------------------------------------------------------------------------

# Cargar variables de entorno desde .env
load_dotenv()

# --- inicializar Flask ------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")  # ahora desde .env
CORS(app)  # habilita CORS en todas las rutas
# ---------------------------------------------------------------------------

# --- inicializar Firebase ---------------------------------------------------
# El archivo serviceAccountKey.json debe estar en la misma carpeta
# (o indicar la ruta en SERVICE_ACCOUNT_FILE dentro de .env)
service_account_path = os.getenv("SERVICE_ACCOUNT_FILE", "serviceAccountKey.json")
cred = credentials.Certificate(service_account_path)
firebase_admin.initialize_app(cred)
db = firestore.client()
# ---------------------------------------------------------------------------

# ──────────────────────────────────
# Rutas
# ──────────────────────────────────

@app.route("/")
def home():
    return "Gestio – Panel Web (Flask)"


# ----- API JSON + creación (programática) -----------------------------------
@app.route("/api/productos", methods=["GET", "POST"])
def productos():
    """
    GET  → Devuelve todos los documentos de la colección 'productos' en JSON.
    POST → Crea un nuevo documento y redirige al panel.
        (pensado para uso programático; el alta vía formulario está en /panel/productos/nuevo)
    """
    if request.method == "POST":
        try:
            nombre = (request.form.get("nombre") or "").strip()
            precio = float(request.form.get("precio", 0) or 0)
            stock  = int(request.form.get("stock", 0) or 0)

            db.collection("productos").add({
                "nombre": nombre,
                "precio": precio,
                "stock":  stock
            })
            # si viene desde un form web, redirigimos al panel
            return redirect(url_for("panel_productos"))
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # --- GET ---
    docs = db.collection("productos").stream()
    productos = [doc.to_dict() | {"id": doc.id} for doc in docs]
    return jsonify(productos)


# ----- Panel Web (HTML) -----------------------------------------------------
@app.route("/panel/productos")
def panel_productos():
    """Muestra la tabla de productos usando la plantilla Jinja2."""
    docs = db.collection("productos").stream()
    productos = [doc.to_dict() | {"id": doc.id} for doc in docs]
    return render_template("productos.html", productos=productos)


@app.route("/panel/productos/nuevo", methods=["GET", "POST"])
def nuevo_producto_form():
    """Muestra el formulario y guarda el producto nuevo con validación y mensajes flash."""
    if request.method == "POST":
        nombre = (request.form.get("nombre") or "").strip()
        precio_raw = request.form.get("precio")
        stock_raw  = request.form.get("stock")

        errores = []

        if not nombre:
            errores.append("El nombre es obligatorio.")

        try:
            precio = float(precio_raw)
            if precio < 0:
                errores.append("El precio no puede ser negativo.")
        except (TypeError, ValueError):
            errores.append("El precio debe ser un número válido.")

        try:
            stock = int(stock_raw)
            if stock < 0:
                errores.append("El stock no puede ser negativo.")
        except (TypeError, ValueError):
            errores.append("El stock debe ser un número entero válido.")

        if errores:
            for e in errores:
                flash(e, "error")
            return render_template(
                "producto_form.html",
                nombre=nombre,
                precio=precio_raw,
                stock=stock_raw
            ), 400

        # Crear documento en Firestore
        db.collection("productos").add({
            "nombre": nombre,
            "precio": precio,
            "stock":  stock
        })

        flash("Producto creado correctamente.", "success")
        return redirect(url_for("panel_productos"))

    # GET -> muestro el formulario
    return render_template("producto_form.html")


# ----- Editar producto (HTML + POST) ----------------------------------------
@app.route("/panel/productos/<doc_id>/editar", methods=["GET", "POST"])
def editar_producto_form(doc_id):
    """Mostrar el form precargado y actualizar el documento."""
    doc_ref = db.collection("productos").document(doc_id)

    if request.method == "POST":
        # Validación básica
        nombre = (request.form.get("nombre") or "").strip()
        precio_raw = request.form.get("precio")
        stock_raw  = request.form.get("stock")

        errores = []
        if not nombre:
            errores.append("El nombre es obligatorio.")
        try:
            precio = float(precio_raw)
            if precio < 0:
                errores.append("El precio no puede ser negativo.")
        except (TypeError, ValueError):
            errores.append("El precio debe ser un número válido.")
        try:
            stock = int(stock_raw)
            if stock < 0:
                errores.append("El stock no puede ser un entero válido.")
        except (TypeError, ValueError):
            errores.append("El stock debe ser un entero válido.")

        if errores:
            for e in errores:
                flash(e, "error")
            # Volver a mostrar el form conservando valores
            return render_template(
                "producto_form.html",
                editar=True,
                doc_id=doc_id,
                nombre=nombre,
                precio=precio_raw,
                stock=stock_raw,
            ), 400

        # Actualizar en Firestore
        doc_ref.update({
            "nombre": nombre,
            "precio": precio,
            "stock":  stock,
        })
        flash("Producto actualizado.", "success")
        return redirect(url_for("panel_productos"))

    # GET → traer datos y mostrar form
    doc = doc_ref.get()
    if not doc.exists:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("panel_productos"))

    data = doc.to_dict()
    return render_template(
        "producto_form.html",
        editar=True,
        doc_id=doc_id,
        nombre=data.get("nombre", ""),
        precio=data.get("precio", ""),
        stock=data.get("stock", ""),
    )


# ----- Eliminar producto (POST) ---------------------------------------------
@app.route("/panel/productos/<doc_id>/eliminar", methods=["POST"])
def eliminar_producto(doc_id):
    """Elimina el documento y vuelve al listado."""
    try:
        doc_ref = db.collection("productos").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists:
            flash("Producto no encontrado.", "error")
        else:
            doc_ref.delete()
            flash("Producto eliminado.", "success")
    except Exception as e:
        flash(f"Ocurrió un error al eliminar: {e}", "error")

    return redirect(url_for("panel_productos"))


@app.route("/panel/dashboard")
def panel_dashboard():
    """Métricas simples del inventario."""
    UMBRAL = int(os.getenv("STOCK_THRESHOLD", 5))  # ahora configurable por .env

    docs = db.collection("productos").stream()
    total_productos = 0
    bajo_stock_total = 0
    valor_inventario = 0.0
    candidatos_bajo_stock = []

    for doc in docs:
        d = doc.to_dict() or {}
        total_productos += 1
        nombre = d.get("nombre", "")
        try:
            precio = float(d.get("precio") or 0)
            stock = int(d.get("stock") or 0)
        except (TypeError, ValueError):
            precio, stock = 0.0, 0

        valor_inventario += precio * stock

        if stock < UMBRAL:
            bajo_stock_total += 1
            candidatos_bajo_stock.append({"nombre": nombre, "stock": stock})

    top_bajo_stock = sorted(candidatos_bajo_stock, key=lambda x: x["stock"])[:5]

    return render_template(
        "dashboard.html",
        total_productos=total_productos,
        bajo_stock=bajo_stock_total,          # ahora cuenta todos, no solo el top5
        valor_inventario=round(valor_inventario, 2),
        top_bajo_stock=top_bajo_stock,
        umbral=UMBRAL,
    )


@app.route("/panel/alertas")
def panel_alertas():
    """Listado de productos con stock por debajo del umbral."""
    UMBRAL = int(os.getenv("STOCK_THRESHOLD", 5))
    # Consulta Firestore: stock < UMBRAL, ordenado ascendente
    query = (
        db.collection("productos")
        .where("stock", "<", UMBRAL)
        .order_by("stock")
        .stream()
    )
    items = []
    for doc in query:
        d = doc.to_dict() or {}
        items.append({
            "id": doc.id,
            "nombre": d.get("nombre", ""),
            "stock": int(d.get("stock") or 0),
        })

    return render_template("alertas.html", items=items, umbral=UMBRAL)

# ──────────────────────────────────
# Arranque
# ──────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)

