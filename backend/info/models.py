from django.db import models

class FundBasicInfo(models.Model):
    fund_id = models.AutoField(primary_key=True)
    fund_code = models.CharField(max_length=20, unique=True)
    fund_name = models.CharField(max_length=200)
    fund_type = models.CharField(max_length=50)
    currency = models.CharField(max_length=10,default='CNY')  # Default to CNY, can be changed as needed
    # SH or SZ for China, NYSE or NASDAQ for US etc.
    listing_exchange = models.CharField(max_length=100)
    fund_company = models.CharField(max_length=100)
    inception_date = models.DateField()
    index_tracked = models.CharField(max_length=200, blank=True, null=True)
    management_fee = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    custodian_fee = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)

    def __str__(self):
        return f"({self.fund_name}) ({self.fund_code})"

class FundDailyData(models.Model):
    '''
    OCHLV + NAV + Estimated NAV
    O: Opening Price
    C: Closing Price
    H: Highest Price
    L: Lowest Price
    V: Trading Volume
    NAV: Net Asset Value
    Estimated NAV: Estimated Net Asset Value (for ETFs)
    '''
    
    fund = models.ForeignKey(FundBasicInfo, on_delete=models.CASCADE)
    date = models.DateField()
    open = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    close = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    high = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    low = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    volume = models.BigIntegerField(blank=True, null=True)
    net_asset_value = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    estimated_nav = models.DecimalField(max_digits=15, decimal_places=4, blank=True, null=True)
    # Uncomment if needed
    # turnover_rate = models.DecimalField(max_digits=5, decimal_places=4, blank=True, null=True)
    class Meta:
        unique_together = ('fund', 'date')
        ordering = ['-date']