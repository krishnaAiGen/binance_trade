import json
from binance.client import Client
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test_trade.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_config(config_path='config.json'):
    """Load configuration from JSON file."""
    try:
        with open(config_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

def initialize_client():
    """Initialize Binance API client with provided credentials"""
    config = load_config()
    if not config:
        logger.error("Failed to load configuration")
        return None, None
        
    try:
        client = Client(config['API_KEY'], config['API_SECRET'], tld='com')
        logger.info("Binance client initialized successfully")
        return client, config
    except Exception as e:
        logger.error(f"Error initializing Binance client: {e}")
        return None, None

def check_open_orders():
    """Check open orders in Binance"""
    client, config = initialize_client()
    print("Client Initialized")
    if not client or not config:
        logger.error("Failed to initialize client. Exiting.")
        return
    
    try:
        symbol = 'BTCUSDT'
        open_orders = client.futures_get_open_orders(symbol=symbol)
        
        # Extract order IDs
        open_order_ids = [order['orderId'] for order in open_orders]
        
        print("\n========== OPEN ORDERS SUMMARY ==========")
        if not open_orders:
            print("No open orders found for BTCUSDT")
        else:
            print(f"Total open orders: {len(open_orders)}")
            for i, order in enumerate(open_orders, 1):
                print(f"\nOrder #{i}:")
                print(f"  Order ID: {order['orderId']}")
                print(f"  Symbol: {order['symbol']}")
                print(f"  Type: {order['type']}")
                print(f"  Side: {order['side']}")
                if 'price' in order and float(order['price']) > 0:
                    print(f"  Price: ${float(order['price'])}")
                if 'stopPrice' in order and float(order['stopPrice']) > 0:
                    print(f"  Stop Price: ${float(order['stopPrice'])}")
                print(f"  Quantity: {order['origQty']}")
        print("=========================================\n")
        
        # Also print the raw data for debugging purposes
        print("Raw order data:")
        print(f"Open orders: {open_orders}")
        print(f"Open order IDs: {open_order_ids}")
        
        return open_orders
    except Exception as e:
        print(f"ERROR: Failed to get open orders: {e}")
        logger.error(f"Error getting open orders: {e}")
        return None

def main():
    """Main entry point for the script"""
    print("Checking for open orders in Binance...")
    check_open_orders()

if __name__ == "__main__":
    main()