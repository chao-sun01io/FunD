
## launch redis server

```bash
docker run --name redis-dev -p 6379:6379 -d redis # Start a Redis server in a Docker container named 'redis-dev', mapping port 6379
```

tips:
To stop the Redis server container, you can use:
```bash
docker stop redis-dev # Stop the Redis server container
```

To remove the Redis server container, you can use:
```bash
docker rm redis-dev # Remove the stopped Redis server container
```

## Key schema

design redis storage for the info app

- security live data
    - key : `info:<security_code>:latest`
    - value type: hash
       -  `security_code`: the code of the security
       -  `timestamp`: the timestamp of the data
       -  `open`: the opening price of the security
       -  `close`: the closing price of the security if available
       -  `price`: the current price of the security
       -  `change`: the change in price
       -  `change_percent`: the percentage change in price
- pcf of a fund
    - key:`info:<fund_code>:pcf:<date>`
    - value: a json object containing pcf data
- usd/cny exchange rate
    - key: `exchange_rate:usd2cny`
    - value
        - date: the date of the exchange rate, e.g., `2023-10-01`
        - rate: the exchange rate value, e.g., `6.4567` (example value)
- cny/hkd exchange rate
    - key: `exchange_rate:cny2hkd`
    - value: `1.2345` (example value)
- cny/hkd exchange rate: 
    - key: `exchange_rate:cny2hkd`
    - value: `1.2345` (example value)


### Name conventions

- key name should be in the format of `<app_name>:<security_code>:latest`
- security code should be in uppercase, and for securities in CN and HK markets, the listing exchange should be included in the security code. e.g. `00001.HK`, `600000.SH`, `000001.SZ`, `APPL`


