"""Configuration for research-only, manual paper trading."""
from dataclasses import dataclass

STARTING_CASH = 1000.0
MAX_POSITION_FRACTION = 0.05
MAX_OPEN_POSITIONS = 4
MAX_DAILY_LOSS = 0.03
STOP_LOSS = 0.08
TAKE_PROFIT = 0.16
TRAILING_STOP = 0.10
ONE_WAY_COST = 0.01
MAX_QUOTE_AGE_SECONDS = 180
API = "https://api.dexscreener.com"
SEEDS = ["BONK", "WIF", "POPCAT", "FARTCOIN", "PENGU", "MEW", "BOME", "MOODENG", "GOAT", "PNUT", "MICHI", "MOG", "TURBO", "NEIRO", "GIGA", "PONKE", "FWOG", "JUP", "RAY", "WEN"]

@dataclass(frozen=True)
class Profile:
    liquidity: float
    volume: float
    transactions: int
    min_age: float
    min_score: float

PROFILES = {
    "Conservative": Profile(50000, 100000, 30, 24, 70),
    "Balanced": Profile(40000, 50000, 20, 12, 67),
    "Exploratory paper": Profile(25000, 25000, 10, 6, 65),
}
