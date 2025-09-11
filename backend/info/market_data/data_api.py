import requests


def get_quotes_from_sina_us(symbols):
    """
    Retrieves the latest quotes for the given symbols from Sina Finance.
    """
    # example: https://hq.sinajs.cn/list=gb_pdd,gb_baba
    base_url = "https://hq.sinajs.cn/list="
    url = base_url + ",".join(["gb_" + symbol.lower() for symbol in symbols])
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "Referer": "https://finance.sina.com.cn/",
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.text
#         data = """
# var hq_str_gb_pdd="拼多多,115.0400,3.03,2025-07-23 05:38:21,3.3800,112.8700,115.5650,111.4800,155.6700,87.1100,8596054,6313535,163316128988,9.91,11.610000,0.00,0.00,0.00,0.00,1419646462,0,115.2500,0.18,0.21,Jul 22 05:36PM EDT,Jul 22 04:00PM EDT,111.6600,129868,1,2025,982125285.0000,122.4613,109.4400,14939144.4509,115.0400,111.6600";
# var hq_str_gb_tme="腾讯音乐,21.3600,0.33,2025-07-23 05:35:22,0.0700,21.0200,21.4650,20.8800,22.5000,9.2300,5837059,6789086,33084600205,0.86,24.840000,0.00,0.00,0.18,0.00,1548904504,0,21.3700,0.05,0.01,Jul 22 05:21PM EDT,Jul 22 04:00PM EDT,21.2900,35050,1,2025,123955126.0000,21.4000,21.1100,748817.7440,21.3600,21.3000";
#  """
        # Parse the data
        # print(data)
        quotes = {}
        lines = data.split(';')
        for i, line in enumerate(lines):
            if line:
                parts = line.split(',')
                if len(parts) < 3:
                    continue
                # Extract the symbol and price
                name = parts[0].split('=')[1].strip('"')
                price = float(parts[1])
                change = float(parts[2])
                datetime = str(parts[3])
                # Extract the overnight price if available
                if len(parts) > 22:
                    overnight_price = float(parts[21])
                    overnight_change = float(parts[22])
                    # print(f"overnight price {parts[21]} {parts[22]}")
                else:
                    # If overnight price is not available, set it to 0
                    overnight_price = 0.0
                    overnight_change = 0.0

                quotes[symbols[i]] = {
                    "name": name,
                    "datetime": datetime,
                    "price": price,
                    "change": change,
                    "overnight_price": overnight_price,
                    "overnight_change": overnight_change
                }
        return quotes
