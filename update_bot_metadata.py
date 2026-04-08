#!/usr/bin/env python3
"""
Script para actualizar metadata de bots en la base de datos.
Uso: python update_bot_metadata.py
"""

import os
import sys
from sqlalchemy import create_engine, text

# Configuración de la base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")

def update_bot_metadata(bot_id: str, metadata: dict):
    """Actualiza el metadata de un bot."""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # Merge metadata (preserva campos existentes)
            sql = text("""
                UPDATE gestion_whatsappbot
                SET metadata = COALESCE(metadata, '{}'::jsonb) || :metadata::jsonb,
                    updated_at = NOW()
                WHERE id = :bot_id
                RETURNING id, external_ref, metadata
            """)
            
            import json
            result = conn.execute(sql, {
                "bot_id": bot_id,
                "metadata": json.dumps(metadata)
            })
            conn.commit()
            
            row = result.fetchone()
            if row:
                print(f"✅ Bot actualizado: {row[1]} (ID: {row[0]})")
                print(f"📋 Metadata actual:")
                print(json.dumps(dict(row[2]), indent=2, ensure_ascii=False))
                return True
            else:
                print(f"❌ No se encontró el bot con ID: {bot_id}")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        engine.dispose()

def get_bot_by_assistant_id(assistant_id: str):
    """Obtiene un bot por su assistant_id."""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            sql = text("""
                SELECT id, external_ref, assistant_id, metadata
                FROM gestion_whatsappbot
                WHERE assistant_id = :assistant_id
            """)
            
            result = conn.execute(sql, {"assistant_id": assistant_id})
            row = result.fetchone()
            
            if row:
                import json
                print(f"🤖 Bot encontrado: {row[1]} (ID: {row[0]})")
                print(f"📋 Assistant ID: {row[2]}")
                print(f"📋 Metadata actual:")
                print(json.dumps(dict(row[3] or {}), indent=2, ensure_ascii=False))
                return row[0]  # Retorna el bot_id
            else:
                print(f"❌ No se encontró bot con assistant_id: {assistant_id}")
                return None
                
    finally:
        engine.dispose()

def main():
    """Función principal."""
    print("=" * 60)
    print("🤖 Actualización de Metadata de Bots")
    print("=" * 60)
    print()
    
    # Bot de BateriasYa
    assistant_id = "asst_svobnYajdAylQaM5Iqz8Dof3"
    
    print(f"Buscando bot con assistant_id: {assistant_id}")
    print()
    
    bot_id = get_bot_by_assistant_id(assistant_id)
    
    if not bot_id:
        print("\n❌ No se pudo encontrar el bot. Verifica el assistant_id.")
        return
    
    print("\n" + "=" * 60)
    print("📝 Configuración a aplicar:")
    print("=" * 60)
    
    metadata = {
        "horizon_api_token": "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO",
        "notification_target_whatsapp": "+56949472881",
        "allow_sucursal_fallback": True,
        "sucursal_phone_map": {
            "santiago": "+56949472881",
            "rm": "+56949472881",
            "región metropolitana": "+56949472881",
            "providencia": "+56949472881",
            "macul": "+56949472881",
            "la florida": "+56949472881",
            "las condes": "+56949472881",
        }
    }
    
    import json
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print()
    
    confirm = input("¿Deseas aplicar esta configuración? (s/n): ")
    
    if confirm.lower() in ['s', 'si', 'y', 'yes']:
        print("\n🔄 Actualizando metadata...")
        if update_bot_metadata(bot_id, metadata):
            print("\n✅ ¡Metadata actualizado exitosamente!")
            print("\n💡 Recuerda:")
            print("   1. Crear y aprobar el template en Twilio")
            print("   2. Agregar el twilio_template_sid una vez aprobado")
            print("   3. Reiniciar el servicio: sudo systemctl restart horizonai-whatsapp-bot")
        else:
            print("\n❌ Error al actualizar metadata")
    else:
        print("\n❌ Operación cancelada")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        sys.exit(0)
    
    main()
