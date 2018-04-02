from pybitflyer import API as API_wrapper
import pybitflyer
import logging
from retry import retry
from retry.api import retry_call
import time
import calendar
import Bitflyer_config as config
import constants 
import requests
from exception import APIException


class ExecutionHandler(API_wrapper):

    SIDE_BUY = 'BUY'
    SIDE_SELL = 'SELL'

    CONDITION_TYPE_LIMIT = 'LIMIT'
    CONDITION_TYPE_MARKET = 'MARKET'
    CONDITION_TYPE_STOP = 'STOP'
    #CONDITION_TYPE_STOP_LIMIT = 'STOP_LIMIT'
    #CONDITION_TYPE_STOP_TRAIL = 'TRAIL'

    ORDER_STATE_ACTIVE = "ACTIVE"
    ORDER_STATE_CANCELED = "CANCELED"

    ERROR_MESSAGE = 'error_message'

    DEFAULT_COUNT = 200

    MAX_DELAY = 1024 # maximum number of seconds to delay ex. 1, 2, 4, ..., 512, 1024, 1024, 1024, ...

    def __init__(self, logger="logger_name", 
                 api_key=config.api_key, api_secret=config.api_secret, 
                 timeout=config.timeout):
        API_wrapper.__init__(self, api_key, api_secret, timeout)
        self.logger = logging.getLogger(logger)
        self.symbol_map = constants.symbol_map["Bitflyer"]
        self.symbol_map_reversed = {v: k for k, v in self.symbol_map.items()}
        self.active_symbols = self.get_active_symbols()
        self.markets = [m for m in self.active_symbols if m in self.get_markets()]


    def handle_response(self, resp, willRaise=False):
        ## forcing failure after __init__() to test backoff ##########
        #if 'tick_id' not in resp:                                   #
        #    raise APIException(msg="Test API error message")        #
        ##############################################################
        if self.ERROR_MESSAGE in resp:
            self.logger.warn(resp)
            if willRaise:
                raise APIException(msg=resp[self.ERROR_MESSAGE])
        return resp

    def get_markets(self):
        '''Gets list of native market pairs from API, using alias where possible'''
        endpoint = "/v1/getmarkets"
        mkt_dict = self.request(endpoint)
        mkt_list = []
        for mkt in mkt_dict:
            code = mkt["alias"] if "alias" in mkt else mkt["product_code"]
            mkt_list.append(code)
        # API quirk: for some reason doesn't include "BTC_USD", or "BTC_EUR"
        for mkt in ["BTC_USD", "BTC_EUR"]:
            if mkt not in mkt_list:
                try:
                    test = self.ticker(product_code=mkt)
                    self.handle_response(test, willRaise=True)
                    mkt_list.append(mkt)
                except APIException:
                    pass
        return mkt_list


    def _get_product_code(self, pair):
        '''ie. BTC_USD --> BTCUSD'''
        return self.symbol_map[pair]
    
    def _get_pair(self, product_code):
        '''ie. BTCUSD --> BTC_USD'''
        return self.symbol_map_reversed[product_code]


    def _get_side(self, side):
        if side == 'buy':
            return self.SIDE_BUY
        elif side == 'sell':
            return self.SIDE_SELL
        else:
            self.logger.exception("Invalid side")


    def _get_order_type(self, order_type):
        if order_type == 'market':
            return self.CONDITION_TYPE_MARKET
        elif order_type == 'limit':
            return self.CONDITION_TYPE_LIMIT
        elif order_type == 'stop':
            return self.CONDITION_TYPE_STOP
        else:
            self.logger.exception("Invalid order type")


    def get_active_symbols(self):
        '''Gets list of native market pairs fron CONFIG file'''
        return [self.symbol_map[s] for s in config.active_pairs]

    def convert_timestamp(self, timestamp):
        '''Converts Bitflyer time string to Epoch time
        ex: "2015-07-07T08:45:53" --> 1436258753'''
        timestamp = timestamp.split('.')[0]
        format = '%Y-%m-%dT%H:%M:%S'
        struct_time = time.strptime(timestamp, format)
        return int(calendar.timegm(struct_time))

    def getchildorders_raise(self, **params):
        resp = self.getchildorders(**params)
        resp = self.handle_response(resp, willRaise=True)
        return resp

    def getparentorders_raise(self, **params):
        resp = self.getparentorders(**params)
        resp = self.handle_response(resp, willRaise=True)
        return resp
    
    def get_all_child_orders(self, count=DEFAULT_COUNT):
        '''requires multiple API calls, 1 for each pair in self.markets'''
        output = {}
        for code in self.markets:
            fkwargs = {"product_code": code,
                       "count": count} 

            resp = retry_call(self.getchildorders_raise, fkwargs=fkwargs, 
                              exceptions=(IOError, APIException), 
                              delay=1, backoff=2, max_delay=self.MAX_DELAY, logger=self.logger)

            if resp != []:
                # When there are open orders for a product_code
                for order in resp:
                    id = order["child_order_acceptance_id"]
                    output[id] = {"open_time": self.convert_timestamp(order["child_order_date"]),
                                    "pair": self._get_pair(order["product_code"]), 
                                    "side": order["side"].lower(),
                                    "price": order["price"],
                                    "volume": order["executed_size"],
                                    "outstanding_size": order["outstanding_size"],
                                    "state": order["child_order_state"],
                                    "order_type": order["child_order_type"],
                                    "average_price": order["average_price"],
                                    "fee": order["total_commission"],
                                    "close_time": None
                                    }
        return output

    def get_all_parent_orders(self, count=DEFAULT_COUNT):
        '''requires multiple API calls, 1 for each pair in self.markets'''
        output = {}
        for code in self.markets:
            fkwargs = {"product_code": code,
                       "count": count} 

            resp = retry_call(self.getparentorders_raise, fkwargs=fkwargs, 
                              exceptions=(IOError, APIException), 
                              delay=1, backoff=2, max_delay=self.MAX_DELAY, logger=self.logger)
     
            if resp != []:
                # When there are open orders for a product_code
                for order in resp:
                    id = order["parent_order_acceptance_id"]
                    output[id] = {"open_time": self.convert_timestamp(order["parent_order_date"]),
                                    "pair": self._get_pair(order["product_code"]), 
                                    "side": order["side"].lower(),
                                    "price": order["price"],
                                    "volume": order["executed_size"],
                                    "outstanding_size": order["outstanding_size"],
                                    "state": order["parent_order_state"],
                                    "order_type": order["parent_order_type"],
                                    "average_price": order["average_price"],
                                    "fee": order["total_commission"],
                                    "close_time": None}
        return output

    def get_all_orders(self, count=DEFAULT_COUNT):
        '''requires multiple API calls, 2 for each pair in self.markets
        optional param: count = Number of orders to include (per product_code)
        Uses exponential backoff for each API call'''
        output = self.get_all_child_orders(count)      # MARKET & LIMIT
        output.update(self.get_all_parent_orders(count))    # STOP
        return output
        
  

    def get_open_orders(self):
        all_orders = self.get_all_orders()
        output = {}
        for order_id, details in all_orders.items():
            if details["state"] == self.ORDER_STATE_ACTIVE:
                d = {'open_time': details['open_time'],
                     'pair': details['pair'],
                     'side': details['side'],
                     'price': details['price'],
                     'volume': details['volume'],
                     'order_type': details['order_type']}
                output[order_id] = d
        return output


    def get_closed_orders(self):
        # A closed order may have either been cancelled, partially filled or completely filled
        all_orders = self.get_all_orders()
        output = {}
        for order_id, details in all_orders.items():
            if details["volume"] != 0 or details["state"] == self.ORDER_STATE_CANCELED:
                if details['average_price'] != 0:
                    d_price = details['price']
                else:
                    d_price = details['average_price']
                d_cost = d_price * details['volume']
                d = {'close_time': details['close_time'],
                     'pair': details['pair'],
                     'side': details['side'],
                     'price': d_price,
                     'volume_executed': details['volume'],
                     'cost': d_cost,
                     'fee': details['fee'],
                     'order_type': details['order_type']}
                output[order_id] = d
        return output

    def cancelchildorder_raise(self, **params):
        resp = self.cancelchildorder(**params)
        resp = self.handle_response(resp, willRaise=True)
        return resp

    def cancelallchildorders_raise(self, **params):
        resp = self.cancelallchildorders(**params)
        resp = self.handle_response(resp, willRaise=True)
        return resp

    def cancelallparentorders_raise(self, **params):
        resp = self.cancelallparentorders(**params)
        resp = self.handle_response(resp, willRaise=True)
        return resp

    def clear_open_orders(self, pair):
        '''Cancel all child orders in one command and then each parent order'''
        fkwargs = {"product_code": self._get_product_code(pair)}
        resp1 = retry_call(self.cancelallchildorders_raise, fkwargs=fkwargs,
                           exceptions=(IOError, APIException), 
                           delay=1, backoff=2, max_delay=self.MAX_DELAY, logger=self.logger)
        if resp1 == '':
            self.logger.debug("cancelallchildorders sent")
        else:
            self.logger.debug(resp1)
        # Make sure that all orders were cancelled
        time.sleep(2)
        open_orders = self.get_open_orders()
        for order in open_orders.items():
            if order[1]['pair'] == pair:
                self.delete_order(pair, order[0])
                # retry to make sure they are all closed
                msg = "{} was deleted individually".format(order[0])
                self.logger.debug(msg)
        self.logger.debug("clear_open_orders({}) completed".format(pair))


    def insert_market_order(self, pair, side, volume):
        '''If successful: returns order id. If failed returns null.'''
        try:
            product_code = self._get_product_code(pair)
            side = self._get_side(side)
            resp = self.sendchildorder(child_order_type=self.CONDITION_TYPE_MARKET, product_code=product_code, 
                                       side=side, size=volume)
            resp = self.handle_response(resp, willRaise=True)
            return resp['child_order_acceptance_id']
        except:
            return None


    def insert_limit_order(self, pair, side, price, volume):
        '''If successful: returns order id. If failed returns null.'''
        try:
            product_code = self._get_product_code(pair)
            side = self._get_side(side)
            resp = self.sendchildorder(child_order_type=self.CONDITION_TYPE_LIMIT, 
                                       product_code=product_code, 
                                       price=price, side=side, size=volume)
            resp = self.handle_response(resp, willRaise=True)
            return resp['child_order_acceptance_id']
        except:
            return None

    def insert_stop_order(self, pair, side, trigger_price, volume):
        '''If successful: returns order id. If failed returns null.'''
        try:
            product_code = self._get_product_code(pair)
            side = self._get_side(side)
            params = {"product_code": product_code,
                      "side": side,
                      "condition_type": self.CONDITION_TYPE_STOP,
                      "size": volume,
                      "trigger_price": trigger_price}
            resp = self.sendparentorder(parameters=[params])   
            resp = self.handle_response(resp, willRaise=True)
            return resp['parent_order_acceptance_id']
        except:
            return None

    def insert_order(self, pair, side, order_type, price, volume, leverage):
        '''If successful: returns order id. If failed returns null.'''
        order_type = self._get_order_type(order_type)

        if order_type == self.CONDITION_TYPE_LIMIT:
            return self.insert_limit_order(pair, side, price, volume)

        elif order_type == self.CONDITION_TYPE_MARKET:
            return self.insert_market_order(pair, side, volume)

        elif order_type == self.CONDITION_TYPE_STOP:
            return self.insert_stop_order(pair, side, price, volume)


    def delete_child_order(self, pair, order_id):
        try:
            product_code = self._get_product_code(pair)
            fkwargs = {"product_code": product_code,
                       "child_order_acceptance_id": order_id}
            resp = retry_call(self.cancelchildorder_raise, fkwargs=fkwargs,
                              exceptions=(IOError, APIException), 
                              delay=1, backoff=2, max_delay=self.MAX_DELAY, logger=self.logger)
            return resp == '' # returns True or False
        except:
            return None

    def delete_parent_order(self, pair, order_id):
        try:
            product_code = self._get_product_code(pair)
            fkwargs = {"product_code": product_code,
                       "parent_order_acceptance_id": order_id}
            resp = retry_call(self.cancelparentorder_raise, fkwargs=fkwargs,
                              exceptions=(IOError, APIException), 
                              delay=1, backoff=2, max_delay=self.MAX_DELAY, logger=self.logger)
            return resp == '' # returns True or False
        except:
            return None

    def delete_order(self, pair, order_id, order_type='limit'):
        if order_type == self.CONDITION_TYPE_STOP:
            return self.delete_parent_order(pair, order_id)   #stop
        else:
            return self.delete_child_order(pair, order_id)    #limit, market

    def test_sell(self):
        pair = "BTCUSD"
        side = "sell"
        type = "limit"
        price = 9000
        qty = 0.001
        order_id = self.insert_order(pair, side, type, price, qty, 0)
        print(order_id)
        return order_id

#--------------------------------------------------
if __name__ == "__main__":
    t1 = ExecutionHandler()
    print("markets:", t1.markets)
    print("open orders:", t1.get_open_orders())
    o = t1.test_sell()
    time.sleep(2)
    print("open orders:", t1.get_open_orders())
    t1.clear_open_orders("BTCUSD")
    print("open orders:", t1.get_open_orders())


