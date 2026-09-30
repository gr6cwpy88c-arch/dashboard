# Daily briefing dashboard

Static site on GitHub Pages. A GitHub Action runs `scripts/build_data.py` every hour, writes `site/data.json`, and publishes `site/`.

- `config.json` – greeting, cities, feeds, tickers, "going crazy" threshold
- `scripts/build_data.py` – fetches everything (Python standard library only)
- `site/` – the page (`index.html`, `style.css`, `app.js`); `data.json` is generated

Run locally: `python3 scripts/build_data.py && python3 -m http.server --directory site`

Sources: BBC, Al Jazeera, Guardian, France 24, CNBC, ECB, Bank of England (RSS); Yahoo Finance (indices, commodities); Frankfurter (FX); CoinGecko (crypto); Open-Meteo (weather). No API keys.
