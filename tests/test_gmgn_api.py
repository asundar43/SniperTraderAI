import requests
import logging

def test_gmgn_api(token_address, wallet_public_key):
    """
    Test the GMGN API with a dummy token address.
    """
    try:
        api_url = (
            f"https://gmgn.ai/defi/router/v1/sol/tx/get_swap_route?"
            f"token_in_address={token_address}&"
            f"token_out_address=So11111111111111111111111111111111111111112&"
            f"in_amount=100000000&"
            f"from_address={wallet_public_key}&"
            f"slippage=5.0"
        )
        response = requests.get(api_url)
        
        if response.status_code == 200:
            data = response.json()
            print("GMGN API Test Successful:", data)
        else:
            print(f"GMGN API Test Failed: Status Code {response.status_code}")
    except requests.RequestException as e:
        logging.error(f"Failed to test GMGN API: {e}")

# Example usage
if __name__ == "__main__":
    test_gmgn_api("dummy_token_address", "dummy_wallet_public_key") 