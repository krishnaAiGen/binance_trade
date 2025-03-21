#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility functions for BTC Bollinger Bands Trading System
"""

import pandas as pd
import numpy as np
import json
import logging
import time
import pytz
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log"),
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

def save_trade_state(state, filepath='trade_state.json'):
    """Save the current trade state to file."""
    try:
        with open(filepath, 'w') as file:
            json.dump(state, file, indent=4)
        logger.info(f"Trade state saved to {filepath}")
    except Exception as e:
        logger.error(f"Error saving trade state: {e}")

def load_trade_state(filepath='trade_state.json'):
    """Load the current trade state from file."""
    try:
        with open(filepath, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        # Create a new state file if it doesn't exist
        initial_state = {
            "in_trade": False,
            "entry_price": 0,
            "entry_time": "",
            "quantity": 0,
            "market_order_id": "",
            "stop_loss_order_id": "",
            "target_order_id": ""
        }
        save_trade_state(initial_state, filepath)
        return initial_state
    except Exception as e:
        logger.error(f"Error loading trade state: {e}")
        return None

def fetch_btc_data(client, limit=100, interval='1h', max_retries=10):
    """
    Fetch BTC/USDT data from Binance with retry mechanism.
    Always fetches complete candles from the previous timeframe (in IST).
    Attempts to fetch data up to max_retries times if there's a failure.
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Get current time in IST
            ist_timezone = pytz.timezone('Asia/Kolkata')
            current_time_ist = datetime.now(ist_timezone)
            
            # Calculate end time for the query - the most recently completed hour
            # This ensures we're always getting completed candles
            end_time = current_time_ist.replace(minute=0, second=0, microsecond=0)
            
            # If we're in the current hour, step back to get the last completed hour
            if current_time_ist.minute > 0:
                end_time = end_time
            else:
                end_time = end_time - timedelta(hours=1)
            
            # Convert to UTC for Binance API (Binance uses UTC timestamps)
            end_time_utc = end_time.astimezone(pytz.UTC)
            
            # Calculate start time based on the limit
            start_time_utc = end_time_utc - timedelta(hours=limit)
            
            # Format timestamps for Binance API
            end_time_ms = int(end_time_utc.timestamp() * 1000)
            start_time_ms = int(start_time_utc.timestamp() * 1000)
            
            logger.info(f"Fetching data from {start_time_utc} to {end_time_utc} UTC")
            
            # Fetch klines with specific start and end times
            klines = client.get_historical_klines(
                symbol='BTCUSDT',
                interval=interval,
                start_str=str(start_time_ms),
                end_str=str(end_time_ms)
            )
            
            # Create DataFrame
            data = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            # Convert types
            data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
            
            # Convert timestamp to IST for better logging and understanding
            data['timestamp_ist'] = data['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                data[col] = data[col].astype(float)
                
            logger.info(f"Successfully fetched {len(data)} hourly candles in IST time")
            logger.info(f"Data range: {data['timestamp_ist'].min()} to {data['timestamp_ist'].max()} IST")
            
            return data
        except Exception as e:
            retry_count += 1
            logger.warning(f"Retry {retry_count}/{max_retries}: Error fetching data: {e}")
            if retry_count < max_retries:
                time.sleep(2)  # Wait 2 seconds before retrying
            else:
                logger.error(f"Failed to fetch data after {max_retries} attempts: {e}")
                return None

def add_bollinger_bands(data, period=10, std_dev=1.5):
    """Add Bollinger Bands to the dataframe."""
    try:
        # Calculate the rolling mean and standard deviation
        data['SMA'] = data['close'].rolling(window=period).mean()
        data['STD'] = data['close'].rolling(window=period).std()
        
        # Calculate upper and lower Bollinger Bands
        data['Upper_Band'] = data['SMA'] + (data['STD'] * std_dev)
        data['Lower_Band'] = data['SMA'] - (data['STD'] * std_dev)
        
        return data
    except Exception as e:
        logger.error(f"Error calculating Bollinger Bands: {e}")
        return data

def check_trade_signal(data):
    """
    Check if there's a trade signal in the latest candle.
    Returns True if:
    1. The low or close price touches the lower Bollinger Band
    2. The Bollinger Band width is greater than the configured minimum width
    """
    try:
        # Get the latest candle
        latest = data.iloc[-1]
        
        # Get minimum Bollinger Band width from config
        config = load_config()
        min_bb_width = config.get('MIN_BOLLINGER_WIDTH', 300)
        
        # Calculate Bollinger Band width
        bb_width = latest['Upper_Band'] - latest['Lower_Band']
        
        # Check if Bollinger Band width is more than the minimum
        if bb_width <= min_bb_width:
            logger.info(f"Bollinger Band width ({bb_width}) is less than or equal to {min_bb_width}. No trade signal.")
            return False
            
        # Check if low or close price touches the lower Bollinger Band
        if latest['low'] <= latest['Lower_Band'] or latest['close'] <= latest['Lower_Band']:
            logger.info(f"Trade signal detected! Price touching lower band with BB width of {bb_width}")
            return True
        
        logger.info(f"No price signal detected. BB width: {bb_width}")
        return False
    except Exception as e:
        logger.error(f"Error checking trade signal: {e}")
        return False

def get_trade_quantity(client, trading_capital, leverage=10):
    """Calculate trade quantity based on specified capital and leverage."""
    try:
        # Use the provided trading capital with specified leverage
        trade_amount = trading_capital * leverage
        
        # Get current BTC price
        ticker = client.get_symbol_ticker(symbol='BTCUSDT')
        btc_price = float(ticker['price'])
        
        # Calculate quantity
        quantity = trade_amount / btc_price
        
        # Round to 3 decimal places (BTC precision)
        quantity = round(quantity, 3)
        
        logger.info(f"Calculated quantity: {quantity} BTC at price {btc_price}")
        logger.info(f"Using capital: ${trading_capital} with {leverage}x leverage")
        return quantity
    except Exception as e:
        logger.error(f"Error calculating quantity: {e}")
        return 0.001  # Minimum quantity as fallback
    

def get_ist_time():
    ist_timezone = pytz.timezone('Asia/Kolkata')    
    current_utc_time = datetime.now(pytz.utc)
    
    current_ist_time = current_utc_time.astimezone(ist_timezone)    
    ist_time_string = current_ist_time.strftime('%Y-%m-%d %H:%M:%S')
    
    return ist_time_string
    