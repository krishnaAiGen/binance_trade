#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trade Manager for BTC Bollinger Bands Trading System
"""

import logging
import time
from datetime import datetime
from binance.enums import *
# Explicitly import order types to avoid any missing constants
from binance.client import Client
# Define constants if they're not available in the imported module
ORDER_TYPE_STOP_MARKET = 'STOP_MARKET'
ORDER_TYPE_MARKET = 'MARKET'
ORDER_TYPE_LIMIT = 'LIMIT'
SIDE_BUY = 'BUY'
SIDE_SELL = 'SELL'
TIME_IN_FORCE_GTC = 'GTC'

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
        """Check the status of current orders and cancel remaining orders if a trade has completed"""
        if not self.is_in_trade():
            return False
        
        try:
            # Get IDs of our target and stop loss orders
            target_id = self.trade_state["target_order_id"]
            stop_id = self.trade_state["stop_loss_order_id"]
            
            # Check open orders
            open_orders = self.client.futures_get_open_orders(symbol=self.symbol)
            open_order_ids = [order['orderId'] for order in open_orders]
            
            # Case 1: Both orders are gone (unusual but possible)
            if target_id not in open_order_ids and stop_id not in open_order_ids:
                logger.info("Both take profit and stop loss orders are gone. Trade has completed.")
                self.trade_state["in_trade"] = False
                save_trade_state(self.trade_state)
                return True
                
            # Case 2: Stop loss is gone but take profit still exists (stop loss was triggered)
            if stop_id not in open_order_ids and target_id in open_order_ids:
                logger.info("Stop loss was triggered. Cancelling take profit order.")
                try:
                    # Cancel the take profit order
                    self.client.futures_cancel_order(
                        symbol=self.symbol,
                        orderId=target_id
                    )
                    logger.info(f"Successfully cancelled take profit order (ID: {target_id})")
                except Exception as e:
                    logger.error(f"Error cancelling take profit order: {e}")
                
                # Mark trade as complete
                self.trade_state["in_trade"] = False
                save_trade_state(self.trade_state)
                return True
                
            # Case 3: Take profit is gone but stop loss still exists (take profit was triggered)
            if target_id not in open_order_ids and stop_id in open_order_ids:
                logger.info("Take profit was triggered. Cancelling stop loss order.")
                try:
                    # Cancel the stop loss order
                    self.client.futures_cancel_order(
                        symbol=self.symbol,
                        orderId=stop_id
                    )
                    logger.info(f"Successfully cancelled stop loss order (ID: {stop_id})")
                except Exception as e:
                    logger.error(f"Error cancelling stop loss order: {e}")
                
                # Mark trade as complete
                self.trade_state["in_trade"] = False
                save_trade_state(self.trade_state)
                return True
            
            # If we reach here, both orders are still open - trade is ongoing
            logger.info("Trade is still active. Both take profit and stop loss orders exist.")
            return False
            
        except Exception as e:
            logger.error(f"Error checking trade status: {e}")
            return False

    def enter_long_trade(self, quantity, latest_candle=None):
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
            
            logger.info(f"Market order placed successfully: Order ID {market_order['orderId']}")
            
            # Wait for the order to be filled and processed
            time.sleep(2)
            
            # Get entry price
            ticker = self.client.get_symbol_ticker(symbol=self.symbol)
            entry_price = float(ticker['price'])
            
            # 2. Calculate stop loss price ($100 below entry)
            stop_price = entry_price - self.stop_loss_points
            stop_price = round(stop_price, 1)  # Round to 1 decimal for BTC
            
            # 3. Place stop loss order
            logger.info(f"Placing stop loss order at ${stop_price}...")
            try:
                stop_loss_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side=SIDE_SELL,
                    type=ORDER_TYPE_STOP_MARKET,
                    stopPrice=stop_price,
                    closePosition='true'
                )
                logger.info(f"Stop loss order placed successfully: Order ID {stop_loss_order['orderId']}")
            except Exception as e:
                logger.error(f"Failed to place stop loss order: {e}")
                # Cancel the market order and exit
                self.cancel_all_orders()
                return False
            
            # 4. Get latest Bollinger Bands data
            # If latest_candle wasn't provided, fetch it now
            if latest_candle is None:
                data = fetch_btc_data(self.client, limit=30, interval='1h')
                data = add_bollinger_bands(data, period=10, std_dev=1.5)
                latest_candle = data.iloc[-1]
                
            upper_band = latest_candle['Upper_Band']
            
            # 5. Place take profit order at the upper Bollinger Band
            target_price = round(upper_band, 1)  # Round to 1 decimal
            
            logger.info(f"Placing take profit order at ${target_price}...")
            try:
                take_profit_order = self.client.futures_create_order(
                    symbol=self.symbol,
                    side=SIDE_SELL,
                    type=ORDER_TYPE_LIMIT,
                    timeInForce=TIME_IN_FORCE_GTC,
                    quantity=quantity,
                    price=target_price
                )
                logger.info(f"Take profit order placed successfully: Order ID {take_profit_order['orderId']}")
            except Exception as e:
                logger.error(f"Failed to place take profit order: {e}")
                # Cancel previous orders and exit
                self.cancel_all_orders()
                return False
            
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
            
            # Log detailed trade information
            logger.info(f"------------- TRADE ENTRY DETAILS -------------")
            logger.info(f"Entry price: ${entry_price}")
            logger.info(f"Quantity: {quantity} BTC (${entry_price * quantity:.2f})")
            logger.info(f"Stop loss: ${stop_price} (${entry_price - stop_price:.2f} points)")
            logger.info(f"Take profit: ${target_price} (${target_price - entry_price:.2f} points)")
            
            if latest_candle is not None:
                logger.info(f"------------- CANDLE & INDICATOR DETAILS -------------")
                logger.info(f"Signal candle time: {latest_candle['timestamp_ist']}")
                logger.info(f"OHLC: Open=${latest_candle['open']:.2f}, High=${latest_candle['high']:.2f}, Low=${latest_candle['low']:.2f}, Close=${latest_candle['close']:.2f}")
                logger.info(f"Bollinger Bands - Lower: ${latest_candle['Lower_Band']:.2f}, SMA: ${latest_candle['SMA']:.2f}, Upper: ${latest_candle['Upper_Band']:.2f}")
                bb_width = latest_candle['Upper_Band'] - latest_candle['Lower_Band']
                logger.info(f"BB Width: ${bb_width:.2f}")
                
                # Check specifically what triggered the trade
                if latest_candle['low'] <= latest_candle['Lower_Band'] and latest_candle['close'] <= latest_candle['Lower_Band']:
                    logger.info(f"Signal type: Both LOW and CLOSE are below the lower band")
                elif latest_candle['low'] <= latest_candle['Lower_Band']:
                    logger.info(f"Signal type: LOW price (${latest_candle['low']:.2f}) is below lower band (${latest_candle['Lower_Band']:.2f})")
                elif latest_candle['close'] <= latest_candle['Lower_Band']:
                    logger.info(f"Signal type: CLOSE price (${latest_candle['close']:.2f}) is below lower band (${latest_candle['Lower_Band']:.2f})")
                
                logger.info(f"Distance to lower band: ${latest_candle['close'] - latest_candle['Lower_Band']:.2f} points")
                logger.info(f"Distance to upper band: ${latest_candle['Upper_Band'] - latest_candle['close']:.2f} points")
            
            logger.info(f"--------------------------------------------")
            
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