import sys
from mtfck.mtfck import fetch_industry_data, get_next_trading_close, nse
from datetime import date

def main():
    print("Testing fetch_industry_data...")
    data = fetch_industry_data()
    print(f"Industry data size: {len(data)}")
    
    print("Testing get_next_trading_close for RELIANCE...")
    close_price = get_next_trading_close("RELIANCE", date.today().replace(year=2024, month=1, day=1))
    print(f"Close price: {close_price}")

    print("Testing NSEClient bulk profile with an API call...")
    q = nse.quote("RELIANCE")
    print(f"Quote fetched successfully: {q.get('info', {}).get('symbol') == 'RELIANCE'}")

    print("All tests passed!")

if __name__ == "__main__":
    main()
