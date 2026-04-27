class ProductSet:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.products = set()
        return cls._instance

    def get(self):
        return self.products

    def add(self, products_to_add):
        if isinstance(products_to_add, set):
            self.products = self.products.union(products_to_add)
        else:
            raise TypeError("products_to_add must be a set")

    def remove(self, products_to_remove):
        if isinstance(products_to_remove, set):
            self.products = self.products - products_to_remove
        else:
            raise TypeError("products_to_remove must be a set")
