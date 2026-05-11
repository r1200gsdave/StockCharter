import subprocess

_OPINION_URL = "https://www.barchart.com/stocks/quotes/{ticker}/opinion"


def get_opinion(ticker: str) -> str:
    url = _OPINION_URL.format(ticker=ticker.upper())
    result = subprocess.run(
        ["w3m", "-dump", url],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Mirror the bash logic: grep -A 6 "[Barchart Opinion" | grep -v ^$ | grep -v ^Over
    found = False
    collected = []
    for line in result.stdout.splitlines():
        if "[Barchart Opinion" in line:
            found = True
            continue
        if found:
            stripped = line.strip()
            if stripped and not stripped.startswith("Over"):
                collected.append(stripped)
            if len(collected) >= 6:
                break
    return collected[0] if collected else "N/A"
