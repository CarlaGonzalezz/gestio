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
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user, current_user, login_required
)
from werkzeug.security import check_password_hash

from flask_cors import CORS
# ❌ QUITAR esta línea para evitar confusión:
# from google.cloud import firestore

# --- filtros Jinja -----------------------------------------------------------
from datetime import datetime, timezone, timedelta
import io, csv
from flask import Response

# .env
import os
import json  # <-- NUEVO
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
login_manager = LoginManager(app)
login_manager.login_view = "login"   # si no está logueado → /login
CORS(app)  # habilita CORS en todas las rutas
# ---------------------------------------------------------------------------

# --- inicializar Firebase ---------------------------------------------------
# En producción (Render) usamos FIREBASE_CREDENTIALS_JSON con el JSON completo.
# En desarrollo local seguimos aceptando SERVICE_ACCOUNT_FILE (o serviceAccountKey.json por defecto).
sa_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

if sa_json:
    try:
        cred_info = json.loads(sa_json)  # la variable contiene el JSON completo
    except json.JSONDecodeError as e:
        raise RuntimeError("FIREBASE_CREDENTIALS_JSON no es un JSON válido") from e
    cred = credentials.Certificate(cred_info)
else:
    # Desarrollo local: archivo en disco
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
                "nombre_lower": nombre.lower(),  
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


