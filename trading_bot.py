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

# ANSI escape codes for colored logging
class LogColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class PumpFunBot:
    def __init__(self, paper_mode=True, buy_amount=0.1):
        if not API_KEY or not WALLET_PUBLIC_KEY or not WALLET_PRIVATE_KEY:
            raise ValueError("API keys or wallet keys not set. Please set them in the .env file.")
        
        # Validate buy_amount
        if buy_amount <= 0:
            raise ValueError("buy_amount must be greater than 0.")
        
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.base_url = BASE_URL
        self.paper_mode = paper_mode  # This flag no longer changes order simulation
        self.virtual_balance = 1  # Starting with 1 SOL
        self.positions = {}  # Track virtual positions
        self.market_data = {}  # Store market data from WebSocket
        self.token_prices = {}  # Track token prices
        self.token_volumes = {}  # Track token volumes
        self.analyzed_tokens = {}  # Cache for analyzed tokens
        self.analysis_cache_time = 300  # Cache analysis results for 5 minutes
        
        # Trading parameters - lowered thresholds for testing
        self.min_volume_threshold = 0.01  # Lowered to 0.01 SOL volume
        self.position_size = 0.1  # 10% of balance per trade
        self.min_price_change = 0.01  # Lowered to 1% minimum price change
        
        # Setup separate logging for market data
        self.market_logger = self.setup_market_logger()
        self.buy_amount = buy_amount  # Configurable buy amount as a percentage of balance

        # Setup general logging to file
        self.setup_logging()

    def setup_logging(self):
        """
        Sets up logging to a file for all logs.
        """
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
        file_handler = logging.FileHandler('trading_bot.log')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)

    def setup_market_logger(self):
        """
        Sets up a separate logger for market data that won't interfere with the stats display
        """
        market_logger = logging.getLogger('market_data')
        market_logger.setLevel(logging.INFO)
        
        # Create a file handler
        fh = logging.FileHandler('market_data.log')
        fh.setLevel(logging.INFO)
        
        # Create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Create formatter and add it to the handlers
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        # Add the handlers to logger
        market_logger.addHandler(fh)
        market_logger.addHandler(ch)
        
        return market_logger

    def get_market_data(self):
        """
        Returns the current market data collected from WebSocket feeds.
        """
        logging.debug(f"Current market data: {self.market_data}")
        return self.market_data

    def place_order(self, coin: str, side: str, quantity: float, price: float):
        """
        Places an order for a given token.
        In this updated version, whether the bot is in paper mode or not,
        the order is simulated (i.e. no API call is made).
        """
        logging.info(f"{LogColors.OKBLUE}Simulating {side} order for {coin}: quantity={quantity}, price={price}{LogColors.ENDC}")
        self.simulate_trade(coin, side, quantity, price)

    def simulate_trade(self, coin: str, side: str, quantity: float, price: float):
        """
        Simulates a trade by updating the virtual balance and positions.
        This simulation is identical regardless of mode.
        """
        try:
            if side == 'buy':
                cost = quantity * price
                if self.virtual_balance >= cost:
                    self.virtual_balance -= cost
                    self.positions[coin] = self.positions.get(coin, 0) + quantity
                    self.token_prices[coin] = price  # Store purchase price
                    logging.info(
                        f"{LogColors.OKCYAN}\n=== SIMULATED BUY ===\n"
                        f"Token: {coin}\n"
                        f"Quantity: {quantity:.4f}\n"
                        f"Price: ◎{price:.4f}\n"
                        f"Cost: ◎{cost:.4f}\n"
                        f"New Balance: ◎{self.virtual_balance:.4f}\n"
                        f"Positions: {self.positions}\n"
                        f"Token Prices: {self.token_prices}{LogColors.ENDC}"
                    )
                else:
                    logging.warning(f"{LogColors.WARNING}Insufficient balance for simulated buy: {cost} > {self.virtual_balance}{LogColors.ENDC}")
            elif side == 'sell':
                if coin in self.positions and self.positions[coin] >= quantity:
                    proceeds = quantity * price
                    self.virtual_balance += proceeds
                    self.positions[coin] -= quantity
                    if self.positions[coin] <= 0:
                        del self.positions[coin]
                        del self.token_prices[coin]
                    logging.info(
                        f"{LogColors.OKCYAN}\n=== SIMULATED SELL ===\n"
                        f"Token: {coin}\n"
                        f"Quantity: {quantity:.4f}\n"
                        f"Price: ◎{price:.4f}\n"
                        f"Proceeds: ◎{proceeds:.4f}\n"
                        f"New Balance: ◎{self.virtual_balance:.4f}\n"
                        f"Positions: {self.positions}\n"
                        f"Token Prices: {self.token_prices}{LogColors.ENDC}"
                    )
                else:
                    logging.warning(f"{LogColors.WARNING}Insufficient position for simulated sell: {coin} position: {self.positions.get(coin, 0)}{LogColors.ENDC}")
        except Exception as e:
            logging.error(f"{LogColors.FAIL}Error in simulate_trade: {e}{LogColors.ENDC}")
            raise e

    def connect_to_websocket(self):
        """
        Connects to the PumpPortal WebSocket for real-time data.
        """
        ws = websocket.WebSocketApp(
            "wss://pumpportal.fun/api/data",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
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
            
            # Handle known message patterns
            if 'message' in data:
                logging.info(f"Info message received: {data['message']}")
                return
            
            if 'errors' in data:
                logging.error(f"Error message received: {data['errors']}")
                return
            
            # Attempt to process messages without an explicit event type
            if 'txType' in data and data['txType'] == 'create':
                logging.info(f"Processing token creation event for: {data.get('symbol', 'Unknown')}")
                self.handle_new_token(data)
                return
            
            # Check if this is a subscription confirmation
            if 'result' in data:
                logging.info(f"Subscription response: {data}")
                return
                
            event_type = data.get('type')
            if not event_type:
                # Log the entire message if no event type is found
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
            self.print_stats()  # Print stats after processing each event
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
        token_address = data.get('mint')
        symbol = data.get('symbol', 'Unknown')
        logging.info(f"New token created: {symbol} ({token_address})")
        
        # Update market data with initial information
        self.market_data[token_address] = {
            'symbol': symbol,
            'address': token_address,
            'initial_buy': data.get('initialBuy', 0),
            'sol_amount': data.get('solAmount', 0),
            'market_cap_sol': data.get('marketCapSol', 0),
            'last_trade': time.time()
        }
        
        # Log the market data for debugging
        logging.debug(f"Market data updated for {symbol}: {self.market_data[token_address]}")
        
        # Add your token analysis logic here
        self.examine_token_contract(token_address)
        
        # Ensure the token is analyzed
        if self.should_analyze_token(token_address):
            logging.info(f"{LogColors.OKBLUE}Analyzing token: {symbol}{LogColors.ENDC}")
            token_data = self.market_data.get(token_address, {})
            if token_data:
                # Check if all necessary data is present
                if 'price' in token_data and 'volume' in token_data:
                    self.execute_momentum_trade(token_data)
                else:
                    logging.warning(f"{LogColors.WARNING}Insufficient data for executing trade on {symbol}. Missing price or volume.{LogColors.ENDC}")
            else:
                logging.warning(f"{LogColors.WARNING}No token data available for {symbol} during trade execution.{LogColors.ENDC}")
        else:
            logging.info(f"{LogColors.WARNING}Token {symbol} does not need analysis (cached).{LogColors.ENDC}")

    def handle_token_trade(self, data):
        """
        Handles token trade events and updates market data.
        """
        token = data.get('mint')
        market_cap = data.get('marketCapSol')
        
        if token:
            # Update market data
            self.market_data[token] = {
                'market_cap': market_cap,
                'address': token,
                'last_trade': time.time(),
                'symbol': data.get('symbol', 'Unknown')
            }
            
            # Log market data separately
            self.market_logger.info(
                f"TRADE | Token: {token[:12]:<12} | "
                f"Market Cap: ◎{market_cap:<10.4f}"
            )
            
            # Ensure the token is analyzed
            if self.should_analyze_token(token):
                logging.info(f"{LogColors.OKBLUE}Analyzing token: {token}{LogColors.ENDC}")
                self.execute_momentum_trade(self.market_data[token])
            else:
                logging.info(f"{LogColors.WARNING}Token {token} does not need analysis (cached).{LogColors.ENDC}")

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

    def examine_token_contract(self, token_address):
        """
        Examines the token contract using the GMGN API.
        Retries if the token is too new to be examined.
        """
        max_retries = 5
        retry_delay = 7200  # 2 hours in seconds

        for attempt in range(max_retries):
            try:
                api_url = (
                    f"https://gmgn.ai/defi/router/v1/sol/tx/get_swap_route?"
                    f"token_in_address={token_address}&"
                    f"token_out_address=So11111111111111111111111111111111111111112&"
                    f"in_amount=100000000&"
                    f"from_address={WALLET_PUBLIC_KEY}&"
                    f"slippage=5.0"
                )
                logging.debug(f"API Request URL: {api_url}")
                response = self.session.get(api_url)
                
                if response.status_code != 200:
                    logging.warning(f"Non-200 response for token contract examination: {response.status_code}")
                    return False
                
                data = response.json()
                if data.get('code') == 0:
                    logging.info(f"Token {token_address} contract examination successful.")
                    return True
                else:
                    error_message = data.get('msg', 'Unknown error')
                    if "jupiter has no route" in error_message:
                        logging.warning(f"Token {token_address} examination failed: No route available for swap.")
                    else:
                        logging.warning(f"Token {token_address} contract examination failed: {error_message}")
                    return False
            except requests.RequestException as e:
                logging.error(f"Failed to examine token contract: {e}")
                return False

            # If the token is too new, wait and retry
            logging.info(f"Token {token_address} is too new for examination. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

        logging.warning(f"Token {token_address} could not be examined after {max_retries} attempts.")
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

    def add_to_final_database(self, token_address, token_details):
        """
        Adds a token to the final database for trading if it passes all checks.
        """
        # Placeholder for final database logic
        # e.g., self.final_database.insert(token_address, token_details)
        logging.info(f"Token {token_address} added to the final database for trading.")

    def calculate_momentum(self, token_data):
        """
        Calculates momentum for a given token using market cap.
        Returns a score between 0 and 1.
        """
        if not token_data:
            logging.debug("No token data provided")
            return 0

        market_cap = token_data.get('market_cap', 0)
        
        logging.debug(f"Analyzing token: Market Cap={market_cap}")
        
        # Skip if basic requirements aren't met
        if market_cap <= 0:
            logging.debug("Skipping: Market Cap <= 0")
            return 0
            
        # Calculate market cap score (0-1)
        market_cap_score = min(market_cap / (self.min_market_cap_threshold * 10), 1)
        
        # Combined score (100% market cap)
        momentum_score = market_cap_score
        
        logging.info(
            f"Momentum analysis for {token_data.get('symbol')}: \n"
            f"  Market Cap: ◎{market_cap:.4f} (Score: {market_cap_score:.2f})\n"
            f"  Total Score: {momentum_score:.2f}"
        )
        
        return momentum_score

    def execute_momentum_trade(self, token_data):
        """
        Executes a trade based on market cap changes.
        """
        try:
            symbol = token_data['symbol']
            market_cap = token_data['market_cap']
            
            # Example trade logic based on market cap
            if market_cap > self.min_market_cap_threshold:
                logging.info(f"{LogColors.OKGREEN}Executing trade for {symbol} with market cap {market_cap}.{LogColors.ENDC}")
                # Simulate or place a real order
                self.place_order(symbol, 'buy', self.position_size, market_cap)
            else:
                logging.info(f"{LogColors.WARNING}Trade conditions not met for {symbol}. Market Cap: {market_cap}{LogColors.ENDC}")
        except Exception as e:
            logging.error(f"{LogColors.FAIL}Error executing momentum trade: {e}{LogColors.ENDC}")

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
        Prints trading statistics without clearing the console.
        """
        try:
            # Calculate values with debug logging
            holdings_value = 0
            holdings_details = []
            
            for token, amount in self.positions.items():
                market_cap = self.token_prices.get(token, 0)
                value = amount * market_cap
                holdings_value += value
                
                if amount > 0:
                    holdings_details.append({
                        'token': token,
                        'amount': amount,
                        'market_cap': market_cap,
                        'value': value
                    })
                    logging.debug(f"Position: {token} - Amount: {amount}, Market Cap: {market_cap}, Value: {value}")
            
            total_value = self.virtual_balance + holdings_value
            current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            
            # Debug state
            logging.debug(f"Virtual Balance: {self.virtual_balance}")
            logging.debug(f"Holdings Value: {holdings_value}")
            logging.debug(f"Total Value: {total_value}")
            logging.debug(f"Current Positions: {self.positions}")
            logging.debug(f"Token Prices: {self.token_prices}")
            
            # Format the statistics
            stats = f"""
{LogColors.HEADER}╔══════════════════════════════════════════════════════════════════╗
║                     PumpFun Trading Bot Stats                     ║
╠═══════════════════════════════╦══════════════════════════════════╣
║ ACCOUNT SUMMARY               ║ TRADING ACTIVITY                  ║
╟───────────────────────────────╫──────────────────────────────────╢
║ Virtual Balance: ◎{self.virtual_balance:<10.4f} ║ Paper Mode: {str(self.paper_mode):<19} ║
║ Holdings Value:  ◎{holdings_value:<10.4f} ║ Active Tokens: {len(self.positions):<16} ║
║ Total Value:     ◎{total_value:<10.4f} ║ Last Update: {current_time}  ║
╠═══════════════════════════════╩══════════════════════════════════╣
║ CURRENT HOLDINGS                                                 ║
╟──────────────────────────────────────────────────────────────────╢{LogColors.ENDC}"""

            # Add holdings details
            if holdings_details:
                for holding in holdings_details:
                    stats += f"\n{LogColors.OKBLUE}║ {holding['token'][:12]:<12} │ Amount: {holding['amount']:<10.4f} │ Market Cap: ◎{holding['market_cap']:<8.4f} │ ◎{holding['value']:<10.4f} ║{LogColors.ENDC}"
            else:
                stats += f"\n{LogColors.WARNING}║ No active positions                                              ║{LogColors.ENDC}"

            stats += f"\n{LogColors.HEADER}╚══════════════════════════════════════════════════════════════════╝{LogColors.ENDC}"
            
            print(stats)
            
        except Exception as e:
            logging.error(f"Error in print_stats: {e}")
            logging.error(f"Current state - Balance: {self.virtual_balance}, Positions: {self.positions}")
            raise e  # Re-raise to see full traceback

    def should_analyze_token(self, token_address):
        """
        Determines if a token needs to be analyzed based on cache.
        """
        last_analysis = self.analyzed_tokens.get(token_address)
        if not last_analysis:
            logging.debug(f"Token {token_address} needs analysis (not in cache).")
            return True
        
        current_time = time.time()
        if current_time - last_analysis['timestamp'] > self.analysis_cache_time:
            logging.debug(f"Token {token_address} needs re-analysis (cache expired).")
            return True
        
        logging.debug(f"Token {token_address} does not need analysis (cache valid).")
        return False

    def save_cache_to_file(self):
        """
        Saves the analyzed tokens cache to a file.
        """
        try:
            with open('analyzed_tokens_cache.json', 'w') as f:
                json.dump(self.analyzed_tokens, f, indent=4)
            logging.info("Analyzed tokens cache saved to file.")
        except Exception as e:
            logging.error(f"Failed to save cache to file: {e}")

    def run(self):
        """
        Main trading loop with optimized analysis.
        """
        # Clear screen once at start
        os.system('cls' if os.name == 'nt' else 'clear')
        
        logging.info("Starting PumpFun Trading Bot...")
        
        # Start WebSocket connection in a separate thread
        import threading
        ws_thread = threading.Thread(target=self.connect_to_websocket)
        ws_thread.daemon = True
        ws_thread.start()
        
        while True:
            try:
                self.print_stats()
                
                # Process market data and execute trades
                market_data = self.get_market_data()
                for token_address, token_data in market_data.items():
                    if not self.should_analyze_token(token_address):
                        continue
                    
                    analysis_result = {
                        'timestamp': time.time(),
                        'is_safe': False
                    }
                    
                    # Log the start of the legitimacy check
                    logging.info(f"{LogColors.OKBLUE}Starting legitimacy check for token: {token_address}{LogColors.ENDC}")
                    
                    if self.examine_token_contract(token_address):
                        logging.info(f"{LogColors.OKGREEN}Token {token_address} passed contract examination.{LogColors.ENDC}")
                        analysis_result['is_safe'] = True
                        self.execute_momentum_trade(token_data)
                    else:
                        logging.info(f"{LogColors.FAIL}Token {token_address} failed contract examination.{LogColors.ENDC}")
                    
                    self.analyzed_tokens[token_address] = analysis_result
                
                # Save cache to file periodically
                self.save_cache_to_file()
                
                time.sleep(1)
                
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(1)


def main():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        bot = PumpFunBot(paper_mode=True)
        bot.run()
    except Exception as e:
        logging.error(f"Error in trading bot: {e}")

if __name__ == "__main__":
    main() 