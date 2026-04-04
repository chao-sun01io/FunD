from django.http import JsonResponse


def _get_history(fund_code: str) -> list[dict]:
    """
    Returns historical OHLCV+NAV data as a list of dicts shaped for Lightweight Charts:
      [{"time": "YYYY-MM-DD", "open": float, "close": float, "high": float,
        "low": float, "nav": float, "volume": int}, ...]
    Ordered oldest-first (required by Lightweight Charts).

    STUB: returns hardcoded data. To switch to DB queries, replace the return
    statement below with the commented-out implementation.
    """
    return [
        {"time": "2025-02-17", "open": 27.10, "close": 27.42, "high": 27.65, "low": 26.95, "nav": 27.15, "volume": 3800000},
        {"time": "2025-02-18", "open": 27.42, "close": 27.89, "high": 28.05, "low": 27.31, "nav": 27.61, "volume": 4200000},
        {"time": "2025-02-19", "open": 27.95, "close": 28.14, "high": 28.42, "low": 27.80, "nav": 27.85, "volume": 5100000},
        {"time": "2025-02-20", "open": 28.20, "close": 27.73, "high": 28.35, "low": 27.58, "nav": 27.46, "volume": 3600000},
        {"time": "2025-02-21", "open": 27.68, "close": 28.32, "high": 28.55, "low": 27.50, "nav": 28.02, "volume": 6700000},
        {"time": "2025-02-24", "open": 28.45, "close": 29.05, "high": 29.30, "low": 28.32, "nav": 28.74, "volume": 7200000},
        {"time": "2025-02-25", "open": 29.10, "close": 28.81, "high": 29.25, "low": 28.62, "nav": 28.52, "volume": 4900000},
        {"time": "2025-02-26", "open": 28.75, "close": 29.47, "high": 29.68, "low": 28.61, "nav": 29.16, "volume": 8100000},
        {"time": "2025-02-27", "open": 29.52, "close": 29.12, "high": 29.70, "low": 28.95, "nav": 28.83, "volume": 5500000},
        {"time": "2025-02-28", "open": 29.08, "close": 28.65, "high": 29.20, "low": 28.48, "nav": 28.37, "volume": 6300000},
        {"time": "2025-03-03", "open": 28.80, "close": 30.18, "high": 30.45, "low": 28.72, "nav": 29.87, "volume": 9400000},
        {"time": "2025-03-04", "open": 30.22, "close": 30.74, "high": 30.98, "low": 30.05, "nav": 30.42, "volume": 8800000},
        {"time": "2025-03-05", "open": 30.80, "close": 31.02, "high": 31.25, "low": 30.62, "nav": 30.69, "volume": 7600000},
        {"time": "2025-03-06", "open": 31.10, "close": 30.56, "high": 31.22, "low": 30.38, "nav": 30.24, "volume": 5200000},
        {"time": "2025-03-07", "open": 30.48, "close": 31.38, "high": 31.60, "low": 30.35, "nav": 31.04, "volume": 6900000},
        {"time": "2025-03-10", "open": 31.42, "close": 31.95, "high": 32.18, "low": 31.28, "nav": 31.60, "volume": 7400000},
        {"time": "2025-03-11", "open": 32.00, "close": 32.47, "high": 32.75, "low": 31.88, "nav": 32.11, "volume": 9200000},
        {"time": "2025-03-12", "open": 32.55, "close": 31.83, "high": 32.70, "low": 31.65, "nav": 31.48, "volume": 6100000},
        {"time": "2025-03-13", "open": 31.78, "close": 32.16, "high": 32.40, "low": 31.60, "nav": 31.80, "volume": 5800000},
        {"time": "2025-03-14", "open": 32.20, "close": 33.04, "high": 33.28, "low": 32.05, "nav": 32.67, "volume": 10300000},
        {"time": "2025-03-17", "open": 33.10, "close": 33.52, "high": 33.78, "low": 32.95, "nav": 33.14, "volume": 8500000},
        {"time": "2025-03-18", "open": 33.58, "close": 32.89, "high": 33.72, "low": 32.70, "nav": 32.52, "volume": 7100000},
        {"time": "2025-03-19", "open": 32.85, "close": 33.71, "high": 33.95, "low": 32.72, "nav": 33.33, "volume": 9600000},
        {"time": "2025-03-20", "open": 33.75, "close": 34.15, "high": 34.42, "low": 33.58, "nav": 33.76, "volume": 11200000},
        {"time": "2025-03-21", "open": 34.20, "close": 33.68, "high": 34.38, "low": 33.50, "nav": 33.30, "volume": 7800000},
        {"time": "2025-03-24", "open": 33.62, "close": 34.43, "high": 34.65, "low": 33.48, "nav": 34.03, "volume": 8300000},
        {"time": "2025-03-25", "open": 34.48, "close": 33.97, "high": 34.62, "low": 33.78, "nav": 33.58, "volume": 6400000},
        {"time": "2025-03-26", "open": 33.92, "close": 34.82, "high": 35.05, "low": 33.78, "nav": 34.41, "volume": 9100000},
        {"time": "2025-03-27", "open": 34.88, "close": 34.29, "high": 35.02, "low": 34.12, "nav": 33.89, "volume": 7300000},
        {"time": "2025-03-28", "open": 34.25, "close": 35.11, "high": 35.35, "low": 34.10, "nav": 34.69, "volume": 12500000},
        {"time": "2025-03-31", "open": 35.15, "close": 35.78, "high": 36.02, "low": 35.00, "nav": 35.36, "volume": 9800000},
        {"time": "2025-04-01", "open": 35.82, "close": 35.42, "high": 35.98, "low": 35.22, "nav": 34.99, "volume": 8700000},
        {"time": "2025-04-02", "open": 35.38, "close": 36.05, "high": 36.28, "low": 35.22, "nav": 35.62, "volume": 11000000},
        {"time": "2025-04-03", "open": 36.10, "close": 36.48, "high": 36.72, "low": 35.95, "nav": 36.04, "volume": 13000000},
        {"time": "2025-04-04", "open": 36.52, "close": 35.89, "high": 36.65, "low": 35.70, "nav": 35.45, "volume": 9200000},
    ]

    # DB IMPLEMENTATION — uncomment to replace stub above:
    # from django.shortcuts import get_object_or_404
    # from .models import FundBasicInfo, FundDailyData
    # fund = get_object_or_404(FundBasicInfo, fund_code=fund_code.upper())
    # qs = (
    #     FundDailyData.objects
    #     .filter(fund=fund)
    #     .order_by('date')
    #     .values('date', 'open', 'close', 'high', 'low', 'net_asset_value', 'volume')
    # )
    # return [
    #     {
    #         "time":   str(row['date']),
    #         "open":   float(row['open'])              if row['open']              is not None else None,
    #         "close":  float(row['close'])             if row['close']             is not None else None,
    #         "high":   float(row['high'])              if row['high']              is not None else None,
    #         "low":    float(row['low'])               if row['low']               is not None else None,
    #         "nav":    float(row['net_asset_value'])   if row['net_asset_value']   is not None else None,
    #         "volume": row['volume'],
    #     }
    #     for row in qs
    # ]


def fund_history(request, symbol: str):
    if request.method != 'GET':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    return JsonResponse({"symbol": symbol.upper(), "data": _get_history(symbol)})
