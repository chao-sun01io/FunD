from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from .utils import redis_conn
from .models import FundBasicInfo, FundDailyData

def index(request):
    funds = FundBasicInfo.objects.all()
    return render(request, 'info/index.html', {'funds': funds})

def detail(request, symbol):
    '''
    This view is used to display the detail of a fund.

    args:
        symbol: the symbol of the fund

    returns:
        a HTML page with the detail of the fund
    '''
    try:
        fund = FundBasicInfo.objects.get(fund_code=symbol.upper())
        
        # Get recent 5 days of daily data
        daily_data = FundDailyData.objects.filter(fund=fund).order_by('-date')[:5]
        
        # Get latest price data from Redis
        redis_client = redis_conn.get_redis_conn()
        if not redis_client:
            return render(request, '404.html', status=404)
        latest_quote_key = f"info:{symbol.lower()}:latest_quote"
        latest_quote_raw = redis_client.get(latest_quote_key)
        
        latest_price = None
        if latest_quote_raw:
            print(latest_quote_raw)
            try:
                # Parse the quote data (stored as Python dict string)
                import ast
                decoded_data = latest_quote_raw.decode('utf-8')
                parsed_data = ast.literal_eval(decoded_data)
                
                # Extract KWEB data from the dictionary
                if 'KWEB' in parsed_data:
                    kweb_data = parsed_data['KWEB']
                    latest_price = {
                        'price': kweb_data.get('price'),
                        'change': kweb_data.get('change'),
                        # 'change_percent': (kweb_data.get('change', 0) / kweb_data.get('overnight_price', 1)) * 100 if kweb_data.get('overnight_price') else 0,
                        'timestamp': kweb_data.get('datetime')
                    }
                print(latest_price)
            except (ValueError, SyntaxError, AttributeError) as e:
                print(f"Error parsing data: {e}")
                # If parsing fails, treat it as a simple string
                latest_price = {'price': latest_quote_raw.decode('utf-8')}
        
        return render(request, 'info/detail.html', {
            'fund': fund,
            'daily_data': daily_data,
            'latest_price': latest_price
        })
    except FundBasicInfo.DoesNotExist:
        return render(request, '404.html', status=404)