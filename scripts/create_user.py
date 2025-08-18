# scripts/create_user.py
import firebase_admin
from firebase_admin import credentials, firestore
from werkzeug.security import generate_password_hash

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def create_user(email: str, password: str, rol="admin"):
    doc = {
        "email": email.strip().lower(),
        "password_hash": generate_password_hash(password),
        "rol": rol,
        "activo": True,
    }
    # doc id = email para lookup directo (puedes usar auto-id si prefieres)
    db.collection("usuarios").document(doc["email"]).set(doc)
    print("Usuario creado:", doc["email"])

if __name__ == "__main__":
    # Cambia por tus credenciales iniciales
    create_user("admin@gestio.local", "admin123", rol="admin")
