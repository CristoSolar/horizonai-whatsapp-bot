"""
Cliente data storage using Redis.
Stores customer information to avoid repetitive questions.
"""
import json
from typing import Dict, Optional, Any
from datetime import datetime

class ClientDataManager:
    """Manages client data storage in Redis."""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.expiration_days = 30  # Data expires after 30 days
    
    def _get_client_key(self, phone_number: str) -> str:
        """Generate Redis key for client data."""
        # Clean phone number (remove spaces, special chars)
        clean_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "")
        return f"client_data:{clean_phone}"
    
    def get_client_data(self, phone_number: str) -> Dict[str, Any]:
        """Get stored client data."""
        try:
            key = self._get_client_key(phone_number)
            data = self.redis_client.get(key)
            
            if data:
                client_data = json.loads(data.decode('utf-8'))
                return client_data
            
            return {}
            
        except Exception as e:
            print(f"Error getting client data for {phone_number}: {e}")
            return {}
    
    def update_client_data(self, phone_number: str, field: str, value: str) -> bool:
        """Update specific field in client data."""
        try:
            # Get existing data
            client_data = self.get_client_data(phone_number)
            
            # Update field
            client_data[field] = value
            client_data['last_updated'] = datetime.now().isoformat()
            
            # Save back to Redis
            return self.save_client_data(phone_number, client_data)
            
        except Exception as e:
            print(f"Error updating client data for {phone_number}: {e}")
            return False
    
    def save_client_data(self, phone_number: str, data: Dict[str, Any]) -> bool:
        """Save complete client data."""
        try:
            key = self._get_client_key(phone_number)
            
            # Add metadata
            data['phone_number'] = phone_number
            data['created_at'] = data.get('created_at', datetime.now().isoformat())
            data['last_updated'] = datetime.now().isoformat()
            
            # Store in Redis with expiration
            expiration_seconds = self.expiration_days * 24 * 3600
            self.redis_client.setex(
                key, 
                expiration_seconds, 
                json.dumps(data, ensure_ascii=False)
            )
            
            return True
            
        except Exception as e:
            print(f"Error saving client data for {phone_number}: {e}")
            return False
    
    def has_required_info(self, phone_number: str, required_fields: list) -> bool:
        """Check if client has all required information."""
        client_data = self.get_client_data(phone_number)
        
        for field in required_fields:
            if field not in client_data or not client_data[field]:
                return False
        
        return True
    
    def get_missing_fields(self, phone_number: str, required_fields: list) -> list:
        """Get list of missing required fields."""
        client_data = self.get_client_data(phone_number)
        missing_fields = []
        
        for field in required_fields:
            if field not in client_data or not client_data[field]:
                missing_fields.append(field)
        
        return missing_fields
    
    def clear_client_data(self, phone_number: str) -> bool:
        """Clear all data for a client."""
        try:
            key = self._get_client_key(phone_number)
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Error clearing client data for {phone_number}: {e}")
            return False
    
    def extract_info_from_message(self, message: str) -> Dict[str, str]:
        """Extract structured information from user message."""
        message_lower = message.lower()
        extracted = {}
        
        # Extract vehicle brand
        brands = ['volkswagen', 'vw', 'toyota', 'chevrolet', 'ford', 'nissan', 'hyundai', 'kia']
        for brand in brands:
            if brand in message_lower:
                extracted['marca'] = brand.title()
                break
        
        # Extract vehicle model
        models = ['gol', 'corolla', 'aveo', 'fiesta', 'sentra', 'accent', 'rio']
        for model in models:
            if model in message_lower:
                extracted['modelo'] = model.title()
                break
        
        # Extract year (4 digits between 1990-2025)
        import re
        year_match = re.search(r'\b(19[9]\d|20[0-2]\d)\b', message)
        if year_match:
            extracted['año'] = year_match.group(1)
        
        # Extract fuel type
        if any(word in message_lower for word in ['bencinero', 'gasolina', 'nafta']):
            extracted['combustible'] = 'Bencinero'
        elif any(word in message_lower for word in ['diesel', 'diésel']):
            extracted['combustible'] = 'Diesel'
        
        # Extract start-stop system
        if any(word in message_lower for word in ['start stop', 'start-stop', 'startstop']):
            if any(word in message_lower for word in ['no', 'sin', 'no tiene']):
                extracted['start_stop'] = 'No'
            else:
                extracted['start_stop'] = 'Sí'
        
        # Extract location/comuna
        comunas = ['la florida', 'florida', 'curicó', 'curico', 'santiago', 'maipu', 'las condes']
        for comuna in comunas:
            if comuna in message_lower:
                extracted['comuna'] = comuna.title()
                break
        
        return extracted