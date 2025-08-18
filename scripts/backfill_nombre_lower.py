# scripts/backfill_nombre_lower.py
import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

docs = db.collection("productos").stream()
count = 0
for d in docs:
    data = d.to_dict() or {}
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        continue
    # si no tiene nombre_lower o está vacío, lo agregamos/actualizamos
    if data.get("nombre_lower") != nombre.lower():
        db.collection("productos").document(d.id).update({
            "nombre_lower": nombre.lower()
        })
        count += 1

print(f"Actualizados {count} documentos.")
