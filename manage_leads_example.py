"""
Script de ejemplo para gestionar leads de BateriasYa en Horizon Manager.

Muestra cómo:
- Crear un lead
- Consultar un lead por ID
- Actualizar el estado de un lead
- Recuperar el ID del lead desde Redis por número de teléfono
"""

import requests
import redis

# Configuración
HORIZON_API_BASE = "https://api.horizonai.cl"
HORIZON_API_TOKEN = "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO"
REDIS_URL = "redis://localhost:6379/0"  # Ajustar según tu configuración

# Headers para las peticiones
HEADERS = {
    "Authorization": f"Bearer {HORIZON_API_TOKEN}",
    "Content-Type": "application/json",
}


def create_lead(nombre, correo, telefono, mensaje, procedencia="whatsapp_bateriasya"):
    """Crear un nuevo lead en Horizon Manager."""
    
    url = f"{HORIZON_API_BASE}/api/leads/"
    payload = {
        "procedencia": procedencia,
        "nombre": nombre,
        "correo": correo,
        "telefono": telefono,
        "mensaje": mensaje,
    }
    
    try:
        response = requests.post(url, headers=HEADERS, json=payload, timeout=10)
        response.raise_for_status()
        lead_data = response.json()
        print(f"✅ Lead creado exitosamente: ID={lead_data.get('id')}")
        return lead_data
    except requests.exceptions.RequestException as e:
        print(f"❌ Error creando lead: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None


def get_lead(lead_id):
    """Obtener información de un lead por su ID."""
    
    url = f"{HORIZON_API_BASE}/api/leads/{lead_id}/"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        lead_data = response.json()
        print(f"✅ Lead obtenido: {lead_data.get('nombre')} - {lead_data.get('procedencia')}")
        return lead_data
    except requests.exceptions.RequestException as e:
        print(f"❌ Error obteniendo lead: {e}")
        return None


def update_lead(lead_id, **updates):
    """Actualizar un lead existente."""
    
    url = f"{HORIZON_API_BASE}/api/leads/{lead_id}/"
    
    try:
        response = requests.patch(url, headers=HEADERS, json=updates, timeout=10)
        response.raise_for_status()
        lead_data = response.json()
        print(f"✅ Lead actualizado: ID={lead_id}")
        return lead_data
    except requests.exceptions.RequestException as e:
        print(f"❌ Error actualizando lead: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None


def get_lead_id_from_redis(phone_number):
    """Recuperar el ID del lead desde Redis usando el número de teléfono."""
    
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        
        # Limpiar el número de teléfono
        clean_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "")
        key = f"lead_id:{clean_phone}"
        
        lead_id = r.get(key)
        
        if lead_id:
            print(f"✅ Lead ID encontrado en Redis: {lead_id} para {phone_number}")
            return int(lead_id)
        else:
            print(f"❌ No se encontró lead ID para {phone_number}")
            return None
            
    except Exception as e:
        print(f"❌ Error conectando a Redis: {e}")
        return None


def save_lead_id_to_redis(phone_number, lead_id):
    """Guardar el ID del lead en Redis."""
    
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        
        clean_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "")
        key = f"lead_id:{clean_phone}"
        
        # Guardar con 30 días de expiración
        r.setex(key, 2592000, str(lead_id))
        print(f"✅ Lead ID {lead_id} guardado en Redis para {phone_number}")
        return True
        
    except Exception as e:
        print(f"❌ Error guardando en Redis: {e}")
        return False


# Ejemplos de uso
if __name__ == "__main__":
    print("=" * 60)
    print("EJEMPLOS DE USO - Gestión de Leads BateriasYa")
    print("=" * 60)
    
    # Ejemplo 1: Crear un lead
    print("\n1️⃣ Crear un nuevo lead")
    print("-" * 60)
    lead = create_lead(
        nombre="Juan Pérez",
        correo="juan.perez@example.com",
        telefono="+56912345678",
        mensaje="Vehículo: Toyota Corolla 2018 - Combustible: bencinero, Start-Stop: no. Servicio en: La Florida. Dirección: Av. Principal 123, Ref: Edificio azul. Estado: agendando"
    )
    
    if lead:
        lead_id = lead.get("id")
        
        # Guardar en Redis
        print("\n2️⃣ Guardar lead ID en Redis")
        print("-" * 60)
        save_lead_id_to_redis("+56912345678", lead_id)
        
        # Recuperar desde Redis
        print("\n3️⃣ Recuperar lead ID desde Redis")
        print("-" * 60)
        recovered_id = get_lead_id_from_redis("+56912345678")
        
        # Consultar el lead
        print("\n4️⃣ Consultar lead por ID")
        print("-" * 60)
        get_lead(lead_id)
        
        # Actualizar el lead
        print("\n5️⃣ Actualizar estado del lead")
        print("-" * 60)
        update_lead(
            lead_id,
            mensaje="[ACTUALIZADO] Cliente confirmó agendamiento para mañana 10:00. " + lead.get("mensaje", "")
        )
    
    print("\n" + "=" * 60)
    print("Ejemplos completados")
    print("=" * 60)


# Función helper para usar en el código del bot
def update_lead_status_by_phone(phone_number, new_status_message):
    """
    Actualizar el estado de un lead usando el número de teléfono.
    
    Útil para actualizar el lead cuando el cliente avanza en el flujo.
    """
    
    # Recuperar lead ID desde Redis
    lead_id = get_lead_id_from_redis(phone_number)
    
    if not lead_id:
        print(f"No se puede actualizar: no hay lead registrado para {phone_number}")
        return False
    
    # Obtener lead actual
    lead = get_lead(lead_id)
    
    if not lead:
        return False
    
    # Actualizar el mensaje agregando el nuevo estado
    current_message = lead.get("mensaje", "")
    updated_message = f"{current_message}\n[{new_status_message}]"
    
    # Actualizar lead
    result = update_lead(lead_id, mensaje=updated_message)
    
    return result is not None


# Ejemplo de uso en el bot
"""
# Cuando el cliente confirma el agendamiento:
update_lead_status_by_phone(
    "+56912345678",
    "Cliente confirmó servicio para 2025-11-04 10:00"
)

# Cuando se completa el servicio:
update_lead_status_by_phone(
    "+56912345678",
    "Servicio completado exitosamente"
)
"""
