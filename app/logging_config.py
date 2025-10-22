import logging
import sys

def configure_logging():
    """Configure logging to work with systemd/journalctl."""
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler that writes to stdout (captured by systemd)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)
    
    # Configure specific loggers
    logging.getLogger('app.routes.whatsapp').setLevel(logging.INFO)
    logging.getLogger('app.services.conversation_service').setLevel(logging.INFO)
    logging.getLogger('app.services.client_data_service').setLevel(logging.INFO)
    
    return root_logger