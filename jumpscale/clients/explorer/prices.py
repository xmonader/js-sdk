from .base import BaseResource


class Prices(BaseResource):
    _resource = "prices"

    def get(self):
        response = self._session.get(self._url)
        prices_dict = response.json()
        return {
            "cu": prices_dict["CuPriceDollarMonth"],
            "su": prices_dict["CuPriceDollarMonth"],
            "ipv4u": prices_dict["CuPriceDollarMonth"]
        
        }

