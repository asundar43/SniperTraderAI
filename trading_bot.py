import os
import time
import logging
import requests
import websocket
from dotenv import load_dotenv
import json

# Load environment variables from secrets.env file
load_dotenv('secrets.env')

# Configuration for the PumpFun API
API_KEY = os.getenv("PUMPFUN_API_KEY")
WALLET_PUBLIC_KEY = os.getenv("WALLET_PUBLIC_KEY")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY")

# Base URL for the PumpFun API
BASE_URL = "https://pumpportal.fun/api"

class PumpFunBot:
    def __init__(self, paper_mode=True):
        if not API_KEY or not WALLET_PUBLIC_KEY or not WALLET_PRIVATE_KEY:
            raise ValueError("API keys or wallet keys not set. Please set them in the .env file.")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.base_url = BASE_URL
        self.paper_mode = paper_mode
        self.virtual_balance = 1  # Starting with 1 SOL
        self.positions = {}  # Track virtual positions
        self.market_data = {}  # Store market data from WebSocket
        self.token_prices = {}  # Track token prices
        self.token_volumes = {}  # Track token volumes

    def get_market_data(self):
        """
        Returns the current market data collected from WebSocket feeds.
        """
        logging.debug(f"Current market data: {self.market_data}")
        return self.market_data

    def place_order(self, coin: str, side: str, quantity: float, price: float):
        """
        Places an order for a given memecoin.
        - coin: the memecoin symbol
        - side: 'buy' or 'sell'
        - quantity: the amount of coin to trade
        - price: target price for the order
        """
        if self.paper_mode:
            self.simulate_trade(coin, side, quantity, price)
        else:
            # Execute real trade using the /trade endpoint
            order_data = {
                "coin": coin,
                "side": side,
                "quantity": quantity,
                "price": price
            }
            try:
                response = self.session.post(f"{self.base_url}/trade?api-key={API_KEY}", json=order_data)
                response.raise_for_status()
                data = response.json()
                logging.info(f"Order placed successfully: {data}")
                return data
            except requests.RequestException as e:
                logging.error(f"Order placement failed: {e}")
                return None

    def simulate_trade(self, coin: str, side: str, quantity: float, price: float):
        """
        Simulates a trade in paper mode.
        """
        if side == 'buy':
            cost = quantity * price
            if self.virtual_balance >= cost:
                self.virtual_balance -= cost
                self.positions[coin] = self.positions.get(coin, 0) + quantity
                logging.info(f"Simulated buy: {quantity} {coin} at {price}. New balance: {self.virtual_balance}")
            else:
                logging.warning("Insufficient virtual balance for buy order.")
        elif side == 'sell':
            if self.positions.get(coin, 0) >= quantity:
                self.virtual_balance += quantity * price
                self.positions[coin] -= quantity
                logging.info(f"Simulated sell: {quantity} {coin} at {price}. New balance: {self.virtual_balance}")
            else:
                logging.warning("Insufficient virtual position for sell order.")

    def connect_to_websocket(self):
        """
        Connects to the PumpPortal WebSocket for real-time data.
        """
        ws = websocket.WebSocketApp("wss://pumpportal.fun/api/data",
                                    on_message=self.on_message,
                                    on_error=self.on_error,
                                    on_close=self.on_close)
        ws.on_open = self.on_open
        ws.run_forever()

    def on_message(self, ws, message):
        """
        Handles incoming WebSocket messages.
        """
        try:
            data = json.loads(message)
            # Log the raw message for debugging
            logging.debug(f"Raw WebSocket message: {message}")
            
            # Check if this is a subscription confirmation
            if 'result' in data:
                logging.info(f"Subscription response: {data}")
                return
                
            event_type = data.get('type')
            if not event_type:
                logging.warning(f"Message received without event type: {data}")
                return
                
            if event_type == 'newToken':
                self.handle_new_token(data)
            elif event_type == 'tokenTrade':
                self.handle_token_trade(data)
            elif event_type == 'accountTrade':
                self.handle_account_trade(data)
            elif event_type == 'raydiumLiquidity':
                self.handle_raydium_liquidity(data)
            else:
                logging.warning(f"Unknown event type received: {event_type}")
            
            logging.info(f"Processed {event_type} event")
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse WebSocket message: {e}")
            logging.error(f"Raw message was: {message}")
        except Exception as e:
            logging.error(f"Error processing WebSocket message: {e}")
            logging.error(f"Message was: {message}")

    def on_open(self, ws):
        """
        Handles WebSocket connection opening and subscribes to desired streams.
        """
        logging.info("WebSocket connection opened")
        
        # Subscribe to different data streams
        subscriptions = [
            {"method": "subscribeNewToken"},
            {"method": "subscribeTokenTrade", "params": ["ALL"]},  # or specific tokens
            {"method": "subscribeRaydiumLiquidity"}
        ]
        
        for sub in subscriptions:
            ws.send(json.dumps(sub))
            logging.info(f"Subscribed to {sub['method']}")

    def handle_new_token(self, data):
        """
        Handles new token creation events.
        """
        token_address = data.get('address')
        if token_address:
            logging.info(f"New token created: {token_address}")
            # Add your token analysis logic here
            self.examine_token_contract(token_address)

    def handle_token_trade(self, data):
        """
        Handles token trade events and updates market data.
        """
        token = data.get('token')
        price = data.get('price')
        volume = data.get('volume')
        
        if token:
            self.token_prices[token] = price
            self.token_volumes[token] = self.token_volumes.get(token, 0) + volume
            
            # Update market data
            self.market_data[token] = {
                'price': price,
                'volume': self.token_volumes[token],
                'address': token,
                'last_trade': time.time()
            }
            
        logging.info(f"Trade detected for {token}: price={price}, volume={volume}")

    def handle_account_trade(self, data):
        """
        Handles account trade events.
        """
        account = data.get('account')
        token = data.get('token')
        side = data.get('side')
        logging.info(f"Account {account} {side} {token}")
        # Add your account tracking logic here

    def handle_raydium_liquidity(self, data):
        """
        Handles Raydium liquidity events.
        """
        token = data.get('token')
        amount = data.get('amount')
        logging.info(f"Liquidity added to Raydium for {token}: {amount}")
        # Add your liquidity analysis logic here

    def analyze_tokens(self, min_liquidity: float, min_volume: float, min_holders: int):
        """
        Analyzes tokens to find promising memecoins based on specified filters.
        - min_liquidity: minimum liquidity required
        - min_volume: minimum trading volume required
        - min_holders: minimum number of holders required
        """
        market_data = self.get_market_data()
        if not market_data:
            logging.error("No market data available for analysis.")
            return []

        promising_tokens = []
        for token, data in market_data.items():
            liquidity = data.get('liquidity', 0)
            volume = data.get('volume', 0)
            holders = data.get('holders', 0)

            if liquidity >= min_liquidity and volume >= min_volume and holders >= min_holders:
                promising_tokens.append(data)

        logging.info(f"Found {len(promising_tokens)} promising tokens based on filters.")
        return promising_tokens

    def examine_token_contract(self, token_address: str):
        """
        Examines the token contract using the GMGN API.
        - token_address: the address of the token contract
        """
        try:
            response = self.session.get(f"https://gmgnapi.com/token/{token_address}/details")
            response.raise_for_status()
            token_details = response.json()

            # Analyze token distribution and contract methods
            distribution = token_details.get('distribution', {})
            contract_methods = token_details.get('contract_methods', [])

            # Check for risks (e.g., high concentration of tokens)
            if self.is_token_risky(distribution, contract_methods):
                logging.warning(f"Token {token_address} is considered risky.")
                return False

            # If safe, add to database
            self.add_token_to_database(token_address, token_details)
            logging.info(f"Token {token_address} added to database.")
            return True

        except requests.RequestException as e:
            logging.error(f"Failed to examine token contract: {e}")
            return False

    def is_token_risky(self, distribution, contract_methods):
        """
        Determines if a token is risky based on its distribution and contract methods.
        """
        # Example risk analysis logic
        top_holder_percentage = distribution.get('top_holder_percentage', 0)
        if top_holder_percentage > 50:
            return True
        # Add more checks as needed
        return False

    def add_token_to_database(self, token_address, token_details):
        """
        Adds a token to the bot's database.
        """
        # Placeholder for database logic
        # e.g., self.database.insert(token_address, token_details)
        logging.info(f"Token {token_address} added to the database.")

    def analyze_with_rugchecksxyz(self, token_address: str):
        """
        Analyzes the token using Rugchecksxyz API for red flags and liquidity issues.
        - token_address: the address of the token contract
        """
        try:
            response = self.session.get(f"https://rugchecksxyz.com/api/token/{token_address}/analysis")
            response.raise_for_status()
            analysis_data = response.json()

            # Check for red flags
            red_flags = analysis_data.get('red_flags', [])
            liquidity_issues = analysis_data.get('liquidity_issues', False)

            if red_flags or liquidity_issues:
                logging.warning(f"Token {token_address} has red flags or liquidity issues.")
                return False

            return True

        except requests.RequestException as e:
            logging.error(f"Failed to analyze token with Rugchecksxyz: {e}")
            return False

    def analyze_with_bubblemaps(self, token_address: str):
        """
        Analyzes the token using Bubblemaps API for activity and distribution.
        - token_address: the address of the token contract
        """
        try:
            response = self.session.get(f"https://bubblemaps.com/api/token/{token_address}/activity")
            response.raise_for_status()
            activity_data = response.json()

            # Check for suspicious activity
            suspicious_activity = activity_data.get('suspicious_activity', False)

            if suspicious_activity:
                logging.warning(f"Token {token_address} has suspicious activity.")
                return False

            return True

        except requests.RequestException as e:
            logging.error(f"Failed to analyze token with Bubblemaps: {e}")
            return False

    def add_to_final_database(self, token_address, token_details):
        """
        Adds a token to the final database for trading if it passes all checks.
        """
        # Placeholder for final database logic
        # e.g., self.final_database.insert(token_address, token_details)
        logging.info(f"Token {token_address} added to the final database for trading.")

    def calculate_momentum(self, token_data):
        """
        Calculates momentum for a given token using simple moving averages.
        - token_data: market data for the token
        """
        prices = token_data.get('prices', [])
        if len(prices) < 20:
            return 0  # Not enough data to calculate momentum

        short_term_avg = sum(prices[-5:]) / 5
        long_term_avg = sum(prices[-20:]) / 20

        return short_term_avg - long_term_avg

    def execute_momentum_trade(self, token):
        """
        Executes a trade based on momentum analysis.
        - token: the token to trade
        """
        momentum = self.calculate_momentum(token)
        if momentum > 0:
            logging.info(f"Positive momentum detected for {token['symbol']}. Placing buy order.")
            self.place_order(coin=token['symbol'], side='buy', quantity=100, price=token['current_price'])
        elif momentum < 0:
            logging.info(f"Negative momentum detected for {token['symbol']}. Placing sell order.")
            self.place_order(coin=token['symbol'], side='sell', quantity=100, price=token['current_price'])

    def on_error(self, ws, error):
        """
        Handles WebSocket errors.
        """
        logging.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """
        Handles WebSocket connection closing.
        """
        logging.info("WebSocket connection closed")

    def print_stats(self):
        """
        Prints trading statistics in an organized, two-column format.
        """
        # Clear screen for better visibility (optional)
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Get current timestamp
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        
        # Calculate total holdings value
        holdings_value = sum(
            self.positions.get(token, 0) * self.token_prices.get(token, 0)
            for token in self.positions
        )
        total_value = self.virtual_balance + holdings_value
        
        # Format the statistics
        stats = f"""
╔══════════════════════════════════════════════════════════════════╗
║                     PumpFun Trading Bot Stats                     ║
╠═══════════════════════════════╦══════════════════════════════════╣
║ ACCOUNT SUMMARY               ║ TRADING ACTIVITY                  ║
╟───────────────────────────────╫──────────────────────────────────╢
║ Virtual Balance: ◎{self.virtual_balance:<10.2f} ║ Paper Mode: {str(self.paper_mode):<19} ║
║ Holdings Value:  ◎{holdings_value:<10.2f} ║ Active Tokens: {len(self.positions):<16} ║
║ Total Value:     ◎{total_value:<10.2f} ║ Last Update: {current_time}  ║
╠═══════════════════════════════╩══════════════════════════════════╣
║ CURRENT HOLDINGS                                                 ║
╟──────────────────────────────────────────────────────────────────╢"""

        # Add holdings details
        holdings_details = ""
        for token, amount in self.positions.items():
            if amount > 0:  # Only show non-zero positions
                price = self.token_prices.get(token, 0)
                value = amount * price
                holdings_details += f"\n║ {token[:12]:<12} │ Amount: {amount:<10.4f} │ Price: ◎{price:<8.4f} │ ◎{value:<10.2f} ║"

        if not holdings_details:
            holdings_details = "\n║ No active positions                                              ║"

        stats += holdings_details
        stats += "\n╚══════════════════════════════════════════════════════════════════╝"
        
        print(stats)
        logging.info("Stats updated")

    def run(self):
        """
        Main trading loop that uses WebSocket data instead of REST API.
        """
        logging.info("Starting PumpFun Trading Bot...")
        
        # Start WebSocket connection in a separate thread
        import threading
        ws_thread = threading.Thread(target=self.connect_to_websocket)
        ws_thread.daemon = True
        ws_thread.start()
        
        while True:
            # Print stats every iteration
            self.print_stats()
            
            # Get current market data from WebSocket-populated data
            market_data = self.get_market_data()
            
            # Analyze each token in our market data
            for token_address, token_data in market_data.items():
                if self.examine_token_contract(token_address):
                    if self.analyze_with_rugchecksxyz(token_address) and self.analyze_with_bubblemaps(token_address):
                        self.add_to_final_database(token_address, token_data)
                        self.execute_momentum_trade(token_data)
            
            time.sleep(10)


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        bot = PumpFunBot(paper_mode=True)
        bot.run()
    except Exception as e:
        logging.error(f"Error in trading bot: {e}")

if __name__ == "__main__":
    main() 