# ----- Buscar producto (por ID o por nombre_lower) -------------------------
@app.route("/api/buscar_producto")
def buscar_producto():
    """
    ?q=texto → busca primero por ID exacto (código), luego por nombre_lower que comience con q.
    Devuelve 404 si no encuentra.
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "query vacía"}), 400

    # 1) Por ID exacto (útil para código de barras)
    doc = db.collection("productos").document(q).get()
    if doc.exists:
        return jsonify(doc.to_dict() | {"id": doc.id})

    # 2) Por nombre_lower (prefijo)
    q_lower = q.lower()
    query = (
        db.collection("productos")
        .order_by("nombre_lower")
        .start_at([q_lower]).end_at([q_lower + "\uf8ff"])
        .limit(1)
        .stream()
    )
    for d in query:
        return jsonify(d.to_dict() | {"id": d.id})

    return jsonify({"error": "no encontrado"}), 404


# ----- Panel Web (HTML) -----------------------------------------------------
@app.route("/panel/productos")
@login_required
def panel_productos():
    """Muestra la tabla de productos usando la plantilla Jinja2."""
    docs = db.collection("productos").stream()
    productos = [doc.to_dict() | {"id": doc.id} for doc in docs]
    return render_template("productos.html", productos=productos)


# ----- Panel Producto Nuevo ------------------------------------------------
@app.route("/panel/productos/nuevo", methods=["GET", "POST"])
@login_required
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
@login_required
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
            "nombre_lower": nombre.lower(),
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
@login_required
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


# ----- Panel Dashboard -----------------------------------------------------
@app.route("/panel/dashboard")
@login_required
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


# ----- Panel Alertas -------------------------------------------------------
@app.route("/panel/alertas")
@login_required
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


# ----- Panel Caja ----------------------------------------------------------
@app.route("/panel/caja")
@login_required
def panel_caja():
    """Pantalla de punto de venta (POS)."""
    return render_template("caja.html")


# ---- Api Ventas -----------------------------------------------------------
@app.route("/api/ventas", methods=["POST"])
def registrar_venta():
    data  = request.get_json(force=True) or {}
    items = data.get("items", [])
    total = float(data.get("total") or 0)

    # Validación simple
    if not items:
        return jsonify({"error": "Carrito vacío"}), 400

    batch = db.batch()
    # Validar stock y preparar updates
    for it in items:
        ref = db.collection("productos").document(it["id"])
        snap = ref.get()
        if not snap.exists:
            return jsonify({"error": f"Producto {it['id']} no existe"}), 400
        sdata = snap.to_dict() or {}
        stock_actual = int(sdata.get("stock") or 0)
        cant = int(it.get("cantidad") or 0)
        if stock_actual < cant:
            return jsonify({"error": f"Stock insuficiente para {sdata.get('nombre','(sin nombre)')}"}), 400
        batch.update(ref, {"stock": stock_actual - cant})

    # Guardar la venta (opcional)
    venta_ref = db.collection("ventas").document()
    batch.set(venta_ref, {
        "items": items,
        "total": total,
        "ts": firestore.SERVER_TIMESTAMP,
    })

    # Ejecutar
    batch.commit()
    return jsonify({"ok": True})



# ------------------ Filtro de fecha para Jinja ------------------
@app.template_filter("fmtfecha")
def fmtfecha(value):
    """
    Convierte un Firestore Timestamp a 'dd/mm/yyyy hh:mm'.
    Si ya viene como datetime, lo formatea igual.
    """
    if not value:
        return ""
    try:
        dt = value.to_datetime()  # Firestore Timestamp
    except Exception:
        dt = value               # ya es datetime
    return dt.strftime("%d/%m/%Y %H:%M")


# ----- Listado de ventas (HTML) ---------------------------------------------
@app.route("/panel/ventas")
@login_required
def panel_ventas():
    f = request.args.get("from")  # 'YYYY-MM-DD'
    t = request.args.get("to")    # 'YYYY-MM-DD'

    q = db.collection("ventas")

    # Filtros por fecha (en UTC). 'ts' debe ser un datetime/timestamp guardado en la venta
    if f:
        dt_from = datetime.strptime(f, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        q = q.where("ts", ">=", dt_from)
    if t:
        # incluir el final del día 'to'
        dt_to = datetime.strptime(t, "%Y-%m-%d") + timedelta(days=1)
        dt_to = dt_to.replace(tzinfo=timezone.utc)
        q = q.where("ts", "<", dt_to)

    # Orden descendente por fecha
    q = q.order_by("ts", direction=firestore.Query.DESCENDING)

    ventas = []
    for d in q.stream():
        data = d.to_dict() or {}
        items = data.get("items", [])
        cant_items = sum(int(i.get("cantidad") or 0) for i in items)
        ventas.append({
            "id": d.id,
            "ts": data.get("ts"),
            "total": float(data.get("total") or 0),
            "items_count": cant_items,
        })

    return render_template("ventas.html", ventas=ventas, f=f or "", t=t or "")


# ----- Exportar ventas a CSV ------------------------------------------------
@app.route("/panel/ventas.csv")
@login_required
def export_ventas_csv():
    f = request.args.get("from")
    t = request.args.get("to")

    q = db.collection("ventas")
    if f:
        dt_from = datetime.strptime(f, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        q = q.where("ts", ">=", dt_from)
    if t:
        dt_to = datetime.strptime(t, "%Y-%m-%d") + timedelta(days=1)
        dt_to = dt_to.replace(tzinfo=timezone.utc)
        q = q.where("ts", "<", dt_to)
    q = q.order_by("ts", direction=firestore.Query.DESCENDING)

    rows = []
    rows.append(["id", "fecha", "items", "total"])
    for d in q.stream():
        data = d.to_dict() or {}
        items = data.get("items", [])
        cant = sum(int(i.get("cantidad") or 0) for i in items)
        fecha = data.get("ts")
        fecha_str = fecha.strftime("%Y-%m-%d %H:%M") if isinstance(fecha, datetime) else ""
        rows.append([d.id, fecha_str, cant, float(data.get("total") or 0)])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    csv_data = buf.getvalue()
    buf.close()

    return Response(
        csv_data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=ventas.csv"},
    )


# ------------------ Detalle de una venta ------------------------------------
@app.route("/panel/ventas/<venta_id>")
@login_required
def panel_venta_detalle(venta_id):
    """
    Muestra los ítems de una venta y su total.
    """
    snap = db.collection("ventas").document(venta_id).get()
    if not snap.exists:
        flash("Venta no encontrada.", "error")
        return redirect(url_for("panel_ventas"))

    venta = snap.to_dict() or {}
    venta["id"] = snap.id
    return render_template("venta_detalle.html", venta=venta)


# ----- Modelo de Usuario para Flask-Login -----------------------------------
class User(UserMixin):
    def __init__(self, doc_id, email, rol, activo=True):
        self.id = doc_id            # requerido por Flask-Login
        self.email = email
        self.rol = rol
        self.activo = activo

    @property
    def is_active(self):
        return bool(self.activo)

@login_manager.user_loader
def load_user(user_id: str):
    # user_id será el id del doc (usamos email como id en el script)
    doc = db.collection("usuarios").document(user_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    return User(doc.id, data.get("email",""), data.get("rol","user"), data.get("activo", True))


# ----- Rutas de Login/Logout --------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        doc = db.collection("usuarios").document(email).get()
        if not doc.exists:
            flash("Usuario no encontrado.", "error")
            return render_template("login.html"), 401

        data = doc.to_dict() or {}
        if not data.get("activo", True):
            flash("Usuario inactivo.", "error")
            return render_template("login.html"), 403

        if not check_password_hash(data.get("password_hash",""), password):
            flash("Credenciales inválidas.", "error")
            return render_template("login.html"), 401

        user = User(doc.id, data.get("email",""), data.get("rol","user"), data.get("activo",True))
        login_user(user)
        flash("Bienvenido/a.", "success")
        # redirige a donde intentaba entrar o al panel principal
        next_url = request.args.get("next") or url_for("panel_productos")
        return redirect(next_url)

    # GET
    return render_template("login.html")


@app.route("/logout")
def logout():
    logout_user()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("login"))

# ──────────────────────────────────
# Arranque
# ──────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)

