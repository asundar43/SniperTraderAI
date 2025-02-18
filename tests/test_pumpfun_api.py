import requests
import logging
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv('secrets.env')

def test_pumpfun_api():
    """
    Test the PumpFun API with the API key from environment variables.
    """
    try:
        api_key = os.getenv("PUMPFUN_API_KEY")
        if not api_key:
            raise ValueError("API key not found in environment variables.")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        response = requests.get("https://pumpportal.fun/api/test_endpoint", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print("PumpFun API Test Successful:", data)
        else:
            print(f"PumpFun API Test Failed: Status Code {response.status_code}")
            print("Response Content:", response.text)
    except requests.RequestException as e:
        logging.error(f"Failed to test PumpFun API: {e}")
    except ValueError as e:
        logging.error(e)

# Example usage
if __name__ == "__main__":
    test_pumpfun_api() 