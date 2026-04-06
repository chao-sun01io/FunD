import logging

from django.http import JsonResponse

from info.market_data.service import HistoricalDataService

logger = logging.getLogger(__name__)

_service = HistoricalDataService()


def fund_history(request, symbol: str):
    if request.method != 'GET':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    range_key = request.GET.get('range', '1Y')
    try:
        data = _service.get_history(fund_code=symbol, range_key=range_key)
    except Exception:
        logger.exception("Error fetching history for %s", symbol)
        return JsonResponse({"error": "Internal error"}, status=500)

    return JsonResponse({"symbol": symbol.upper(), "data": data})
