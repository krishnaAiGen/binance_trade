def get_next_check_time():
    """
    Calculate the next time to check for trading signals.
    Trading check happens at the 31st minute of each hour in IST
    to ensure the hourly candle is complete.
    """
    # Get current time in IST
    ist_timezone = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist_timezone)
    
    # Calculate next check time - always at the 31st minute of each hour
    if now_ist.minute < 31:
        # If before xx:31, schedule for current hour at xx:31
        next_check = now_ist.replace(minute=31, second=0, microsecond=0)
    else:
        # If after xx:31, schedule for next hour at xx:31
        next_check = (now_ist.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).replace(minute=31)
    
    return next_check#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Entry Point for BTC Bollinger Bands Trading Bot

This bot monitors BTC price and enters a long trade when price touches 
the lower Bollinger Band. It manages trades with:
- Fixed 10x leverage
- Automatic stop loss at 2% below entry
- Take profit at 3% above entry
- One trade at a time (waits for previous trade to complete)
"""

import time
import logging
import schedule
import pytz
from datetime import datetime, timedelta
from binance.client import Client
from utils import load_config, fetch_btc_data, add_bollinger_bands, check_trade_signal, get_trade_quantity
from trade_manager import TradeManager

# Setup logging
logger = logging.getLogger(__name__)

def initialize_client():
    """Initialize Binance API client and load config"""
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

def run_trading_cycle(client, trade_manager, config):
    """Run a single trading cycle - check for signals and execute if needed"""
    logger.info("Running trading cycle...")
    
    # Check if we're already in a trade
    if trade_manager.is_in_trade():
        # Check if the trade has completed
        trade_complete = trade_manager.check_trade_status()
        if trade_complete:
            logger.info("Previous trade is complete, ready for next signal")
        else:
            logger.info("Still in active trade, waiting for exit")
            return
    
    # Fetch latest BTC data
    data = fetch_btc_data(client, limit=30, interval='1h')  # Get 30 hourly candles
    if data is None or len(data) < 20:
        logger.error("Insufficient data to calculate Bollinger Bands")
        return
    
    # Add Bollinger Bands (10 period, 1.5 standard deviations)
    period = config.get('BOLLINGER_PERIOD', 10)
    std_dev = config.get('BOLLINGER_STD', 1.5)
    data = add_bollinger_bands(data, period=period, std_dev=std_dev)
    
    # Check for trade signal
    if check_trade_signal(data):
        logger.info("Trade signal detected! Price touching lower Bollinger Band with width > 300")
        
        # Calculate trade quantity
        trading_capital = config.get('TRADING_CAPITAL', 5000)
        leverage = config.get('LEVERAGE', 10)
        quantity = get_trade_quantity(client, trading_capital, leverage=leverage)
        if quantity <= 0:
            logger.error("Invalid trade quantity calculated")
            return
        
        # Enter the trade
        success = trade_manager.enter_long_trade(quantity)
        if success:
            logger.info(f"Successfully entered long trade with {quantity} BTC")
        else:
            logger.warning("Failed to enter trade")
    else:
        logger.info("No trade signal detected")

def main():
    """Main entry point for the trading bot"""
    logger.info("Starting BTC Bollinger Bands Trading Bot")
    
    # Initialize Binance client
    client, config = initialize_client()
    if not client or not config:
        logger.error("Failed to initialize. Exiting.")
        return
    
    # Log configuration settings
    logger.info(f"Trading with capital: ${config.get('TRADING_CAPITAL', 5000)}")
    logger.info(f"Leverage: {config.get('LEVERAGE', 10)}x")
    logger.info(f"Bollinger Bands: Period={config.get('BOLLINGER_PERIOD', 10)}, StdDev={config.get('BOLLINGER_STD', 1.5)}")
    logger.info(f"Min Bollinger Band Width: {config.get('MIN_BOLLINGER_WIDTH', 300)}")
    logger.info(f"Stop Loss: ${config.get('STOP_LOSS_POINTS', 100)}")
    
    # Initialize trade manager with config
    trade_manager = TradeManager(client, config)
    
    # Schedule first check at the next minute 31
    next_check = get_next_check_time()
    
    # Convert current time to IST for comparison
    ist_timezone = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist_timezone)
    
    # Calculate seconds until next check (comparing two timezone-aware datetimes)
    seconds_until_next_check = (next_check - now_ist).total_seconds()
    
    logger.info(f"Scheduling first check at {next_check.strftime('%Y-%m-%d %H:%M:%S')} IST "
                f"({int(seconds_until_next_check/60)} minutes, {int(seconds_until_next_check%60)} seconds from now)")
    
    # Schedule checks at minute 31 of every hour (in IST time)
    schedule.every().hour.at(":31").do(run_trading_cycle, client=client, trade_manager=trade_manager, config=config)
    
    # Main loop
    logger.info("Bot running. Press Ctrl+C to stop.")
    try:
        if seconds_until_next_check > 0:
            logger.info(f"Waiting for next check time...")
            time.sleep(seconds_until_next_check)
            # Run first check
            run_trading_cycle(client, trade_manager, config)
        
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    
if __name__ == "__main__":
    main()