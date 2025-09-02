import asyncio
import argparse
from agent import AgentInvest

def main():
    parser = argparse.ArgumentParser(description="Run AgentInvest PoC.")
    parser.add_argument("ticker", type=str, help="The stock ticker symbol to generate a report for (e.g., 'AAPL').")
    args = parser.parse_args()

    agent = AgentInvest()
    asyncio.run(agent.run(ticker=args.ticker))

if __name__ == "__main__":
    main()
