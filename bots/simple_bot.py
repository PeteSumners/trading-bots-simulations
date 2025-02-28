import time
import threading
import json
import websocket
import pandas as pd
import logging

LOG_FILE = "simple_bot.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger()

class SimpleBot:
    def __init__(self, initial_capital=10000.0, stock="AAPL"):
        self.capital = initial_capital
        self.stock = stock
        self.positions = {}
        self.profit = 0.0
        self.running = True
        self.data = []  # List of price dicts
        self.trades = []
        self.finnhub_api_key = "cv08lh1r01qo8ssfb3i0cv08lh1r01qo8ssfb3ig"

    def start_finnhub_feed(self):
        def on_message(ws, message):
            data = json.loads(message)
            if 'data' in data and data['type'] == 'trade':
                for trade in data['data']:
                    price = trade['p']
                    self.data.append({"price": price, "timestamp": time.time()})
                    if len(self.data) > 50:  # Keep last 50 for MA calc
                        self.data = self.data[-50:]
                    logger.info(f"Finnhub - {self.stock} Price: ${price:.2f}")
        ws = websocket.WebSocketApp(f"wss://ws.finnhub.io?token={self.finnhub_api_key}", 
                                    on_open=lambda ws: ws.send(json.dumps({"type": "subscribe", "symbol": self.stock})), 
                                    on_message=on_message,
                                    on_error=lambda ws, error: logger.error(f"Finnhub Error: {error}"))
        threading.Thread(target=ws.run_forever, daemon=True).start()
        return ws

    def calculate_moving_averages(self):
        prices = [d["price"] for d in self.data]
        if len(prices) < 20:
            logger.info(f"MA Calc - Not enough data: {len(prices)} prices")
            return None, None
        short_ma = sum(prices[-5:]) / 5  # 5-period MA
        long_ma = sum(prices[-20:]) / 20  # 20-period MA
        logger.info(f"MA Calc - Short MA (5): {short_ma:.2f}, Long MA (20): {long_ma:.2f}, Prices: {prices[-5:]}")
        return short_ma, long_ma

    def trade(self):
        if len(self.data) < 20:
            logger.info(f"{self.stock} - Not enough data yet: {len(self.data)} entries")
            return
        price = self.data[-1]["price"]
        short_ma, long_ma = self.calculate_moving_averages()
        if short_ma is None or long_ma is None:
            return
        
        prev_short = sum([d["price"] for d in self.data[-6:-1]]) / 5 if len(self.data) >= 6 else short_ma
        prev_long = sum([d["price"] for d in self.data[-21:-1]]) / 20 if len(self.data) >= 21 else long_ma

        # Buy: Short MA crosses above Long MA
        if short_ma > long_ma and prev_short <= prev_long:
            quantity = min(10, int(self.capital / price))
            if quantity > 0:
                self.buy(price, quantity)
        # Sell: Short MA crosses below Long MA
        elif short_ma < long_ma and prev_short >= prev_long and self.stock in self.positions:
            self.sell(price, self.positions[self.stock]["quantity"])

    def buy(self, price, quantity):
        cost = price * quantity
        if self.capital >= cost:
            self.capital -= cost
            if self.stock in self.positions:
                current = self.positions[self.stock]
                total_quantity = current["quantity"] + quantity
                avg_price = ((current["buy_price"] * current["quantity"]) + (price * quantity)) / total_quantity
                self.positions[self.stock] = {"quantity": total_quantity, "buy_price": avg_price}
            else:
                self.positions[self.stock] = {"quantity": quantity, "buy_price": price}
            self.trades.append({"timestamp": time.time(), "action": "buy", "price": price, "shares": quantity, "capital": self.capital, "profit": self.profit})
            logger.info(f"Trade - Bought {quantity} {self.stock} at ${price:.2f}, Capital: ${self.capital:.2f}")
            pd.DataFrame(self.trades).to_csv("trades.csv", index=False)
            return True
        logger.info(f"Trade Failed - Insufficient capital for {quantity} {self.stock} at ${price:.2f}")
        return False

    def sell(self, price, quantity):
        if self.stock in self.positions and self.positions[self.stock]["quantity"] >= quantity:
            position = self.positions[self.stock]
            profit = (price - position["buy_price"]) * quantity
            self.capital += price * quantity
            self.profit += profit
            position["quantity"] -= quantity
            if position["quantity"] == 0:
                del self.positions[self.stock]
            self.trades.append({"timestamp": time.time(), "action": "sell", "price": price, "shares": quantity, "capital": self.capital, "profit": self.profit})
            logger.info(f"Trade - Sold {quantity} {self.stock} at ${price:.2f}, Profit: ${profit:.2f}, Capital: ${self.capital:.2f}")
            pd.DataFrame(self.trades).to_csv("trades.csv", index=False)
            return True
        logger.info(f"Trade Failed - No/insufficient position to sell {quantity} {self.stock}")
        return False

    def run(self):
        logger.info(f"Starting with ${self.capital:.2f} for {self.stock}")
        finnhub_stream = self.start_finnhub_feed()
        time.sleep(5)  # Wait for data
        while self.running:
            self.trade()
            time.sleep(1)  # Check every second
        finnhub_stream.close()
        logger.info(f"Stopped - Capital: ${self.capital:.2f}, Profit: ${self.profit:.2f}, Positions: {self.positions}")

if __name__ == "__main__":
    bot = SimpleBot(stock="AAPL")
    try:
        bot.run()
    except KeyboardInterrupt:
        bot.running = False