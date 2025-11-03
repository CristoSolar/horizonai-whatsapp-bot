#!/usr/bin/env python3
"""
Script para configurar el bot de BateriasYa con metadata.
Funciona con Redis o SQL según esté disponible.
"""

import os
import sys
import json

# Configurar el path para importar módulos de la app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup_with_redis():
    """Configurar bot usando Redis."""
    import redis
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"Conectando a Redis: {redis_url}")
    
    r = redis.from_url(redis_url, decode_responses=True)
    
    # Ver bots existentes
    bots_data = r.hgetall("bots:registry")
    
    print("\n" + "="*60)
    print("🤖 Bots existentes en Redis:")
    print("="*60)
    
    if not bots_data:
        print("❌ No hay bots en Redis")
        print("\n💡 ¿El bot está registrado? Verifica con:")
        print("   redis-cli HGETALL bots:registry")
        return
    
    for bot_id, bot_json in bots_data.items():
        bot = json.loads(bot_json)
        print(f"\n📋 Bot ID: {bot_id}")
        print(f"   Nombre: {bot.get('name', 'N/A')}")
        print(f"   Assistant ID: {bot.get('assistant_id', 'N/A')}")
        print(f"   Twilio: {bot.get('twilio_phone_number', 'N/A')}")
        
        # Si es el bot de BateriasYa, actualizarlo
        if bot.get('assistant_id') == 'asst_svobnYajdAylQaM5Iqz8Dof3':
            print("\n✅ ¡Encontrado el bot de BateriasYa!")
            
            # Actualizar metadata
            metadata = bot.get('metadata', {})
            metadata.update({
                "horizon_api_token": "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO",
                "sucursal_phone_map": {
                    "santiago": "+56978493528",
                    "rm": "+56978493528",
                    "región metropolitana": "+56978493528",
                    "providencia": "+56978493528",
                    "macul": "+56978493528",
                    "la florida": "+56978493528",
                    "las condes": "+56978493528"
                }
            })
            
            bot['metadata'] = metadata
            
            # Guardar de vuelta a Redis
            r.hset("bots:registry", bot_id, json.dumps(bot))
            
            print("\n✅ Metadata actualizado en Redis!")
            print("\n📋 Nueva configuración:")
            print(json.dumps(metadata, indent=2, ensure_ascii=False))
            
            return True
    
    print("\n❌ No se encontró el bot con assistant_id: asst_svobnYajdAylQaM5Iqz8Dof3")
    return False

def setup_with_sql():
    """Configurar bot usando SQL."""
    from sqlalchemy import create_engine, text
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL no configurado")
        return False
    
    print(f"Conectando a base de datos SQL...")
    engine = create_engine(database_url)
    
    try:
        with engine.connect() as conn:
            # Ver bots existentes
            result = conn.execute(text("""
                SELECT id, external_ref, assistant_id, metadata
                FROM gestion_whatsappbot
            """))
            
            rows = result.fetchall()
            
            print("\n" + "="*60)
            print("🤖 Bots existentes en SQL:")
            print("="*60)
            
            if not rows:
                print("❌ No hay bots en la tabla gestion_whatsappbot")
                print("\n💡 Necesitas crear el bot primero. Ver setup_bateriasya_metadata.sql")
                return False
            
            found = False
            for row in rows:
                print(f"\n📋 Bot ID: {row[0]}")
                print(f"   Nombre: {row[1]}")
                print(f"   Assistant ID: {row[2]}")
                
                if row[2] == 'asst_svobnYajdAylQaM5Iqz8Dof3':
                    found = True
                    print("\n✅ ¡Encontrado el bot de BateriasYa!")
                    
                    # Actualizar metadata
                    metadata = {
                        "horizon_api_token": "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO",
                        "sucursal_phone_map": {
                            "santiago": "+56978493528",
                            "rm": "+56978493528",
                            "región metropolitana": "+56978493528",
                            "providencia": "+56978493528",
                            "macul": "+56978493528",
                            "la florida": "+56978493528",
                            "las condes": "+56978493528"
                        }
                    }
                    
                    conn.execute(text("""
                        UPDATE gestion_whatsappbot
                        SET metadata = :metadata,
                            updated_at = NOW()
                        WHERE id = :bot_id
                    """), {"metadata": json.dumps(metadata), "bot_id": row[0]})
                    
                    conn.commit()
                    
                    print("\n✅ Metadata actualizado en SQL!")
                    print("\n📋 Nueva configuración:")
                    print(json.dumps(metadata, indent=2, ensure_ascii=False))
            
            if not found:
                print("\n❌ No se encontró el bot con assistant_id: asst_svobnYajdAylQaM5Iqz8Dof3")
            
            return found
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        engine.dispose()

def main():
    """Función principal."""
    print("="*60)
    print("🚀 Setup de Bot BateriasYa")
    print("="*60)
    print()
    
    # Intentar primero con Redis (más común)
    print("🔍 Buscando bot en Redis...")
    try:
        if setup_with_redis():
            print("\n✅ ¡Configuración completada en Redis!")
            print("\n🔄 Reinicia el servicio para aplicar cambios:")
            print("   sudo systemctl restart horizonai-whatsapp-bot")
            return
    except Exception as e:
        print(f"⚠️ No se pudo usar Redis: {e}")
    
    # Si no está en Redis, intentar SQL
    print("\n🔍 Buscando bot en SQL...")
    try:
        if setup_with_sql():
            print("\n✅ ¡Configuración completada en SQL!")
            print("\n🔄 Reinicia el servicio para aplicar cambios:")
            print("   sudo systemctl restart horizonai-whatsapp-bot")
            return
    except Exception as e:
        print(f"⚠️ No se pudo usar SQL: {e}")
    
    print("\n" + "="*60)
    print("❌ No se pudo configurar el bot")
    print("="*60)
    print("\n💡 Posibles soluciones:")
    print("1. Verifica que el bot existe en Redis o SQL")
    print("2. Verifica las variables de entorno REDIS_URL y DATABASE_URL")
    print("3. Crea el bot manualmente usando la API o SQL")

if __name__ == "__main__":
    main()
