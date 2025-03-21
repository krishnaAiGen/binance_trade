#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trade Manager for BTC Bollinger Bands Trading System
"""

import logging
import time
from datetime import datetime
from binance.enums import *
from utils import save_trade_state, load_trade_state, fetch_btc_data, add_bollinger_bands, get_ist_time

# Setup logging
logger = logging.getLogger(__name__)

class TradeManager:
    def __init__(self, client, config):
        self.client = client
        self.symbol = 'BTCUSDT'
        self.leverage = config.get('LEVERAGE', 10)
        self.trading_capital = config.get('TRADING_CAPITAL', 5000)
        self.trade_state = load_trade_state()
        self.stop_loss_points = config.get('STOP_LOSS_POINTS', 100)  # $100 stop loss
        self.use_upper_band_exit = config.get('USE_UPPER_BAND_EXIT', True)  # Exit when price touches upper band
        
        # Set leverage for BTCUSDT
        self._set_leverage()

    def _set_leverage(self):
        """Set leverage for BTCUSDT to 10x"""
        try:
            self.client.futures_change_leverage(symbol=self.symbol, leverage=self.leverage)
            logger.info(f"Leverage set to {self.leverage}x for {self.symbol}")
        except Exception as e:
            logger.error(f"Error setting leverage: {e}")

    def is_in_trade(self):
        """Check if we're currently in a trade"""
        return self.trade_state["in_trade"]

    def check_trade_status(self):
        """Check the status of current orders"""
        if not self.is_in_trade():
            return False
        
        try:
            # Check if target was hit
            target_id = self.trade_state["target_order_id"]
            stop_id = self.trade_state["stop_loss_order_id"]
            
            # Check open orders
            open_orders = self.client.futures_get_open_orders(symbol=self.symbol)
            open_order_ids = [order['orderId'] for order in open_orders]
            
            # If neither target nor stop loss is in open orders, one was executed
            if target_id not in open_order_ids and stop_id not in open_order_ids:
                logger.info("Trade has been completed (either target hit or stop loss triggered)")
                self.trade_state["in_trade"] = False
                save_trade_state(self.trade_state)
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking trade status: {e}")
            return False

    def enter_long_trade(self, quantity):
        """Enter a long trade for BTC"""
        if self.is_in_trade():
            logger.info("Already in a trade. Skipping.")
            return False
        
        try:
            ist_time = get_ist_time()
            print("TAKEN TRADE at time", ist_time)
            logger.info(f"TAKEN TRADE at time {ist_time}")
            # 1. Place market buy order
            market_order = self.client.futures_create_order(
                symbol=self.symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quantity=quantity
            )
            
            # Get entry price
            ticker = self.client.get_symbol_ticker(symbol=self.symbol)
            entry_price = float(ticker['price'])
            
            # 2. Calculate stop loss price ($100 below entry)
            stop_price = entry_price - self.stop_loss_points
            stop_price = round(stop_price, 1)  # Round to 1 decimal for BTC
            
            # 3. Place stop loss order
            stop_loss_order = self.client.futures_create_order(
                symbol=self.symbol,
                side=SIDE_SELL,
                type=ORDER_TYPE_STOP_MARKET,
                stopPrice=stop_price,
                closePosition='true'
            )
            
            # 4. Get latest Bollinger Bands data
            data = fetch_btc_data(self.client, limit=30, interval='1h')
            data = add_bollinger_bands(data, period=10, std_dev=1.5)
            upper_band = data['Upper_Band'].iloc[-1]
            
            # 5. Place take profit order at the upper Bollinger Band
            target_price = round(upper_band, 1)  # Round to 1 decimal
            
            take_profit_order = self.client.futures_create_order(
                symbol=self.symbol,
                side=SIDE_SELL,
                type=ORDER_TYPE_LIMIT,
                timeInForce=TIME_IN_FORCE_GTC,
                quantity=quantity,
                price=target_price
            )
            
            # Update trade state
            self.trade_state = {
                "in_trade": True,
                "entry_price": entry_price,
                "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "quantity": quantity,
                "market_order_id": market_order['orderId'],
                "stop_loss_order_id": stop_loss_order['orderId'],
                "target_order_id": take_profit_order['orderId'],
                "stop_loss_price": stop_price,
                "target_price": target_price
            }
            
            # Save trade state to file
            save_trade_state(self.trade_state)
            
            logger.info(f"Entered long trade: {quantity} BTC at ${entry_price}")
            logger.info(f"Stop loss set at: ${stop_price}")
            logger.info(f"Take profit set at: ${target_price}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error entering trade: {e}")
            return False

    def update_trailing_stop(self):
        """Update stop loss order to trail price movement (optional feature)"""
        if not self.is_in_trade():
            return False
            
        try:
            # Get current price
            ticker = self.client.get_symbol_ticker(symbol=self.symbol)
            current_price = float(ticker['price'])
            
            # Calculate new stop loss ($100 below current price)
            new_stop_price = current_price - self.stop_loss_points
            new_stop_price = round(new_stop_price, 1)
            
            # Only update if new stop is higher than the current one
            if new_stop_price > self.trade_state["stop_loss_price"]:
                # Cancel existing stop loss
                self.client.futures_cancel_order(
                    symbol=self.symbol,
                    orderId=self.trade_state["stop_loss_order_id"]
                )
                
                # Place new stop loss
                new_stop_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side=SIDE_SELL,
                    type=ORDER_TYPE_STOP_MARKET,
                    stopPrice=new_stop_price,
                    closePosition='true'
                )
                
                # Update trade state
                self.trade_state["stop_loss_order_id"] = new_stop_order['orderId']
                self.trade_state["stop_loss_price"] = new_stop_price
                save_trade_state(self.trade_state)
                
                logger.info(f"Updated stop loss to ${new_stop_price}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating trailing stop: {e}")
            
        return False

    def cancel_all_orders(self):
        """Cancel all open orders for BTC (emergency function)"""
        try:
            result = self.client.futures_cancel_all_open_orders(symbol=self.symbol)
            logger.info(f"Cancelled all open orders: {result}")
            
            # Reset trade state
            self.trade_state["in_trade"] = False
            save_trade_state(self.trade_state)
            
            return True
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")
            return False