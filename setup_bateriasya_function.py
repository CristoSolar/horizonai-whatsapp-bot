"""
Script para configurar el asistente de BateriasYa con la función extract_hori_bateriasya_data.

Este script actualiza el asistente existente para agregar la definición de la función
que extrae datos del servicio y envía notificación a la sucursal correspondiente.
"""

# Configuración del asistente
ASSISTANT_ID = "asst_svobnYajdAylQaM5Iqz8Dof3"

# Definición de la función para el asistente
FUNCTION_DEFINITION = {
    "type": "function",
    "function": {
        "name": "extract_hori_bateriasya_data",
        "description": "Extrae desde el mensaje los datos del servicio y del vehículo (comuna, marca, modelo, año, combustible, start-stop) y, si el usuario ya acepta agendar, los datos del cliente.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "servicio": {
                    "type": "object",
                    "description": "Datos del servicio a domicilio.",
                    "properties": {
                        "comuna": {
                            "type": "string",
                            "description": "Comuna donde se requiere el servicio (RM o Curicó)."
                        }
                    },
                    "required": ["comuna"],
                    "additionalProperties": False
                },
                "vehiculo": {
                    "type": "object",
                    "description": "Datos mínimos para compatibilidad y cotización.",
                    "properties": {
                        "marca": {"type": "string"},
                        "modelo": {"type": "string"},
                        "anio": {
                            "type": "integer",
                            "minimum": 1950,
                            "maximum": 2100
                        },
                        "combustible": {
                            "type": "string",
                            "description": "Tipo de combustible.",
                            "enum": ["bencinero", "diésel"]
                        },
                        "start_stop": {
                            "type": "string",
                            "description": "¿Tiene sistema Start-Stop?",
                            "enum": ["si", "no", "desconocido"]
                        }
                    },
                    "required": ["marca", "modelo", "anio", "combustible", "start_stop"],
                    "additionalProperties": False
                },
                "cliente": {
                    "type": "object",
                    "description": "Se completa solo después de que el cliente acepta cotización/agendamiento.",
                    "properties": {
                        "nombre": {"type": "string"},
                        "apellido": {"type": "string"},
                        "rut": {
                            "type": "string",
                            "description": "RUT chileno (ej: 12.345.678-9 o 12345678-9)."
                        },
                        "direccion": {
                            "type": "string",
                            "description": "Dirección exacta."
                        },
                        "referencia": {
                            "type": "string",
                            "description": "Referencia para llegar."
                        },
                        "telefono": {"type": "string"},
                        "correo": {
                            "type": "string",
                            "format": "email"
                        }
                    },
                    "required": ["nombre", "apellido", "rut", "direccion", "referencia", "telefono", "correo"],
                    "additionalProperties": False
                },
                "estado_flujo": {
                    "type": "string",
                    "description": "Estado inferido del flujo de atención.",
                    "enum": ["pre_cotizacion", "cotizacion_enviada", "agendando", "agendado"]
                }
            },
            "required": ["servicio", "vehiculo", "cliente", "estado_flujo"],
            "additionalProperties": False
        }
    }
}

# Ejemplo de cómo actualizar el asistente vía API
def update_assistant_with_function():
    """
    Actualiza el asistente de OpenAI para agregar la función.
    
    Ejecutar desde Python con:
    ```
    from openai import OpenAI
    client = OpenAI()
    
    # Obtener herramientas actuales
    assistant = client.beta.assistants.retrieve(ASSISTANT_ID)
    current_tools = assistant.tools or []
    
    # Agregar la nueva función
    new_tools = current_tools + [FUNCTION_DEFINITION]
    
    # Actualizar asistente
    updated = client.beta.assistants.update(
        ASSISTANT_ID,
        tools=new_tools
    )
    
    print(f"Asistente actualizado: {updated.id}")
    print(f"Total de herramientas: {len(updated.tools)}")
    ```
    """
    pass

# Ejemplo de cómo actualizar vía curl
CURL_EXAMPLE = """
# Actualizar asistente con la función vía curl
curl -X POST https://api.openai.com/v1/assistants/{ASSISTANT_ID} \\
  -H "Authorization: Bearer $OPENAI_API_KEY" \\
  -H "Content-Type: application/json" \\
  -H "OpenAI-Beta: assistants=v2" \\
  -d '{
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "extract_hori_bateriasya_data",
          "description": "Extrae desde el mensaje los datos del servicio...",
          ...
        }
      }
    ]
  }'
""".format(ASSISTANT_ID=ASSISTANT_ID)

# Configuración del mapeo sucursal -> teléfono
SUCURSAL_PHONES = {
    "santiago": "+56978493528",
    "rm": "+56978493528",
    "región metropolitana": "+56978493528",
    "curico": "+56978493528",
    "curicó": "+56978493528",
}

# Notas de implementación
"""
IMPLEMENTACIÓN COMPLETA:

1. La función extract_hori_bateriasya_data ya está configurada en:
   - app/services/custom_functions_service.py
   
2. El flujo es:
   - Asistente OpenAI llama a extract_hori_bateriasya_data con los datos
   - CustomFunctionsService._handle_bateriasya_extraction() procesa los datos
   - Se determina la sucursal según la comuna
   - Se formatea un mensaje con los datos del servicio, vehículo y cliente
   - Se envía vía WhatsApp usando TwilioMessagingService al número de la sucursal
   
3. Para agregar nuevas sucursales, editar SUCURSAL_PHONES en:
   app/services/custom_functions_service.py (línea ~36)

4. El mensaje incluye:
   - Datos del servicio (comuna)
   - Datos del vehículo (marca, modelo, año, combustible, start-stop)
   - Datos del cliente (nombre, rut, teléfono, email, dirección, referencia)
   - Estado del flujo

5. Para probar:
   - Enviar un mensaje al bot que incluya todos los datos
   - El asistente extraerá automáticamente y llamará a la función
   - Se enviará la notificación a la sucursal correspondiente
"""

if __name__ == "__main__":
    print("Configuración del asistente BateriasYa")
    print(f"Assistant ID: {ASSISTANT_ID}")
    print(f"\nSucursales configuradas:")
    for sucursal, phone in SUCURSAL_PHONES.items():
        print(f"  - {sucursal}: {phone}")
    print("\nLa función extract_hori_bateriasya_data está lista para usar.")
    print("Asegúrate de que el asistente tenga esta función configurada en OpenAI.")
