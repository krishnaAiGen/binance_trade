#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Binance trading functionality
Places a long trade with $100 stop loss and $500 take profit
"""

import logging
import json
import time
from datetime import datetime
import pytz
from binance.client import Client

# Define order type constants
ORDER_TYPE_MARKET = 'MARKET'
ORDER_TYPE_LIMIT = 'LIMIT'
ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
TIME_IN_FORCE_GTC = 'GTC'

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

def get_ist_time():
    """Get current time in IST format with timezone indicator"""
    ist_timezone = pytz.timezone('Asia/Kolkata')    
    current_utc_time = datetime.now(pytz.utc)
    
    current_ist_time = current_utc_time.astimezone(ist_timezone)    
    ist_time_string = current_ist_time.strftime('%Y-%m-%d %H:%M:%S IST')
    
    return ist_time_string

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

def set_leverage(client, symbol, leverage):
    """Set leverage for the specified symbol"""
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logger.info(f"Leverage set to {leverage}x for {symbol}")
        return True
    except Exception as e:
        logger.error(f"Error setting leverage: {e}")
        return False

def place_test_trade():
    """Place a test trade with specified stop loss and take profit"""
    # Initialize client
    client, config = initialize_client()
    if not client or not config:
        logger.error("Failed to initialize client. Exiting.")
        return
    
    # Get trading parameters
    symbol = 'BTCUSDT'
    leverage = config.get('LEVERAGE', 3)
    stop_loss_points = 100  # $100 below entry
    take_profit_points = 500  # $500 above entry
    
    # Set leverage
    if not set_leverage(client, symbol, leverage):
        logger.error("Failed to set leverage. Exiting.")
        return
    
    # Calculate quantity (0.001 BTC for testing)
    quantity = 0.01
    
    try:
        # Log start of test
        ist_time = get_ist_time()
        logger.info(f"------- STARTING TEST TRADE at {ist_time} -------")
        logger.info(f"Symbol: {symbol}")
        logger.info(f"Leverage: {leverage}x")
        logger.info(f"Quantity: {quantity} BTC")
        logger.info(f"Stop Loss: ${stop_loss_points} below entry")
        logger.info(f"Take Profit: ${take_profit_points} above entry")
        
        # 1. Place market buy order
        logger.info("Placing market buy order...")
        market_order = client.futures_create_order(
            symbol=symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        
        logger.info(f"Market order placed successfully: Order ID {market_order['orderId']}")
        
        # Wait for the order to be filled
        time.sleep(2)
        
        # Get entry price
        ticker = client.get_symbol_ticker(symbol=symbol)
        entry_price = float(ticker['price'])
        logger.info(f"Entry price: ${entry_price}")
        
        # 2. Calculate stop loss price ($100 below entry)
        stop_price = entry_price - stop_loss_points
        stop_price = round(stop_price, 1)  # Round to 1 decimal for BTC
        
        # 3. Place stop loss order
        logger.info(f"Placing stop loss order at ${stop_price}...")
        stop_loss_order = client.futures_create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_STOP_MARKET,
            stopPrice=stop_price,
            closePosition='true'
        )
        
        logger.info(f"Stop loss order placed successfully: Order ID {stop_loss_order['orderId']}")
        
        # 4. Calculate take profit price ($500 above entry)
        target_price = entry_price + take_profit_points
        target_price = round(target_price, 1)  # Round to 1 decimal
        
        # 5. Place take profit order
        logger.info(f"Placing take profit order at ${target_price}...")
        take_profit_order = client.futures_create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            quantity=quantity,
            price=target_price
        )
        
        logger.info(f"Take profit order placed successfully: Order ID {take_profit_order['orderId']}")
        
        # Log order summary
        logger.info("------- TEST TRADE SUMMARY -------")
        logger.info(f"Entry Price: ${entry_price}")
        logger.info(f"Stop Loss: ${stop_price} (${entry_price - stop_price:.2f} points below entry)")
        logger.info(f"Take Profit: ${target_price} (${target_price - entry_price:.2f} points above entry)")
        logger.info(f"Market Order ID: {market_order['orderId']}")
        logger.info(f"Stop Loss Order ID: {stop_loss_order['orderId']}")
        logger.info(f"Take Profit Order ID: {take_profit_order['orderId']}")
        logger.info("--------------------------------")
        
        logger.info("Test trade placed successfully. Monitor the orders in your Binance account.")
        return True
    
    except Exception as e:
        logger.error(f"Error placing test trade: {e}")
        logger.exception(e)  # Log full traceback
        return False

def main():
    """Main entry point for test script"""
    logger.info("Starting Binance trading test script")
    result = place_test_trade()
    
    if result:
        logger.info("Test completed successfully. Check your Binance account for the orders.")
    else:
        logger.error("Test failed. See logs for details.")


if __name__ == "__main__":
    main() 