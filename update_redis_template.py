#!/usr/bin/env python3
"""
Script para actualizar el template SID en Redis para el bot de BateriasYa
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def update_template():
    import redis
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    print(f"Conectando a Redis: {redis_url}")
    
    r = redis.from_url(redis_url, decode_responses=True)
    
    # Obtener el bot de BateriasYa
    bot_id = "cc6b403d499043da9f68e9604db5ab65"
    bot_json = r.hget("bots:registry", bot_id)
    
    if not bot_json:
        print(f"❌ No se encontró el bot {bot_id}")
        return False
    
    bot = json.loads(bot_json)
    
    print(f"\n📋 Bot encontrado: {bot.get('name', 'N/A')}")
    print(f"   Assistant ID: {bot.get('assistant_id', 'N/A')}")
    
    # Actualizar metadata con el template
    metadata = bot.get('metadata', {})
    
    print(f"\n🔧 Metadata actual:")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    
    # Agregar el template SID
    metadata['twilio_template_sid'] = 'HX1fb6b0f4baadd214e76cada1fa1369b8'
    metadata['twilio_template_name'] = 'baterias_ya'
    
    bot['metadata'] = metadata
    
    # Guardar de vuelta
    r.hset("bots:registry", bot_id, json.dumps(bot))
    
    print(f"\n✅ Metadata actualizado!")
    print(f"\n📋 Nueva configuración:")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    
    return True

if __name__ == "__main__":
    print("="*60)
    print("🚀 Actualizar Template SID en Redis")
    print("="*60)
    print()
    
    try:
        if update_template():
            print("\n✅ ¡Template configurado exitosamente!")
            print("\n🔄 Reinicia el servicio para aplicar cambios:")
            print("   sudo systemctl restart horizonai-whatsapp-bot")
            print("\n💡 Ahora el bot enviará notificaciones usando el template aprobado")
        else:
            print("\n❌ No se pudo actualizar el template")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
