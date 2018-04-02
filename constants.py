## add to constants.py

'''We have a file called constants.py with symbol_map 
dict of dicts that takes exchange as first key, 
quotebase as next key which results in the exchange specific name
'''

symbol_map = {'Bitflyer':
              {'BTCJPY': 'BTC_JPY',
               'BTCUSD': 'BTC_USD',
               'BTCEUR': 'BTC_EUR',
               'ETHBTC': 'ETH_BTC',
               'BCHBTC': 'BCH_BTC',
               'BTCJPY_FX': 'FX_BTC_JPY',
               'BTCJPY_MAT1WK': 'BTCJPY_MAT1WK',
               'BTCJPY_MAT2WK': 'BTCJPY_MAT2WK'
              }}
'''
[{"product_code":"BTC_JPY"},{"product_code":"FX_BTC_JPY"},{"product_code":"ETH_BTC"},
{"product_code":"BCH_BTC"},{"product_code":"BTCJPY30MAR2018","alias":"BTCJPY_MAT1WK"},
{"product_code":"BTCJPY06APR2018","alias":"BTCJPY_MAT2WK"}]
'''