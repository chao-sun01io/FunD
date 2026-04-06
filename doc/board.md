## Goal 1: For each fund, display an interactive chart of historical price, NAV, and volume data on the existing info page.

> Get the very basic version online, to collect data for future analysis.

### Tasks
- [x] 1. Implement the front end chart, without worrying about the data source (use hardcoded sample data for now)
- [x] 2. Implment the backend to serve historical data, and connect it to the front end chart (initially with static data)
    - It can be a simple API endpoint that returns hardcoded JSON data for now, to be replaced with real DB queries in the future. 
- [x] 3. Implement MarketDataProvider for historical OHLCV data
- [ ] 4. Implement NAV fetching and storage (daily end-of-day NAV + intraday estimated NAV), and display it on the chart
- [ ] 5. For 1D time rance, use the 1-min intraday data. For longer ranges (5D, 1M, 3M, YTD, 1Y), use the historical OHLCV data
- [ ] 6. For historical data, buffer the data in DataBase

## Goals
- [ ] Goal 1: Implement the basic fund display functionality
- [ ] Goal 2: Implement the Est.Nav / premium discount to discover trading opportunities

## Backlog
- Responsive design for mobile
- Using Restful API + Vue.js for frontend (instead of Django templates) when the logic gets more complex (e.g. multiple pages, user accounts, etc.). But keep it simple for now with server-side rendering and minimal JS.
- Use time-series database (e.g. TimescaleDB) for storing historical price data if the volume grows significantly, to improve query performance and enable advanced time-series features.